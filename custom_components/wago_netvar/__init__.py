"""Integracja Wago NetVar UDP (CODESYS 2.3 / .S3) dla Home Assistant.

Konfiguracja wyłącznie ręczna (YAML w configuration.yaml), bez config flow.
"""
import asyncio
import ipaddress
import logging
import math
import re
import time

import voluptuous as vol

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.number import NumberDeviceClass, NumberMode
from homeassistant.components.sensor import (
    DEVICE_CLASS_UNITS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv
from homeassistant.util import slugify

from .codec import (
    DEFAULT_MIN_INTERVAL,
    DEFAULT_ON_CHANGE,
    DEFAULT_PORT,
    DEFAULT_REQUIRE_VALUES,
    DEFAULT_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DIAGNOSTIC_REFRESH_INTERVAL,
    DOMAIN,
    ENTITY_CATEGORIES,
    HEADER_SIZE,
    MAGIC,
    MAX_PAYLOAD_SIZE,
    MODE_READ,
    MODE_WRITE,
    READ_ENTITIES,
    SERVICE_SEND_LIST,
    STRING_TYPE,
    SUPPORTED_TYPES,
    TEMPORAL_FORMATS,
    TEMPORAL_TYPES,
    WARNING_INTERVAL,
    WRITE_ENTITIES,
    encode_value,
    normalize_type,
    number_to_text,
    string_length,
    to_bool,
    type_range,
    variable_size,
)

_LOGGER = logging.getLogger(__name__)

# Opóźnienie (s) jednorazowej wysyłki po przywróceniu stanu encji po restarcie.
STARTUP_SEND_DELAY = 1.0

# Klucz "jednostki wysyłki" listy pakowanej (cała lista = jedna ramka). W liście niepakowanej
# jednostką jest pozycja zmiennej.
LIST_KEY = -1

# Dozwolone wartości device_class dla poszczególnych rodzajów encji.
DEVICE_CLASSES = {
    "sensor": tuple(item.value for item in SensorDeviceClass),
    "binary_sensor": tuple(item.value for item in BinarySensorDeviceClass),
    "switch": tuple(item.value for item in SwitchDeviceClass),
    "number": tuple(item.value for item in NumberDeviceClass),
}
STATE_CLASSES = tuple(item.value for item in SensorStateClass)
NUMBER_MODES = tuple(item.value for item in NumberMode)

DEVICE_KEYS = frozenset(
    {
        "ip_address",
        "port",
        "list_id",
        "mode",
        "direction",  # alias mode (nazwa używana w ESPHome)
        "send_on_change",  # alias on_change
        "pack_variables",
        "var_count",
        "payload_size",
        "on_change",
        "min_interval",
        "update_interval",
        "timeout",
        "require_values",
        "variables",
    }
)

VARIABLE_KEYS = frozenset(
    {
        "name",
        "unique_id",
        "offset",
        "byte_offset",  # alias offset (nazwa używana w ESPHome)
        "index",
        "type",
        "length",
        "entity",
        "format",
        "initial_value",
        "restore_value",
        "require_value",
        "min",
        "max",
        "step",
        "mode",
        "device_class",
        "state_class",
        "unit_of_measurement",
        "suggested_display_precision",
        "icon",
        "entity_category",
        "enabled_by_default",
        "force_update",
        "zero_as_unavailable",
        "visible_by_default",
        "suggested_unit_of_measurement",
        "inverted",
    }
)

# Pola dostępne tylko dla jednego rodzaju encji.
ENTITY_ONLY_KEYS = {
    "min": "number",
    "max": "number",
    "step": "number",
    "mode": "number",
    "state_class": "sensor",
    "suggested_display_precision": "sensor",
    "zero_as_unavailable": "sensor",
    "format": "sensor",
    "suggested_unit_of_measurement": "sensor",
}


# --------------------------------------------------------------------------
# Walidacja konfiguracji
# --------------------------------------------------------------------------


def _as_int(value, name, minimum=None, maximum=None):
    """Zwraca liczbę całkowitą albo zgłasza vol.Invalid."""
    if isinstance(value, bool):
        raise vol.Invalid(f"{name} musi być liczbą całkowitą")

    try:
        number = int(value)

        if isinstance(value, float) and not value.is_integer():
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise vol.Invalid(f"{name} musi być liczbą całkowitą") from None

    if minimum is not None and number < minimum:
        raise vol.Invalid(f"{name} musi być >= {minimum}")

    if maximum is not None and number > maximum:
        raise vol.Invalid(f"{name} musi być <= {maximum}")

    return number


def _as_number(value, name):
    """Zwraca skończoną liczbę zmiennoprzecinkową albo zgłasza vol.Invalid."""
    if isinstance(value, bool):
        raise vol.Invalid(f"{name} musi być liczbą")

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise vol.Invalid(f"{name} musi być liczbą") from None

    if not math.isfinite(number):
        raise vol.Invalid(f"{name} musi być liczbą skończoną")

    return number


_DURATION = re.compile(r"^(\d+(?:\.\d+)?)\s*(ms|s|min|h)?$")
_DURATION_UNITS = {"ms": 0.001, "s": 1.0, "min": 60.0, "h": 3600.0}


def _as_duration(value, name, default_unit):
    """Czas w sekundach. Przyjmuje liczbę (w default_unit) albo tekst: 500ms, 5s, 2min, 1h, never."""
    if isinstance(value, bool):
        raise vol.Invalid(f"{name} musi być czasem (np. 500ms, 5s, 2min)")

    if isinstance(value, (int, float)):
        number, unit = float(value), default_unit
    elif isinstance(value, str):
        text = value.strip().lower()

        if text == "never":
            return 0.0

        match = _DURATION.match(text)

        if match is None:
            raise vol.Invalid(f"{name} musi być czasem (np. 500ms, 5s, 2min)")

        number, unit = float(match.group(1)), match.group(2) or default_unit
    else:
        raise vol.Invalid(f"{name} musi być czasem (np. 500ms, 5s, 2min)")

    if not math.isfinite(number) or number < 0:
        raise vol.Invalid(f"{name} musi być liczbą nieujemną")

    return number * _DURATION_UNITS[unit]


def _as_bool(result, key):
    if key in result and not isinstance(result[key], bool):
        raise vol.Invalid(f"{key} musi być wartością logiczną (true/false)")


def _unit_allowed(device_class, unit):
    """Sprawdza, czy jednostka pasuje do device_class sensora."""
    try:
        units = DEVICE_CLASS_UNITS.get(SensorDeviceClass(device_class))
    except ValueError:
        return True

    if not units:
        return True

    allowed = set()

    for item in units:
        if item is None:
            continue

        if isinstance(item, type):
            allowed.update(str(member) for member in item)
        else:
            allowed.add(str(item))

    return not allowed or unit in allowed


def validate_variable(variable, mode=MODE_WRITE):
    """Walidacja definicji pojedynczej zmiennej NetVar.

    Offset i index mogą być pominięte: uzupełnia je validate_device.
    """
    if not isinstance(variable, dict):
        raise vol.Invalid("Definicja zmiennej musi być słownikiem")

    unknown = sorted(str(key) for key in set(variable) - VARIABLE_KEYS)

    if unknown:
        raise vol.Invalid(f"Nieznane pola zmiennej: {', '.join(unknown)}")

    for key in ("name", "type", "entity"):
        if key not in variable:
            raise vol.Invalid(f"Brakujące pole zmiennej: {key}")

    result = dict(variable)
    result["name"] = str(result["name"]).strip()

    if not result["name"]:
        raise vol.Invalid("Nazwa zmiennej nie może być pusta")

    if result.get("unique_id") is None:
        result.pop("unique_id", None)
    else:
        result["unique_id"] = str(result["unique_id"]).strip()

        if not result["unique_id"]:
            result.pop("unique_id")

    # byte_offset to alias offset (nazwa używana w konfiguracji ESPHome).
    if "byte_offset" in result:
        if "offset" in result:
            raise vol.Invalid("Użyj tylko offset (byte_offset to jego alias)")

        result["offset"] = result.pop("byte_offset")

    for key in ("offset", "index"):
        if result.get(key) is None:
            result.pop(key, None)
        else:
            result[key] = _as_int(
                result[key], key, 0, 65535 if key == "index" else None
            )

    result["type"] = normalize_type(result["type"])
    result["entity"] = str(result["entity"])
    entity = result["entity"]
    name = result["name"]

    if result["type"] not in SUPPORTED_TYPES:
        raise vol.Invalid(f"Nieobsługiwany typ zmiennej: {result['type']}")

    if entity not in READ_ENTITIES + WRITE_ENTITIES:
        raise vol.Invalid(f"Nieobsługiwany typ encji: {entity}")

    if result["type"] == "BOOL":
        if entity not in ("binary_sensor", "switch"):
            raise vol.Invalid("BOOL musi używać binary_sensor lub switch")
    elif entity in ("binary_sensor", "switch"):
        raise vol.Invalid("Tylko BOOL może używać binary_sensor lub switch")

    for key, owner in ENTITY_ONLY_KEYS.items():
        if key in result and entity != owner:
            raise vol.Invalid(
                f"Pole {key} (zmienna {name}) jest dostępne tylko dla encji {owner}"
            )

    if result["type"] == STRING_TYPE:
        # sensor = odczyt tekstu; number = zapis (liczba jest zamieniana na tekst).
        if entity not in ("sensor", "number"):
            raise vol.Invalid(
                "STRING może używać tylko encji sensor (odczyt) albo number "
                "(zapis, liczba zamieniana na tekst)"
            )

        try:
            result["length"] = string_length(result.get("length"))
        except ValueError as err:
            raise vol.Invalid(str(err)) from err
    elif "length" in result:
        raise vol.Invalid(f"Pole length (zmienna {name}) dotyczy tylko typu STRING")

    for key in (
        "device_class",
        "state_class",
        "unit_of_measurement",
        "icon",
        "entity_category",
    ):
        if result.get(key) is None:
            result.pop(key, None)
        else:
            result[key] = str(result[key])

    device_class = result.get("device_class")

    if device_class is not None and device_class not in DEVICE_CLASSES[entity]:
        raise vol.Invalid(
            f"Nieprawidłowa device_class '{device_class}' dla encji {entity}"
        )

    if result.get("state_class", STATE_CLASSES[0]) not in STATE_CLASSES:
        raise vol.Invalid(f"Nieprawidłowa state_class '{result['state_class']}'")

    if result.get("entity_category", ENTITY_CATEGORIES[0]) not in ENTITY_CATEGORIES:
        raise vol.Invalid(
            f"Nieprawidłowa entity_category '{result['entity_category']}'"
        )

    # Typy czasowe: sensor pokazuje tekst IEC (text, domyślnie) albo surową liczbę (raw).
    if "format" in result:
        if result["type"] not in TEMPORAL_TYPES:
            raise vol.Invalid(
                f"Pole format (zmienna {name}) dotyczy tylko typów "
                f"{', '.join(TEMPORAL_TYPES)}"
            )

        result["format"] = str(result["format"]).strip().lower()

        if result["format"] not in TEMPORAL_FORMATS:
            raise vol.Invalid(
                f"Nieprawidłowy format '{result['format']}' (dozwolone: "
                f"{', '.join(TEMPORAL_FORMATS)})"
            )
    elif entity == "sensor" and result["type"] in TEMPORAL_TYPES:
        result["format"] = "text"

    textual = entity == "sensor" and (
        result["type"] == STRING_TYPE or result.get("format") == "text"
    )

    if result["type"] == STRING_TYPE or textual:
        forbidden = (
            ("device_class", "state_class", "unit_of_measurement",
             "suggested_display_precision", "suggested_unit_of_measurement")
            if textual
            else ("device_class",)
        )

        if any(key in result for key in forbidden):
            raise vol.Invalid(
                f"Encja {entity} tekstowa ({name}, typ {result['type']}) nie "
                f"może mieć pól: {', '.join(forbidden)}"
            )

    unit = result.get("unit_of_measurement")

    if entity == "sensor" and device_class and unit:
        if not _unit_allowed(device_class, unit):
            raise vol.Invalid(
                f"Jednostka '{unit}' nie pasuje do device_class '{device_class}'"
            )

    if "suggested_display_precision" in result:
        result["suggested_display_precision"] = _as_int(
            result["suggested_display_precision"],
            "suggested_display_precision",
            0,
            15,
        )

    for key in (
        "enabled_by_default",
        "force_update",
        "zero_as_unavailable",
        "restore_value",
        "require_value",
        "visible_by_default",
        "inverted",
    ):
        _as_bool(result, key)

    if result.get("inverted") and entity not in ("binary_sensor", "switch"):
        raise vol.Invalid(
            f"inverted (zmienna {name}) dotyczy tylko encji binary_sensor i switch"
        )

    if result.get("restore_value") and entity not in ("switch", "number"):
        raise vol.Invalid(
            f"restore_value (zmienna {name}) dotyczy tylko encji switch i number"
        )

    if "require_value" in result and entity not in WRITE_ENTITIES:
        raise vol.Invalid(
            f"require_value (zmienna {name}) dotyczy tylko zmiennych list write"
        )

    result.setdefault("restore_value", False)

    result.setdefault("enabled_by_default", True)
    result.setdefault("force_update", False)

    if entity == "sensor":
        result.setdefault("zero_as_unavailable", False)

    if entity == "number":
        _validate_number(result)

    if mode == MODE_WRITE:
        _validate_initial_value(result)

    return result


def _validate_number(result):
    """Walidacja min/max/step/mode dla encji number."""
    limits = type_range(result["type"])

    if limits is None:
        for key in ("min", "max"):
            if key not in result:
                raise vol.Invalid(
                    f"Pole {key} jest wymagane dla encji number typu "
                    f"{result['type']}"
                )

    low, high = limits if limits else (0, 0)

    result["min"] = _as_number(result.get("min", low), "min")
    result["max"] = _as_number(result.get("max", high), "max")
    result["step"] = _as_number(result.get("step", 1), "step")

    if result["min"] >= result["max"]:
        raise vol.Invalid("min dla number musi być mniejsze niż max")

    if result["step"] <= 0:
        raise vol.Invalid("step dla number musi być dodatni")

    if limits:
        if result["min"] < low or result["max"] > high:
            raise vol.Invalid(
                f"min/max poza zakresem typu {result['type']} ({low}..{high})"
            )

        if not result["step"].is_integer():
            raise vol.Invalid(
                f"step dla typu {result['type']} musi być liczbą całkowitą"
            )

    result["mode"] = str(result.get("mode", NumberMode.AUTO.value))

    if result["mode"] not in NUMBER_MODES:
        raise vol.Invalid(
            f"Nieprawidłowy mode '{result['mode']}' (dozwolone: "
            f"{', '.join(NUMBER_MODES)})"
        )


def _validate_initial_value(result):
    """Walidacja initial_value zgodnie z kodowaniem typu zmiennej."""
    name = result["name"]

    # Czy wartość początkowa została podana jawnie (liczy się jako "zmienna ma wartość").
    result["initial_explicit"] = "initial_value" in result

    if "initial_value" not in result:
        if result["type"] == "BOOL":
            result["initial_value"] = False
        elif result["entity"] == "number":
            result["initial_value"] = min(
                max(0.0, result["min"]), result["max"]
            )
        elif result["type"] == STRING_TYPE:
            result["initial_value"] = ""
        else:
            result["initial_value"] = 0

    value = result["initial_value"]

    if result["type"] not in ("BOOL", STRING_TYPE) and isinstance(value, bool):
        raise vol.Invalid(
            f"initial_value dla {name} nie może być wartością logiczną"
        )

    try:
        encode_value(value, result["type"], result.get("length"))
    except ValueError as err:
        raise vol.Invalid(f"Nieprawidłowa initial_value dla {name}: {err}") from err

    if result["entity"] == "number":
        try:
            number = float(value)
        except (TypeError, ValueError) as err:
            raise vol.Invalid(
                f"initial_value dla {name} musi być liczbą"
            ) from err

        if not result["min"] <= number <= result["max"]:
            raise vol.Invalid(
                f"initial_value dla {name} jest poza zakresem min/max"
            )


def validate_device(device):
    """Walidacja konfiguracji urządzenia (listy NetVar)."""
    if not isinstance(device, dict):
        raise vol.Invalid("Konfiguracja urządzenia musi być słownikiem")

    unknown = sorted(str(key) for key in set(device) - DEVICE_KEYS)

    if unknown:
        raise vol.Invalid(f"Nieznane pola listy: {', '.join(unknown)}")

    result = dict(device)

    # direction to alias mode (nazwa używana w konfiguracji ESPHome).
    if "direction" in result:
        if "mode" in result:
            raise vol.Invalid("Użyj tylko mode (direction to jego alias)")

        result["mode"] = result.pop("direction")

    # send_on_change to alias on_change (nazwa używana w opisie założeń projektu).
    if "send_on_change" in result:
        if "on_change" in result:
            raise vol.Invalid("Użyj tylko on_change (send_on_change to jego alias)")

        result["on_change"] = result.pop("send_on_change")

    try:
        address = ipaddress.ip_address(str(result["ip_address"]).strip())
    except (KeyError, ValueError):
        raise vol.Invalid("Nieprawidłowy ip_address") from None

    if address.version != 4:
        raise vol.Invalid("ip_address musi być adresem IPv4")

    result["ip_address"] = str(address)

    result.setdefault("port", DEFAULT_PORT)
    result.setdefault("mode", MODE_READ)
    result.setdefault("pack_variables", True)
    result.setdefault("on_change", DEFAULT_ON_CHANGE)
    result.setdefault("min_interval", DEFAULT_MIN_INTERVAL)
    result.setdefault("update_interval", DEFAULT_UPDATE_INTERVAL)
    result.setdefault("timeout", DEFAULT_TIMEOUT)

    if "list_id" not in result:
        raise vol.Invalid("Brakujące pole listy: list_id")

    result["port"] = _as_int(result["port"], "port", 1, 65535)
    result["list_id"] = _as_int(result["list_id"], "list_id", 0, 65535)

    if result["mode"] not in (MODE_READ, MODE_WRITE):
        raise vol.Invalid("mode musi być read lub write")

    for key in ("pack_variables", "on_change"):
        _as_bool(result, key)

    # Czasy: liczba (min_interval w ms, update_interval i timeout w s) albo tekst
    # z jednostką, np. "500ms", "5s", "2min", "1h"; "never"/0 wyłącza.
    result["min_interval"] = int(
        round(_as_duration(result["min_interval"], "min_interval", "ms") * 1000)
    )
    result["update_interval"] = _as_duration(
        result["update_interval"], "update_interval", "s"
    )
    result["timeout"] = _as_duration(result["timeout"], "timeout", "s")

    mode = result["mode"]
    packed = result["pack_variables"]

    if mode == MODE_WRITE and address.is_unspecified:
        raise vol.Invalid(
            "Dla listy write ip_address jest adresem docelowym i nie może "
            "być 0.0.0.0"
        )

    if mode == MODE_READ and address == ipaddress.IPv4Address("255.255.255.255"):
        raise vol.Invalid(
            "Dla listy read ip_address jest adresem nadawcy: 255.255.255.255 "
            "jest niedozwolony (0.0.0.0 akceptuje dowolnego nadawcę)"
        )

    # require_values dotyczy listy write pakowanej (cała lista jest wysyłana
    # jedną ramką); w liście niepakowanej służy require_value przy zmiennych.
    if "require_values" in result:
        _as_bool(result, "require_values")

        if mode == MODE_WRITE and not packed:
            raise vol.Invalid(
                "require_values dotyczy tylko list pakowanych; w liście "
                "niepakowanej użyj require_value przy zmiennych"
            )

    result.setdefault("require_values", DEFAULT_REQUIRE_VALUES)

    # Parametry niedotyczące danego trybu są ignorowane (ułatwia to
    # przełączanie trybu bez ręcznego czyszczenia konfiguracji).
    if mode != MODE_READ:
        result.pop("timeout", None)

    if mode != MODE_WRITE:
        result.pop("require_values", None)

    if not packed:
        result.pop("var_count", None)
        result.pop("payload_size", None)

    variables = result.get("variables")

    if not isinstance(variables, list) or not variables:
        raise vol.Invalid("Wymagana jest co najmniej jedna zmienna")

    result["variables"] = [validate_variable(item, mode) for item in variables]

    allowed = READ_ENTITIES if mode == MODE_READ else WRITE_ENTITIES

    for variable in result["variables"]:
        if variable["entity"] not in allowed:
            raise vol.Invalid(
                f"Lista {mode} może zawierać tylko encje: {', '.join(allowed)} "
                f"(zmienna {variable['name']})"
            )

    for variable in result["variables"]:
        if packed and variable.get("require_value"):
            raise vol.Invalid(
                f"require_value (zmienna {variable['name']}) dotyczy tylko list "
                "niepakowanych; w liście pakowanej użyj require_values listy"
            )

    _assign_unique_ids(result["variables"])
    _assign_offsets_and_indices(result["variables"], packed)
    _check_overlaps(result["variables"])

    needed = max(
        variable["offset"] + variable_size(variable)
        for variable in result["variables"]
    )

    if packed:
        payload_size = result.get("payload_size")

        if payload_size is not None:
            payload_size = _as_int(payload_size, "payload_size", 1)

            if payload_size < needed:
                raise vol.Invalid(
                    f"payload_size ({payload_size}) jest mniejszy niż rozmiar "
                    f"wynikający z offsetów zmiennych ({needed})"
                )

            result["payload_size"] = payload_size

        var_count = _as_int(
            result.get("var_count", len(result["variables"])),
            "var_count",
            1,
            65535,
        )

        if var_count < len(result["variables"]):
            raise vol.Invalid(
                "var_count nie może być mniejsze niż liczba zmiennych "
                "skonfigurowanych na liście"
            )

        result["var_count"] = var_count

    result["buffer_size"] = result.get("payload_size") or needed

    if result["buffer_size"] > MAX_PAYLOAD_SIZE:
        raise vol.Invalid(
            f"Rozmiar danych listy przekracza limit {MAX_PAYLOAD_SIZE} bajtów"
        )

    return result


def _assign_unique_ids(variables):
    """Ustala unique_id encji: podany ręcznie albo wyznaczony z nazwy zmiennej.

    Powtórzony identyfikator (także dwie nazwy dające ten sam slug) jest błędem.
    Identyfikator encji w Home Assistant zawiera dodatkowo adres, port, list_id i tryb listy.
    """
    used = {}

    for variable in variables:
        manual = "unique_id" in variable
        unique_id = variable["unique_id"] if manual else slugify(variable["name"])

        if not unique_id:
            raise vol.Invalid(
                f"Nie można wyznaczyć unique_id z nazwy '{variable['name']}': "
                "podaj unique_id ręcznie"
            )

        if unique_id in used:
            raise vol.Invalid(
                f"Powtórzony unique_id '{unique_id}' (zmienne '{used[unique_id]}' "
                f"i '{variable['name']}'); podaj unikalny unique_id ręcznie"
            )

        used[unique_id] = variable["name"]
        variable["unique_id"] = unique_id


def _assign_offsets_and_indices(variables, packed):
    """Uzupełnia offset i index oraz sprawdza ich spójność.

    Lista pakowana: offset jest wymagany, index nie jest używany.
    Lista niepakowana: index to numer zmiennej w liście PLC (domyślnie
    kolejna wolna liczba od 0), offset to tylko miejsce w buforze HA
    (domyślnie bezpośrednio za poprzednimi zmiennymi).
    """
    if packed:
        for variable in variables:
            if "offset" not in variable:
                raise vol.Invalid(
                    f"Brakujące pole zmiennej {variable['name']}: offset"
                )

            variable.pop("index", None)

        return

    used = set()

    for variable in variables:
        if "index" in variable:
            if variable["index"] in used:
                raise vol.Invalid(
                    f"Powtórzony index zmiennej: {variable['index']}"
                )

            used.add(variable["index"])

    next_offset = 0
    next_index = 0

    for variable in variables:
        if "offset" not in variable:
            variable["offset"] = next_offset

        next_offset = max(
            next_offset, variable["offset"] + variable_size(variable)
        )

        if "index" not in variable:
            while next_index in used:
                next_index += 1

            variable["index"] = next_index
            used.add(next_index)


def _check_overlaps(variables):
    ranges = []

    for variable in variables:
        start = variable["offset"]
        end = start + variable_size(variable)

        for other_start, other_end in ranges:
            if start < other_end and other_start < end:
                raise vol.Invalid(
                    f"Nakładający się offset zmiennej {variable['name']} "
                    f"przy {start}"
                )

        ranges.append((start, end))


# Poszczególne listy są walidowane osobno przy starcie (validate_device w
# _async_create_coordinator): błędna lista jest pomijana z komunikatem w logu,
# a pozostałe listy działają normalnie.
CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [dict])},
    extra=vol.ALLOW_EXTRA,
)

SEND_LIST_SCHEMA = vol.Schema(
    {
        vol.Required("list_id"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=65535)
        ),
        vol.Optional("ip_address"): cv.string,
    }
)


# --------------------------------------------------------------------------
# Komunikacja UDP
# --------------------------------------------------------------------------


class NetVarUDPProtocol(asyncio.DatagramProtocol):
    """Protokół UDP dla NetVar (używany przez hub portu i nadajnik)."""

    def __init__(self, owner):
        self.owner = owner

    def connection_made(self, transport):
        self.owner.transport = transport

    def datagram_received(self, data, addr):
        self.owner.handle_packet(data, addr)

    def error_received(self, exc):
        self.owner.handle_socket_error(exc)

    def connection_lost(self, exc):
        if exc:
            _LOGGER.warning("Połączenie NetVar UDP utracone: %s", exc)


class NetVarSender:
    """Jedno gniazdo wysyłające wspólne dla wszystkich list write.

    Gniazdo używa portu lokalnego przydzielonego przez system, więc listy write
    nie zajmują portów i nie kolidują z listami read na tym samym numerze portu
    (tak samo jak w wersji ESPHome).
    """

    RECENT_LIMIT = 64
    RECENT_TTL = 5.0

    def __init__(self, hass):
        self.hass = hass
        self.transport = None
        self.local_port = 0
        self.coordinators = {}
        self._sending = False
        self._send_failed = False
        # Ostatnio wysłane ramki (do rozpoznania własnego broadcastu, który wraca
        # do list read na tym samym hoście).
        self._recent = {}

    async def async_setup(self):
        loop = asyncio.get_running_loop()

        # allow_broadcast jest wymagane do wysyłki na 255.255.255.255.
        await loop.create_datagram_endpoint(
            lambda: NetVarUDPProtocol(self),
            local_addr=("0.0.0.0", 0),
            allow_broadcast=True,
        )
        self.local_port = self.transport.get_extra_info("sockname")[1]

    async def async_stop(self):
        if self.transport is not None:
            self.transport.close()
            self.transport = None

    def register(self, coordinator):
        key = (coordinator.ip_address, coordinator.port, coordinator.list_id)

        if key in self.coordinators:
            raise ValueError(f"Zduplikowana lista write NetVar: {key}")

        self.coordinators[key] = coordinator

    def unregister(self, coordinator):
        key = (coordinator.ip_address, coordinator.port, coordinator.list_id)
        self.coordinators.pop(key, None)

    def handle_packet(self, data, addr):
        """Nadajnik nie przetwarza odbieranych datagramów."""

    def handle_socket_error(self, exc):
        if self._sending:
            self._send_failed = True

        _LOGGER.error("Błąd wysyłania NetVar UDP: %s", exc)

    def sendto(self, data, address):
        """Wysyłanie danych UDP. Zwraca False, gdy wysyłka się nie powiodła."""
        if self.transport is None:
            _LOGGER.error("Transport NetVar UDP nie jest dostępny")
            return False

        # Błędy wysyłki asyncio zgłasza synchronicznie przez error_received.
        self._sending = True
        self._send_failed = False

        try:
            self.transport.sendto(data, address)
        except OSError as err:
            _LOGGER.error("Błąd wysyłania NetVar UDP do %s: %s", address, err)
            return False
        finally:
            self._sending = False

        if self._send_failed:
            return False

        self._remember(data)

        return True

    def _remember(self, data):
        now = time.monotonic()

        for key in [k for k, stamp in self._recent.items() if now - stamp > self.RECENT_TTL]:
            del self._recent[key]

        self._recent.pop(data, None)
        self._recent[data] = now

        while len(self._recent) > self.RECENT_LIMIT:
            del self._recent[next(iter(self._recent))]

    def is_own_frame(self, data, addr):
        """Czy datagram to własna, niedawno wysłana ramka (np. broadcast wracający do hosta)."""
        if self.local_port == 0 or addr[1] != self.local_port:
            return False

        stamp = self._recent.get(data)

        return stamp is not None and time.monotonic() - stamp <= self.RECENT_TTL


class NetVarPortHub:
    """Hub odbiorczy: jedno gniazdo UDP na port, współdzielone przez listy read."""

    def __init__(self, hass, port, sender):
        self.hass = hass
        self.port = port
        self.sender = sender
        self.transport = None
        self.coordinators = {}

    async def async_setup(self):
        """Otwarcie gniazda nasłuchującego; zgłasza OSError, gdy port jest zajęty."""
        loop = asyncio.get_running_loop()

        try:
            await loop.create_datagram_endpoint(
                lambda: NetVarUDPProtocol(self),
                local_addr=("0.0.0.0", self.port),
            )
        except OSError as err:
            raise OSError(
                f"Nie można otworzyć portu UDP {self.port}: {err}"
            ) from err

        _LOGGER.info("NetVar UDP nasłuchuje na porcie %d", self.port)

    async def async_stop(self):
        """Zatrzymanie gniazda UDP."""
        if self.transport is not None:
            self.transport.close()
            self.transport = None

    def register(self, coordinator):
        """Rejestracja koordynatora listy read w hubie."""
        key = (coordinator.ip_address, coordinator.list_id)

        if key in self.coordinators:
            raise ValueError(f"Zduplikowana lista read NetVar: {key}")

        self.coordinators[key] = coordinator

    def unregister(self, coordinator):
        key = (coordinator.ip_address, coordinator.list_id)
        self.coordinators.pop(key, None)

    def handle_socket_error(self, exc):
        """Obsługa błędu gniazda zgłoszonego przez asyncio."""
        _LOGGER.error("Błąd NetVar UDP (port %d): %s", self.port, exc)

        for coordinator in self.coordinators.values():
            coordinator.count("rx_errors")

    def handle_packet(self, data, addr):
        """Obsługa pakietu UDP odebranego na porcie huba.

        Zasady zliczania rejected_packets (takie same jak w wersji ESPHome):
        - ramka niemożliwa do zidentyfikowania (za krótka, zła sygnatura) albo
          o list_id, którego nie obsługuje żadna lista read tego portu, jest
          zliczana na wszystkich listach read portu,
        - ramka o list_id obsługiwanym przez listy tego portu, której żadna z
          nich nie przyjęła (zły nadawca, var_count, frame_size...), jest
          zliczana tylko na listach o tym list_id,
        - ramka przyjęta przez co najmniej jedną listę nie jest odrzucona
          (listy o tym samym list_id mogą różnić się adresem nadawcy).
        Walidacja portu docelowego jest niejawna: hub nasłuchuje na porcie listy.
        """
        # Własny broadcast wraca do list read na tym samym porcie: pomijamy go.
        if self.sender.is_own_frame(data, addr):
            return

        readers = list(self.coordinators.values())

        if not readers:
            return

        candidates = []

        if len(data) >= HEADER_SIZE and data[0:4] == MAGIC:
            list_id = int.from_bytes(data[8:10], "little")
            candidates = [c for c in readers if c.list_id == list_id]

        if not candidates:
            for coordinator in readers:
                coordinator.reject(
                    "Port %d: odebrano ramkę nieobsługiwaną przez żadną listę "
                    "read (zła sygnatura, długość lub list_id)",
                    self.port,
                    warn=False,
                )

            return

        accepted = False
        failures = []

        for coordinator in candidates:
            reason = coordinator.process_frame(addr[0], data)

            if reason is None:
                accepted = True
            else:
                failures.append((coordinator, reason))

        if accepted:
            return

        for coordinator, (message, args) in failures:
            coordinator.reject(message, *args)


class NetVarCoordinator:
    """Koordynator listy NetVar (odbiór i wysyłka)."""

    def __init__(self, hass, config, sender):
        self.hass = hass
        self.config = config
        self.sender = sender

        self.ip_address = config["ip_address"]
        self.port = config["port"]
        self.list_id = config["list_id"]
        self.mode = config["mode"]
        self.device_key = (
            f"{self.ip_address}_{self.port}_{self.list_id}_{self.mode}"
        )

        self.pack_variables = config["pack_variables"]
        self.on_change = config["on_change"]
        self.min_interval = config["min_interval"]
        self.update_interval = config["update_interval"]
        self.timeout = config.get("timeout", 0)
        self.require_values = config.get("require_values", False)

        self.variables = config["variables"]
        self.buffer_size = config["buffer_size"]

        # Liczba zmiennych w liście PLC (może być większa niż skonfigurowana).
        self.var_count = config.get("var_count", len(self.variables))
        # Gdy podano payload_size, ramka musi mieć dokładnie taki ładunek.
        self.exact_size = "payload_size" in config

        # Numer zmiennej w liście PLC -> pozycja w self.variables.
        self.index_map = (
            {}
            if self.pack_variables
            else {
                variable["index"]: position
                for position, variable in enumerate(self.variables)
            }
        )

        self.payload = bytearray(self.buffer_size)

        # Pozycja zmiennej -> czas (monotonic) ostatniego odbioru.
        self.last_received = {}
        self._expired = set()

        self.listeners = []
        self.diagnostic_listeners = []
        # sequence_counter (bajty 16-17): jeden na listę (pakowana) albo osobny dla każdej zmiennej (niepakowana)
        self.sequences = {}

        self.rx_packets = 0
        self.tx_packets = 0
        self.rx_errors = 0
        self.tx_errors = 0
        self.rejected_packets = 0

        # Stan wysyłki on_change. Jednostka wysyłki to cała lista (pakowana) albo pojedyncza zmienna (niepakowana):
        # każda ma własny czas ostatniej wysyłki (min_interval) i własny timer wysyłki zaległej.
        self.dirty = set()  # pozycje zmiennych zmienionych od ostatniej wysyłki
        self._last_sent = {}
        self._timers = {}
        self.startup_timer = None
        self.periodic_task = None
        self.watchdog_task = None
        self._diagnostic_handle = None
        self._last_warning = {}

        # Pozycje zmiennych, które mają wartość (lista write): podaną jawnie
        # initial_value, przywróconą po restarcie albo ustawioną w czasie pracy.
        self.has_value = set()

        if self.mode == MODE_WRITE:
            for position, variable in enumerate(self.variables):
                encoded = encode_value(
                    self._wire_value(variable, variable["initial_value"]),
                    variable["type"],
                    variable.get("length"),
                )

                offset = variable["offset"]
                self.payload[offset:offset + len(encoded)] = encoded

                if variable.get("initial_explicit"):
                    self.has_value.add(position)

    # --- słuchacze i liczniki ---------------------------------------------

    def register_listener(self, callback):
        if callback not in self.listeners:
            self.listeners.append(callback)

    def unregister_listener(self, callback):
        if callback in self.listeners:
            self.listeners.remove(callback)

    def register_diagnostic_listener(self, callback):
        if callback not in self.diagnostic_listeners:
            self.diagnostic_listeners.append(callback)

    def unregister_diagnostic_listener(self, callback):
        if callback in self.diagnostic_listeners:
            self.diagnostic_listeners.remove(callback)

    def notify(self, updated_indices):
        """Powiadomienie encji o zmianie danych lub dostępności."""
        data = bytes(self.payload)

        for callback in list(self.listeners):
            try:
                callback(data, set(updated_indices))
            except Exception:
                _LOGGER.exception(
                    "Błąd powiadamiania słuchacza NetVar dla listy %d",
                    self.list_id,
                )

    def count(self, name, amount=1):
        """Zwiększa licznik diagnostyczny i planuje odświeżenie sensorów."""
        setattr(self, name, getattr(self, name) + amount)

        if self._diagnostic_handle is None and self.diagnostic_listeners:
            self._diagnostic_handle = self.hass.loop.call_later(
                DIAGNOSTIC_REFRESH_INTERVAL, self._flush_diagnostics
            )

    def _flush_diagnostics(self):
        self._diagnostic_handle = None

        for callback in list(self.diagnostic_listeners):
            callback()

    def warn_throttled(self, key, message, *args):
        """Ostrzeżenie w logu, nie częściej niż raz na WARNING_INTERVAL."""
        now = time.monotonic()
        last = self._last_warning.get(key)

        if last is not None and now - last < WARNING_INTERVAL:
            return

        self._last_warning[key] = now
        _LOGGER.warning(
            message + " (powtórzenia są ograniczone do jednego na minutę)",
            *args,
        )

    def reject(self, message, *args, warn=True):
        """Odrzucenie ramki, która nie przeszła walidacji.

        warn=False: powód trafia tylko do logu debug (ruch obcych list).
        """
        self.count("rejected_packets")

        if warn:
            self.warn_throttled(message, message, *args)
        else:
            _LOGGER.debug(message, *args)

    # --- dostępność (timeout) ---------------------------------------------

    def is_available(self, position):
        """Czy zmienna odebrała dane i nie przekroczono timeout."""
        return position in self.last_received and position not in self._expired

    def _mark_received(self, positions):
        now = time.monotonic()

        if self._expired & positions:
            _LOGGER.info(
                "Lista %d: wznowiono odbiór danych z %s",
                self.list_id,
                self.ip_address,
            )
            self._expired -= positions

        for position in positions:
            self.last_received[position] = now

    async def _watchdog(self):
        """Oznacza zmienne jako niedostępne po przekroczeniu timeout."""
        interval = max(0.1, min(1.0, self.timeout / 2))

        while True:
            await asyncio.sleep(interval)

            now = time.monotonic()
            expired = {
                position
                for position, stamp in self.last_received.items()
                if position not in self._expired and now - stamp > self.timeout
            }

            if expired:
                self._expired |= expired
                _LOGGER.warning(
                    "Lista %d (%s): brak danych przez %s s - encje (%d) "
                    "oznaczone jako niedostępne",
                    self.list_id,
                    self.ip_address,
                    self.timeout,
                    len(expired),
                )
                self.notify(expired)

    # --- odbiór -----------------------------------------------------------

    def _handle_unpacked_frame(self, payload, variable_index, variable_count):
        """Zwraca (zbiór zaktualizowanych pozycji, None) albo (None, powód)."""
        if variable_count != 1:
            return None, (
                "Lista %d: ramka niepakowana ma var_count=%d, oczekiwano 1",
                (self.list_id, variable_count),
            )

        position = self.index_map.get(variable_index)

        if position is None:
            # Poprawna ramka zmiennej, której nie odczytujemy.
            _LOGGER.debug(
                "Lista %d: pominięto zmienną %d (brak w konfiguracji)",
                self.list_id,
                variable_index,
            )
            return set(), None

        variable = self.variables[position]
        size = variable_size(variable)

        if len(payload) != size:
            return None, (
                "Lista %d zmienna %d: długość ładunku %d, oczekiwano %d",
                (self.list_id, variable_index, len(payload), size),
            )

        offset = variable["offset"]
        self.payload[offset:offset + size] = payload

        return {position}, None

    def _handle_packed_frame(self, payload, variable_index, variable_count):
        """Zwraca (zbiór zaktualizowanych pozycji, None) albo (None, powód)."""
        if variable_index != 0:
            return None, (
                "Lista pakowana %d ma nieoczekiwany index %d",
                (self.list_id, variable_index),
            )

        if variable_count != self.var_count:
            return None, (
                "Lista pakowana %d ma var_count=%d, oczekiwano %d",
                (self.list_id, variable_count, self.var_count),
            )

        if self.exact_size:
            size_ok = len(payload) == self.buffer_size
        else:
            size_ok = len(payload) >= self.buffer_size

        if not size_ok:
            return None, (
                "Lista pakowana %d: długość ładunku %d, oczekiwano %s%d",
                (
                    self.list_id,
                    len(payload),
                    "" if self.exact_size else "co najmniej ",
                    self.buffer_size,
                ),
            )

        self.payload[:] = payload[:self.buffer_size]

        return set(range(len(self.variables))), None

    def process_frame(self, sender_ip, data):
        """Walidacja i dekodowanie ramki dla tej listy.

        Zwraca None, gdy ramka została przyjęta (i zdekodowana), albo krotkę
        (komunikat, argumenty) z powodem odrzucenia. Pola sequence (bajty 16-17)
        i checksum (18-19) są tylko odczytywane (log debug), nie są walidowane.
        """
        if self.mode != MODE_READ:
            return ("Lista %d nie jest listą read", (self.list_id,))

        # 0.0.0.0 = akceptuj dowolnego nadawcę.
        if self.ip_address != "0.0.0.0" and self.ip_address != sender_ip:
            return (
                "Lista %d: ramka od nieoczekiwanego nadawcy %s (oczekiwano %s)",
                (self.list_id, sender_ip, self.ip_address),
            )

        # Typ wiadomości (bajty 4-7; w dokumentacji 3S pole "ID"): 0 = dane zmiennych sieciowych.
        # Inne wartości to potwierdzenia, prośby bootup i wymiana parametrów (SDO).
        message_type = int.from_bytes(data[4:8], "little")

        if message_type != 0:
            return (
                "Lista %d: ramka o typie wiadomości %d (to nie dane zmiennych: "
                "potwierdzenie, prośba bootup albo SDO)",
                (self.list_id, message_type),
            )

        total_length = int.from_bytes(data[14:16], "little")

        if total_length != len(data):
            return (
                "Lista %d: nieprawidłowa długość ramki: nagłówek=%d "
                "rzeczywista=%d",
                (self.list_id, total_length, len(data)),
            )

        variable_index = int.from_bytes(data[10:12], "little")
        variable_count = int.from_bytes(data[12:14], "little")
        sequence = int.from_bytes(data[16:18], "little")
        payload = data[HEADER_SIZE:]

        if self.pack_variables:
            updated, reason = self._handle_packed_frame(
                payload, variable_index, variable_count
            )
        else:
            updated, reason = self._handle_unpacked_frame(
                payload, variable_index, variable_count
            )

        if reason is not None:
            return reason

        _LOGGER.debug(
            "RX %s lista=%d index=%d count=%d sequence=%d "
            "bajty_naglowka_18_19=%02X %02X ładunek=%s",
            sender_ip,
            self.list_id,
            variable_index,
            variable_count,
            sequence,
            data[18],
            data[19],
            payload.hex(),
        )

        self.count("rx_packets")

        if updated:
            self._mark_received(updated)
            self.notify(updated)

        return None

    # --- wysyłka ----------------------------------------------------------

    def _position(self, variable):
        return next(
            position
            for position, item in enumerate(self.variables)
            if item is variable
        )

    @staticmethod
    def _wire_value(variable, value):
        """Wartość BOOL zmiennej z inverted: do PLC trafia negacja wartości logicznej encji."""
        if variable.get("inverted") and variable["type"] == "BOOL":
            return not to_bool(value)

        return value

    def set_variable(self, variable, value, restore=False):
        """Ustawienie wartości zmiennej w buforze i zaplanowanie wysyłki przy zmianie.

        Wysyłka on_change następuje tylko wtedy, gdy wartość się zmieniła (albo zmienna dostaje
        pierwszą wartość). Lista pakowana wysyła wtedy całą listę, niepakowana tylko tę zmienną.

        restore=True: wartość przywrócona po restarcie. Trafia do bufora i oznacza
        zmienną jako mającą wartość, ale nie uruchamia wysyłki (patrz
        schedule_startup_send, która wysyła listę jednokrotnie po przywróceniu).
        """
        if self.mode != MODE_WRITE:
            raise ValueError("Nie można zapisać do listy tylko do odczytu")

        value = self._wire_value(variable, value)
        encoded = encode_value(value, variable["type"], variable.get("length"))
        offset = variable["offset"]

        if variable["type"] == STRING_TYPE:
            text = value if isinstance(value, str) else number_to_text(value)

            if len(text) > variable["length"]:
                self.warn_throttled(
                    ("truncate", variable["name"]),
                    "Lista %d: wartość zmiennej %s ucięta do %d znaków",
                    self.list_id,
                    variable["name"],
                    variable["length"],
                )

        position = self._position(variable)
        changed = bytes(self.payload[offset:offset + len(encoded)]) != encoded
        first_value = position not in self.has_value

        self.payload[offset:offset + len(encoded)] = encoded
        self.has_value.add(position)

        if restore or not self.on_change or not (changed or first_value):
            return

        self.dirty.add(position)
        self._request_send(self._unit(position))

    def _unit(self, position):
        return LIST_KEY if self.pack_variables else position

    def _units(self):
        if self.pack_variables:
            return [LIST_KEY]

        return list(range(len(self.variables)))

    def schedule_startup_send(self):
        """Jednorazowa wysyłka po przywróceniu stanu encji (z krótkim opóźnieniem).

        Opóźnienie pozwala przywrócić wszystkie encje listy i wysłać jedną ramkę
        zamiast kilku z wartościami częściowymi. Nie dotyczy listy, która nie jest
        wysyłana automatycznie (on_change wyłączone i update_interval równe 0).
        """
        if not self.on_change and self.update_interval <= 0:
            return

        if self.startup_timer is not None:
            self.startup_timer.cancel()

        self.startup_timer = asyncio.get_running_loop().call_later(
            STARTUP_SEND_DELAY, self._startup_send
        )

    def _startup_send(self):
        self.startup_timer = None
        self._send_everything()

    def _request_send(self, unit):
        """Wysyłka zmiany z uwzględnieniem min_interval danej jednostki (listy albo zmiennej).

        Pierwsza wysyłka nie jest ograniczona. Zmiana przed upływem min_interval jest
        wysyłana dopiero po jego upływie, a zmiany w tym czasie są scalane w jedną ramkę.
        """
        last = self._last_sent.get(unit)
        wait = 0.0

        if last is not None:
            wait = last + self.min_interval / 1000.0 - time.monotonic()

        if wait <= 0:
            self._flush(unit)
        elif unit not in self._timers:
            self._timers[unit] = asyncio.get_running_loop().call_later(
                wait, self._flush_timer, unit
            )

    def _flush_timer(self, unit):
        self._timers.pop(unit, None)
        self._flush(unit)

    def _flush(self, unit):
        """Wysyła jednostkę, jeśli ma niewysłane zmiany."""
        if self.pack_variables:
            pending = bool(self.dirty)
        else:
            pending = unit in self.dirty

        if pending:
            self._send_unit(unit)

    def send_now(self):
        """Natychmiastowa wysyłka całej listy (usługa send_list)."""
        self._send_everything()

    def _send_everything(self):
        """Wysyłka cykliczna, na żądanie i startowa: cała lista albo wszystkie zmienne (niepakowana)."""
        if self.mode != MODE_WRITE:
            return

        for timer in self._timers.values():
            timer.cancel()

        self._timers.clear()

        for unit in self._units():
            self._send_unit(unit)

    def _missing_names(self):
        """Nazwy zmiennych, które nie mają jeszcze wartości."""
        return [
            variable["name"]
            for position, variable in enumerate(self.variables)
            if position not in self.has_value
        ]

    def _send_unit(self, unit):
        """Wysyła jedną jednostkę: całą listę (pakowana) albo jedną zmienną (niepakowana).

        require_values (lista pakowana): lista nie jest wysyłana, dopóki każda
        zmienna nie dostała wartości. require_value (lista niepakowana): ramka
        zmiennej bez wartości jest pomijana.
        """
        if self.mode != MODE_WRITE:
            return

        if self.pack_variables:
            if self.require_values and len(self.has_value) < len(self.variables):
                self.warn_throttled(
                    ("require_values", self.list_id),
                    "Lista %d: nie wysłano, zmienne bez wartości: %s",
                    self.list_id,
                    ", ".join(self._missing_names()),
                )
                return

            ok = self._transmit(
                self.build_packet(bytes(self.payload), 0, self.var_count, unit)
            )
            positions = set(range(len(self.variables)))
        else:
            variable = self.variables[unit]

            if variable.get("require_value") and unit not in self.has_value:
                self.warn_throttled(
                    ("require_value", unit),
                    "Lista %d: nie wysłano zmiennej %s (brak wartości)",
                    self.list_id,
                    variable["name"],
                )
                return

            offset = variable["offset"]
            size = variable_size(variable)
            ok = self._transmit(
                self.build_packet(
                    bytes(self.payload[offset:offset + size]),
                    variable["index"],
                    1,
                    unit,
                )
            )
            positions = {unit}

        # Czas zapisujemy także przy błędzie: nieudana wysyłka jest ponawiana najwyżej raz na min_interval.
        self._last_sent[unit] = time.monotonic()

        if ok:
            self.dirty -= positions
        elif self.dirty & positions and unit not in self._timers:
            self._timers[unit] = asyncio.get_running_loop().call_later(
                max(self.min_interval / 1000.0, 1.0), self._flush_timer, unit
            )

    def _transmit(self, packet):
        """Transmisja pakietu UDP i aktualizacja liczników."""
        if not self.sender.sendto(packet, (self.ip_address, self.port)):
            self.count("tx_errors")
            _LOGGER.error(
                "Błąd TX PLC=%s:%d lista=%d",
                self.ip_address,
                self.port,
                self.list_id,
            )
            return False

        self.count("tx_packets")

        _LOGGER.debug(
            "TX PLC=%s:%d lista=%d pakowane=%s ładunek=%s",
            self.ip_address,
            self.port,
            self.list_id,
            self.pack_variables,
            packet[HEADER_SIZE:].hex(),
        )

        return True

    async def _periodic_send(self):
        """Cykliczne wysyłanie listy co update_interval sekund."""
        while True:
            await asyncio.sleep(self.update_interval)

            try:
                self._send_everything()
            except Exception:
                _LOGGER.exception(
                    "Błąd cyklicznej wysyłki listy %d", self.list_id
                )

    async def async_start(self):
        """Uruchomienie zadań w tle (wysyłka cykliczna, kontrola timeout)."""
        if self.mode == MODE_WRITE and self.update_interval > 0:
            self.periodic_task = asyncio.create_task(self._periodic_send())

        if self.mode == MODE_READ and self.timeout > 0:
            self.watchdog_task = asyncio.create_task(self._watchdog())

    async def async_stop(self):
        """Zatrzymanie timerów i zadań w tle."""
        for timer in self._timers.values():
            timer.cancel()

        self._timers.clear()

        if self.startup_timer is not None:
            self.startup_timer.cancel()
            self.startup_timer = None

        if self._diagnostic_handle is not None:
            self._diagnostic_handle.cancel()
            self._diagnostic_handle = None

        for attribute in ("periodic_task", "watchdog_task"):
            task = getattr(self, attribute)

            if task is not None:
                task.cancel()
                setattr(self, attribute, None)

    def build_packet(self, payload, variable_index, variable_count, unit=LIST_KEY):
        """Budowa ramki NetVar UDP z nagłówkiem i ładunkiem."""
        header = bytearray(HEADER_SIZE)

        header[0:4] = MAGIC
        header[8:10] = self.list_id.to_bytes(2, "little")
        header[10:12] = variable_index.to_bytes(2, "little")
        header[12:14] = variable_count.to_bytes(2, "little")
        header[14:16] = (HEADER_SIZE + len(payload)).to_bytes(2, "little")
        sequence = self.sequences.get(unit, 1)
        header[16:18] = sequence.to_bytes(2, "little")

        # Flagi i suma kontrolna (bajty 18-19) zawsze 00 00: algorytm sumy
        # kontrolnej jest nieznany, więc nie jest generowany. Lista odbiorcza
        # w PLC musi mieć wyłączone sprawdzanie sumy kontrolnej.
        header[18:20] = b"\x00\x00"

        self.sequences[unit] = (sequence + 1) & 0xFFFF

        return bytes(header) + payload


# --------------------------------------------------------------------------
# Uruchamianie i zatrzymywanie
# --------------------------------------------------------------------------


async def _async_create_coordinator(hass, config):
    """Tworzenie i uruchomienie koordynatora na podstawie konfiguracji.

    Zgłasza vol.Invalid (zła konfiguracja), ValueError (duplikat listy)
    albo OSError (port UDP niedostępny dla listy read).
    """
    config = validate_device(config)

    runtime = hass.data.setdefault(DOMAIN, {})
    hubs = runtime.setdefault("hubs", {})
    runtime.setdefault("devices", {})

    sender = runtime.get("sender")

    if sender is None:
        sender = NetVarSender(hass)
        await sender.async_setup()
        runtime["sender"] = sender

    port = config["port"]
    created_hub = None

    if config["mode"] == MODE_READ:
        hub = hubs.get(port)

        if hub is None:
            hub = NetVarPortHub(hass, port, sender)
            await hub.async_setup()
            hubs[port] = hub
            created_hub = hub

        registry = hub
    else:
        registry = sender

    coordinator = NetVarCoordinator(hass, config, sender)

    try:
        registry.register(coordinator)
    except ValueError:
        if created_hub is not None:
            await created_hub.async_stop()
            hubs.pop(port, None)

        raise

    await coordinator.async_start()

    return coordinator


async def _async_stop_all(hass):
    """Zatrzymanie wszystkich list, hubów i nadajnika (np. przy zamykaniu HA)."""
    runtime = hass.data.get(DOMAIN, {})

    for device in runtime.get("devices", {}).values():
        await device["coordinator"].async_stop()

    for hub in runtime.get("hubs", {}).values():
        await hub.async_stop()

    sender = runtime.get("sender")

    if sender is not None:
        await sender.async_stop()


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Integracja z konfiguracji YAML (oraz zadania wspólne dla wpisów)."""
    runtime = hass.data.setdefault(DOMAIN, {})
    runtime.setdefault("hubs", {})
    runtime.setdefault("devices", {})

    async def _async_on_stop(_event):
        await _async_stop_all(hass)

    async def _async_send_list(call: ServiceCall):
        list_id = call.data["list_id"]
        ip_address = call.data.get("ip_address")
        sent = 0

        for device in runtime["devices"].values():
            coordinator = device["coordinator"]

            if (
                coordinator.mode == MODE_WRITE
                and coordinator.list_id == list_id
                and ip_address in (None, coordinator.ip_address)
            ):
                coordinator.send_now()
                sent += 1

        if not sent:
            raise ServiceValidationError(
                f"Nie znaleziono listy write o list_id={list_id}"
            )

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_on_stop)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_LIST,
        _async_send_list,
        schema=SEND_LIST_SCHEMA,
    )

    if DOMAIN not in config:
        return True

    platforms = set()

    for number, raw_config in enumerate(config[DOMAIN], start=1):
        try:
            coordinator = await _async_create_coordinator(hass, raw_config)
        except (OSError, ValueError, vol.Invalid) as err:
            _LOGGER.error(
                "Nie można uruchomić listy YAML nr %d: %s", number, err
            )
            continue

        key = (
            f"yaml_{number}_{coordinator.ip_address}_"
            f"{coordinator.port}_{coordinator.list_id}"
        )

        runtime["devices"][key] = {
            "coordinator": coordinator,
            "source": "yaml",
        }

        for variable in coordinator.variables:
            platforms.add(variable["entity"])

        # Sensory diagnostyczne są zawsze tworzone, więc platforma sensor
        # jest wymagana niezależnie od trybu listy.
        platforms.add("sensor")

    for platform in platforms:
        hass.async_create_task(
            discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
        )

    return True
