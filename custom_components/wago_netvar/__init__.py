
import asyncio
import ipaddress
import logging
import time

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    DEFAULT_ON_CHANGE,
    DEFAULT_MIN_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    MAGIC,
    HEADER_SIZE,
    MODE_READ,
    MODE_WRITE,
    SUPPORTED_TYPES,
    READ_ENTITIES,
    WRITE_ENTITIES,
)
from .codec import (
    encode_value,
    normalize_type,
    string_length,
    variable_size,
)

_LOGGER = logging.getLogger(__name__)


def validate_variable(variable):
    if not isinstance(variable, dict):
        raise vol.Invalid("Variable definition must be a dictionary")

    required = ("name", "offset", "type", "entity")

    for key in required:
        if key not in variable:
            raise vol.Invalid(f"Missing variable field: {key}")

    result = dict(variable)
    result["name"] = str(result["name"]).strip()

    if not result["name"]:
        raise vol.Invalid("Variable name cannot be empty")

    if isinstance(result["offset"], bool):
        raise vol.Invalid("Variable offset must be an integer")

    try:
        offset = int(result["offset"])
    except (TypeError, ValueError, OverflowError):
        raise vol.Invalid("Variable offset must be an integer")

    if isinstance(result["offset"], float) and not result["offset"].is_integer():
        raise vol.Invalid("Variable offset must be an integer")

    if offset < 0:
        raise vol.Invalid("Variable offset cannot be negative")

    result["offset"] = offset
    result["type"] = normalize_type(result["type"])
    result["entity"] = str(result["entity"])

    if result["type"] not in SUPPORTED_TYPES:
        raise vol.Invalid(
            f"Unsupported variable type: {result['type']}"
        )

    if result["entity"] not in READ_ENTITIES + WRITE_ENTITIES:
        raise vol.Invalid(
            f"Unsupported entity type: {result['entity']}"
        )

    if result["type"] == "BOOL":
        if result["entity"] not in ("binary_sensor", "switch"):
            raise vol.Invalid(
                "BOOL must use binary_sensor or switch"
            )
    elif result["entity"] in ("binary_sensor", "switch"):
        raise vol.Invalid(
            "Only BOOL can use binary_sensor or switch"
        )

    if result["type"] == "STRING":
        if result["entity"] != "sensor":
            raise vol.Invalid("STRING can only use sensor")

        try:
            result["length"] = string_length(result.get("length"))
        except ValueError as err:
            raise vol.Invalid(str(err)) from err
    else:
        result.pop("length", None)

    if result["type"] == "BOOL":
        default_initial_value = False
    elif result["type"] == "STRING":
        default_initial_value = ""
    else:
        default_initial_value = 0

    result.setdefault("initial_value", default_initial_value)
    result.setdefault("enabled_by_default", True)
    result.setdefault("force_update", False)

    if result["entity"] == "sensor":
        result.setdefault("zero_as_unavailable", False)

    if result["entity"] == "number":
        result.setdefault("min", 0)
        result.setdefault("max", 100)
        result.setdefault("step", 1)

        try:
            result["min"] = float(result["min"])
            result["max"] = float(result["max"])
            result["step"] = float(result["step"])
        except (TypeError, ValueError, OverflowError):
            raise vol.Invalid("Invalid number min/max/step")

        if result["min"] >= result["max"]:
            raise vol.Invalid("Number min must be lower than max")

        if result["step"] <= 0:
            raise vol.Invalid("Number step must be positive")

        try:
            initial_value = float(result["initial_value"])

            if not result["min"] <= initial_value <= result["max"]:
                raise ValueError(
                    "initial_value is outside number min/max"
                )
        except (ValueError, TypeError, OverflowError) as err:
            raise vol.Invalid(
                f"Invalid initial_value for {result['name']}: {err}"
            )

    return result


def validate_device(device):
    if not isinstance(device, dict):
        raise vol.Invalid("Device configuration must be a dictionary")

    result = dict(device)

    try:
        result["ip_address"] = str(result["ip_address"])
        ipaddress.ip_address(result["ip_address"])
    except (KeyError, ValueError):
        raise vol.Invalid("Invalid ip_address")

    result.setdefault("port", DEFAULT_PORT)
    result.setdefault("mode", MODE_READ)
    result.setdefault("pack_variables", True)
    result.setdefault("on_change", DEFAULT_ON_CHANGE)
    result.setdefault("min_interval", DEFAULT_MIN_INTERVAL)
    result.setdefault("update_interval", DEFAULT_UPDATE_INTERVAL)

    # transmit_checksum was removed: the checksum algorithm is unknown.
    legacy_transmit_checksum = result.pop("transmit_checksum", False)

    try:
        result["port"] = int(result["port"])
        result["list_id"] = int(result["list_id"])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise vol.Invalid("port and list_id must be integers")

    if not 1 <= result["port"] <= 65535:
        raise vol.Invalid("port must be between 1 and 65535")

    if not 0 <= result["list_id"] <= 65535:
        raise vol.Invalid("list_id must be between 0 and 65535")

    if result["mode"] not in (MODE_READ, MODE_WRITE):
        raise vol.Invalid("mode must be read or write")

    if not isinstance(result["pack_variables"], bool):
        raise vol.Invalid("pack_variables must be boolean")

    if not isinstance(result["on_change"], bool):
        raise vol.Invalid("on_change must be boolean")

    try:
        result["min_interval"] = int(result["min_interval"])
        result["update_interval"] = int(result["update_interval"])
    except (TypeError, ValueError, OverflowError):
        raise vol.Invalid("min_interval and update_interval must be integers")

    if result["min_interval"] < 0:
        raise vol.Invalid("min_interval must be >= 0")

    if result["update_interval"] < 0:
        raise vol.Invalid("update_interval must be >= 0")

    if legacy_transmit_checksum is True and result["mode"] == MODE_WRITE:
        raise vol.Invalid(
            "transmit_checksum is no longer supported. Remove it and "
            "disable checksum checking on the PLC receive list"
        )

    variables = result.get("variables")

    if not isinstance(variables, list) or not variables:
        raise vol.Invalid("At least one variable is required")

    result["variables"] = [
        validate_variable(item) for item in variables
    ]

    for variable in result["variables"]:
        if result["mode"] == MODE_READ:
            if variable["entity"] not in READ_ENTITIES:
                raise vol.Invalid(
                    "Read lists can only contain sensor and binary_sensor"
                )
        else:
            if variable["entity"] not in WRITE_ENTITIES:
                raise vol.Invalid(
                    "Write lists can only contain switch and number"
                )

    ranges = []

    for variable in result["variables"]:
        start = variable["offset"]
        end = start + variable_size(variable)

        for other_start, other_end in ranges:
            if start < other_end and other_start < end:
                raise vol.Invalid(
                    f"Overlapping variable offset at {start}"
                )

        ranges.append((start, end))

    result["buffer_size"] = max(
        variable["offset"] + variable_size(variable)
        for variable in result["variables"]
    )

    return result


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            cv.ensure_list,
            [vol.All(dict, validate_device)],
        )
    },
    extra=vol.ALLOW_EXTRA,
)


class NetVarUDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, hub):
        self.hub = hub

    def connection_made(self, transport):
        self.hub.transport = transport

    def datagram_received(self, data, addr):
        self.hub.handle_packet(data, addr)

    def error_received(self, exc):
        _LOGGER.error("NetVar UDP error: %s", exc)

    def connection_lost(self, exc):
        if exc:
            _LOGGER.warning("NetVar UDP connection lost: %s", exc)


class NetVarPortHub:
    def __init__(self, hass, port):
        self.hass = hass
        self.port = port
        self.transport = None
        self.protocol = None
        self.coordinators = {}

    async def async_setup(self):
        loop = asyncio.get_running_loop()

        self.transport, self.protocol = (
            await loop.create_datagram_endpoint(
                lambda: NetVarUDPProtocol(self),
                local_addr=("0.0.0.0", self.port),
            )
        )

        _LOGGER.info(
            "NetVar UDP listening on port %d",
            self.port,
        )

    async def async_stop(self):
        if self.transport is not None:
            self.transport.close()
            self.transport = None
            self.protocol = None

    def register(self, coordinator):
        key = (coordinator.ip_address, coordinator.list_id)

        if key in self.coordinators:
            raise ValueError(
                f"Duplicate NetVar list configuration: {key}"
            )

        self.coordinators[key] = coordinator

    def unregister(self, coordinator):
        key = (coordinator.ip_address, coordinator.list_id)
        self.coordinators.pop(key, None)

    def sendto(self, data, address):
        if self.transport is None:
            _LOGGER.error("NetVar UDP transport is not available")
            return False

        self.transport.sendto(data, address)
        return True

    def _find_coordinator(self, ip, list_id):
        for coordinator in self.coordinators.values():
            if coordinator.list_id == list_id and (
                coordinator.ip_address == "0.0.0.0"
                or coordinator.ip_address == ip
            ):
                return coordinator
        return None

    def handle_packet(self, data, addr):
        if len(data) < HEADER_SIZE:
            return

        if data[0:4] != MAGIC:
            return

        list_id = int.from_bytes(data[8:10], "little")
        variable_index = int.from_bytes(data[10:12], "little")
        variable_count = int.from_bytes(data[12:14], "little")
        total_length = int.from_bytes(data[14:16], "little")
        sequence = int.from_bytes(data[16:18], "little")
        checksum = int.from_bytes(data[18:20], "little")

        coordinator = self._find_coordinator(addr[0], list_id)

        if coordinator is None:
            _LOGGER.debug(
                "No configuration for PLC %s list %d",
                addr[0],
                list_id,
            )
            return

        if total_length != len(data):
            coordinator.rejected_packets += 1
            coordinator.rx_errors += 1
            _LOGGER.warning(
                "Invalid packet length: header=%d actual=%d",
                total_length,
                len(data),
            )
            return

        payload = data[HEADER_SIZE:]

        _LOGGER.debug(
            "RX %s:%d list=%d index=%d count=%d "
            "sequence=%d header_bytes_18_19=%02X %02X payload=%s",
            addr[0],
            self.port,
            list_id,
            variable_index,
            variable_count,
            sequence,
            checksum & 0xFF,
            checksum >> 8,
            payload.hex(),
        )

        coordinator.rx_packets += 1
        coordinator.handle_packet(
            payload=payload,
            variable_index=variable_index,
            variable_count=variable_count,
            sequence=sequence,
            checksum=checksum,
        )


class NetVarCoordinator:
    def __init__(self, hass, config, hub):
        self.hass = hass
        self.config = config
        self.hub = hub

        self.ip_address = config["ip_address"]
        self.port = config["port"]
        self.list_id = config["list_id"]
        self.mode = config["mode"]

        self.pack_variables = config["pack_variables"]
        self.on_change = config["on_change"]
        self.min_interval = config["min_interval"]
        self.update_interval = config["update_interval"]

        self.variables = config["variables"]
        self.buffer_size = config["buffer_size"]

        self.payload = bytearray(self.buffer_size)

        # Variables received at least once.
        self.received = set()

        self.last_checksum = 0

        self.listeners = []
        self.tx_sequence = 0

        self.rx_packets = 0
        self.tx_packets = 0
        self.rx_errors = 0
        self.tx_errors = 0
        self.rejected_packets = 0

        self.last_send_time = 0.0
        self.send_timer = None
        self.periodic_task = None

        if self.mode == MODE_WRITE:
            for variable in self.variables:
                encoded = encode_value(
                    variable["initial_value"],
                    variable["type"],
                    variable.get("length"),
                )

                offset = variable["offset"]
                self.payload[offset:offset + len(encoded)] = encoded

    @property
    def expected_count(self):
        return len(self.variables)

    def register_listener(self, callback):
        if callback not in self.listeners:
            self.listeners.append(callback)

    def unregister_listener(self, callback):
        if callback in self.listeners:
            self.listeners.remove(callback)

    def notify(self, updated_indices=None):
        data = bytes(self.payload)

        if updated_indices is None:
            updated_indices = set(range(len(self.variables)))

        for callback in list(self.listeners):
            try:
                callback(data, set(updated_indices))
            except Exception:
                _LOGGER.exception(
                    "Error notifying NetVar listener for list %d",
                    self.list_id,
                )

    def _handle_unpacked_packet(
        self,
        payload,
        variable_index,
        variable_count,
        sequence,
        checksum,
    ):
        if variable_count != 1:
            self.rejected_packets += 1
            self.rx_errors += 1
            _LOGGER.debug(
                "Unpacked packet has variable_count=%d, expected 1",
                variable_count,
            )
            return

        if not 0 <= variable_index < len(self.variables):
            self.rejected_packets += 1
            self.rx_errors += 1
            _LOGGER.warning(
                "Invalid variable index %d for list %d",
                variable_index,
                self.list_id,
            )
            return

        variable = self.variables[variable_index]
        size = variable_size(variable)

        if len(payload) != size:
            self.rejected_packets += 1
            self.rx_errors += 1
            _LOGGER.warning(
                "List %d variable %d payload length %d, expected %d",
                self.list_id,
                variable_index,
                len(payload),
                size,
            )
            return

        offset = variable["offset"]
        self.payload[offset:offset + size] = payload

        self.received.add(variable_index)
        self.last_checksum = checksum

        # Publish immediately after every valid frame.
        self.notify({variable_index})

        _LOGGER.debug(
            "List %d: received variable %d",
            self.list_id,
            variable_index,
        )

    def _handle_packed_packet(
        self,
        payload,
        variable_index,
        variable_count,
        sequence,
        checksum,
    ):
        if variable_index != 0:
            self.rejected_packets += 1
            self.rx_errors += 1
            _LOGGER.warning(
                "Packed list %d has unexpected index %d",
                self.list_id,
                variable_index,
            )
            return

        if variable_count != len(self.variables):
            self.rejected_packets += 1
            self.rx_errors += 1
            _LOGGER.warning(
                "Packed list %d has count %d, expected %d",
                self.list_id,
                variable_count,
                len(self.variables),
            )
            return

        if len(payload) != self.buffer_size:
            self.rejected_packets += 1
            self.rx_errors += 1
            _LOGGER.warning(
                "Packed list %d payload length %d, expected %d",
                self.list_id,
                len(payload),
                self.buffer_size,
            )
            return

        self.payload[:] = payload

        all_indices = set(range(len(self.variables)))
        self.received = set(all_indices)
        self.last_checksum = checksum

        self.notify(all_indices)

    def handle_packet(
        self,
        payload,
        variable_index,
        variable_count,
        sequence,
        checksum=0,
    ):
        if self.mode != MODE_READ:
            return

        if self.pack_variables:
            self._handle_packed_packet(
                payload,
                variable_index,
                variable_count,
                sequence,
                checksum,
            )
        else:
            self._handle_unpacked_packet(
                payload,
                variable_index,
                variable_count,
                sequence,
                checksum,
            )

    def set_variable(self, variable, value):
        if self.mode != MODE_WRITE:
            raise ValueError("Cannot write to a read-only list")

        encoded = encode_value(
            value,
            variable["type"],
            variable.get("length"),
        )
        offset = variable["offset"]

        self.payload[offset:offset + len(encoded)] = encoded

        self._schedule_send()

    def _schedule_send(self):
        if not self.on_change:
            return

        now = time.monotonic()

        if self.min_interval <= 0:
            self._send_all()
            return

        elapsed = now - self.last_send_time

        if elapsed >= self.min_interval / 1000.0:
            self._send_all()
        else:
            if self.send_timer is not None:
                self.send_timer.cancel()

            delay = (self.min_interval / 1000.0) - elapsed
            loop = asyncio.get_running_loop()
            self.send_timer = loop.call_later(delay, self._send_all)

    def _send_all(self):
        if self.mode != MODE_WRITE:
            return

        if self.pack_variables:
            packet = self.build_packet(
                bytes(self.payload),
                0,
                len(self.variables),
            )
            self._transmit(packet)
        else:
            for index, variable in enumerate(self.variables):
                offset = variable["offset"]
                size = variable_size(variable)

                value = bytes(
                    self.payload[offset:offset + size]
                )

                packet = self.build_packet(
                    value,
                    index,
                    1,
                )
                self._transmit(packet)

        self.last_send_time = time.monotonic()

    def _transmit(self, packet):
        sent = self.hub.sendto(
            packet,
            (self.ip_address, self.port),
        )

        if not sent:
            self.tx_errors += 1
            _LOGGER.error(
                "TX failed PLC=%s:%d list=%d",
                self.ip_address,
                self.port,
                self.list_id,
            )
            return

        self.tx_packets += 1

        _LOGGER.info(
            "TX PLC=%s:%d list=%d packed=%s payload=%s",
            self.ip_address,
            self.port,
            self.list_id,
            self.pack_variables,
            packet[HEADER_SIZE:].hex(),
        )

    async def _periodic_send(self):
        while True:
            await asyncio.sleep(self.update_interval)
            if self.mode == MODE_WRITE:
                self._send_all()

    async def async_start(self):
        if self.mode == MODE_WRITE and self.update_interval > 0:
            self.periodic_task = asyncio.create_task(
                self._periodic_send()
            )

    async def async_stop(self):
        if self.send_timer is not None:
            self.send_timer.cancel()
            self.send_timer = None

        if self.periodic_task is not None:
            self.periodic_task.cancel()
            self.periodic_task = None

    def build_packet(self, payload, variable_index, variable_count):
        header = bytearray(HEADER_SIZE)

        header[0:4] = MAGIC
        header[8:10] = self.list_id.to_bytes(2, "little")
        header[10:12] = variable_index.to_bytes(2, "little")
        header[12:14] = variable_count.to_bytes(2, "little")

        header[14:16] = (
            HEADER_SIZE + len(payload)
        ).to_bytes(2, "little")

        header[16:18] = self.tx_sequence.to_bytes(2, "little")

        # Flags and checksum (bytes 18-19) are always 00 00: the checksum
        # algorithm is unknown, so it is not generated. The PLC receive
        # list must have checksum checking disabled.
        header[18:20] = b"\x00\x00"

        self.tx_sequence = (self.tx_sequence + 1) & 0xFFFF

        return bytes(header) + payload


async def _async_create_coordinator(hass, config):
    config = validate_device(config)

    runtime = hass.data.setdefault(DOMAIN, {})
    hubs = runtime.setdefault("hubs", {})
    runtime.setdefault("devices", {})

    port = config["port"]

    if port not in hubs:
        hub = NetVarPortHub(hass, port)
        await hub.async_setup()
        hubs[port] = hub
    else:
        hub = hubs[port]

    coordinator = NetVarCoordinator(hass, config, hub)

    try:
        hub.register(coordinator)
    except ValueError:
        if not hub.coordinators:
            await hub.async_stop()
            hubs.pop(port, None)
        raise

    await coordinator.async_start()

    return coordinator


async def _async_stop_all(hass, _event):
    runtime = hass.data.get(DOMAIN, {})

    for hub in runtime.get("hubs", {}).values():
        await hub.async_stop()


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    runtime = hass.data.setdefault(DOMAIN, {})
    runtime.setdefault("hubs", {})
    runtime.setdefault("devices", {})

    if DOMAIN not in config:
        return True

    platforms = set()

    for index, raw_config in enumerate(config[DOMAIN]):
        coordinator = await _async_create_coordinator(
            hass,
            raw_config,
        )

        key = (
            f"yaml_{index}_"
            f"{coordinator.ip_address}_"
            f"{coordinator.port}_"
            f"{coordinator.list_id}"
        )

        runtime["devices"][key] = {
            "coordinator": coordinator,
            "source": "yaml",
        }

        for variable in coordinator.variables:
            platforms.add(variable["entity"])

        if coordinator.mode == MODE_READ:
            platforms.add("sensor")

    for platform in platforms:
        hass.async_create_task(
            discovery.async_load_platform(
                hass,
                platform,
                DOMAIN,
                {},
                config,
            )
        )

    hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP,
        lambda event: hass.async_create_task(
            _async_stop_all(hass, event)
        ),
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    coordinator = await _async_create_coordinator(
        hass,
        dict(entry.data),
    )

    hass.data[DOMAIN]["devices"][entry.entry_id] = {
        "coordinator": coordinator,
        "source": "config_entry",
    }

    await hass.config_entries.async_forward_entry_setups(
        entry,
        ["sensor", "binary_sensor", "switch", "number"],
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(
        entry,
        ["sensor", "binary_sensor", "switch", "number"],
    )

    if not unloaded:
        return False

    device = hass.data[DOMAIN]["devices"].pop(
        entry.entry_id,
        None,
    )

    if device:
        coordinator = device["coordinator"]
        await coordinator.async_stop()
        hub = coordinator.hub

        hub.unregister(coordinator)

        if not hub.coordinators:
            await hub.async_stop()
            hass.data[DOMAIN]["hubs"].pop(hub.port, None)

    return True
