import asyncio
import ipaddress
import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
from homeassistant.helpers.event import async_call_later
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    MAGIC,
    HEADER_SIZE,
    MODE_READ,
    MODE_WRITE,
    TYPE_SIZES,
    READ_ENTITIES,
    WRITE_ENTITIES,
)
from .codec import get_size, encode_value

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
        result["offset"] = int(result["offset"])
    except (TypeError, ValueError):
        raise vol.Invalid("Variable offset must be an integer")

    if result["offset"] < 0:
        raise vol.Invalid("Variable offset cannot be negative")

    result["type"] = str(result["type"]).upper()

    if result["type"] not in TYPE_SIZES:
        raise vol.Invalid(
            f"Unsupported variable type: {result['type']}"
        )

    result["entity"] = str(result["entity"])

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

    result.setdefault(
        "initial_value",
        False if result["type"] == "BOOL" else 0,
    )

    result.setdefault("enabled_by_default", True)
    result.setdefault("force_update", False)

    if result["entity"] == "sensor":
        result.setdefault("zero_as_unavailable", True)

    if result["entity"] == "number":
        result.setdefault("min", 0)
        result.setdefault("max", 100)
        result.setdefault("step", 1)

        try:
            result["min"] = float(result["min"])
            result["max"] = float(result["max"])
            result["step"] = float(result["step"])
        except (TypeError, ValueError):
            raise vol.Invalid("Invalid number min/max/step")

        if result["min"] >= result["max"]:
            raise vol.Invalid("Number min must be lower than max")

        if result["step"] <= 0:
            raise vol.Invalid("Number step must be positive")

    if result["entity"] == "number":
        try:
            encode_value(result["initial_value"], result["type"])
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

    try:
        result["port"] = int(result["port"])
        result["list_id"] = int(result["list_id"])
    except (KeyError, TypeError, ValueError):
        raise vol.Invalid("port and list_id must be integers")

    if not 1 <= result["port"] <= 65535:
        raise vol.Invalid("port must be between 1 and 65535")

    if not 0 <= result["list_id"] <= 65535:
        raise vol.Invalid("list_id must be between 0 and 65535")

    if result["mode"] not in (MODE_READ, MODE_WRITE):
        raise vol.Invalid("mode must be read or write")

    if not isinstance(result["pack_variables"], bool):
        raise vol.Invalid("pack_variables must be boolean")

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
        end = start + get_size(variable["type"])

        for other_start, other_end in ranges:
            if start < other_end and other_start < end:
                raise vol.Invalid(
                    f"Overlapping variable offset at {start}"
                )

        ranges.append((start, end))

    result["buffer_size"] = max(
        variable["offset"] + get_size(variable["type"])
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

        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: NetVarUDPProtocol(self),
            local_addr=("0.0.0.0", self.port),
        )

        _LOGGER.info("NetVar UDP listening on port %d", self.port)

    async def async_stop(self):
        if self.transport is not None:
            self.transport.close()
            self.transport = None

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
            return

        self.transport.sendto(data, address)

    def handle_packet(self, data, addr):
        if len(data) < HEADER_SIZE:
            _LOGGER.debug("Ignored short UDP packet from %s", addr[0])
            return

        if data[0:4] != MAGIC:
            _LOGGER.debug("Ignored packet with invalid magic")
            return

        list_id = int.from_bytes(data[8:10], "little")
        variable_index = int.from_bytes(data[10:12], "little")
        variable_count = int.from_bytes(data[12:14], "little")
        total_length = int.from_bytes(data[14:16], "little")
        sequence = int.from_bytes(data[16:18], "little")

        if total_length != len(data):
            _LOGGER.warning(
                "Invalid packet length: header=%d actual=%d",
                total_length,
                len(data),
            )
            return

        payload = data[HEADER_SIZE:]

        coordinator = self.coordinators.get((addr[0], list_id))

        if coordinator is None:
            _LOGGER.debug(
                "No configuration for PLC %s list %d",
                addr[0],
                list_id,
            )
            return

        _LOGGER.debug(
            "RX %s:%d list=%d index=%d count=%d seq=%d payload=%s",
            addr[0],
            self.port,
            list_id,
            variable_index,
            variable_count,
            sequence,
            payload.hex(),
        )

        coordinator.handle_packet(
            payload,
            variable_index,
            variable_count,
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
        self.variables = config["variables"]
        self.buffer_size = config["buffer_size"]

        self.payload = bytearray(self.buffer_size)
        self.listeners = []
        self.sequence = 0
        self.received = set()

        if self.mode == MODE_WRITE:
            for variable in self.variables:
                encoded = encode_value(
                    variable["initial_value"],
                    variable["type"],
                )
                offset = variable["offset"]
                self.payload[offset:offset + len(encoded)] = encoded

    def register_listener(self, callback):
        if callback not in self.listeners:
            self.listeners.append(callback)

    def unregister_listener(self, callback):
        if callback in self.listeners:
            self.listeners.remove(callback)

    def notify(self):
        data = bytes(self.payload)

        for callback in list(self.listeners):
            callback(data)

    def handle_packet(self, payload, variable_index, variable_count):
        if self.mode != MODE_READ:
            return

        if self.pack_variables:
            if variable_index != 0:
                _LOGGER.warning(
                    "Packed list %d has unexpected index %d",
                    self.list_id,
                    variable_index,
                )
                return

            if variable_count != len(self.variables):
                _LOGGER.warning(
                    "Packed list %d has count %d, expected %d",
                    self.list_id,
                    variable_count,
                    len(self.variables),
                )
                return

            if len(payload) != self.buffer_size:
                _LOGGER.warning(
                    "Packed list %d payload length %d, expected %d",
                    self.list_id,
                    len(payload),
                    self.buffer_size,
                )
                return

            self.payload[:] = payload
            self.received = set(range(len(self.variables)))

        else:
            if variable_count != 1:
                _LOGGER.debug(
                    "Unpacked packet has variable_count=%d, expected 1",
                    variable_count,
                )
                return

            if not 0 <= variable_index < len(self.variables):
                _LOGGER.warning(
                    "Invalid variable index %d for list %d",
                    variable_index,
                    self.list_id,
                )
                return

            variable = self.variables[variable_index]
            size = get_size(variable["type"])

            if len(payload) != size:
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

        self.notify()

    def set_variable(self, variable, value):
        if self.mode != MODE_WRITE:
            raise ValueError("Cannot write to a read-only list")

        encoded = encode_value(value, variable["type"])
        offset = variable["offset"]

        self.payload[offset:offset + len(encoded)] = encoded

        self.send_variable(variable)
        self.notify()

    def build_packet(self, payload, variable_index, variable_count):
        header = bytearray(HEADER_SIZE)

        header[0:4] = MAGIC
        header[8:10] = self.list_id.to_bytes(2, "little")
        header[10:12] = variable_index.to_bytes(2, "little")
        header[12:14] = variable_count.to_bytes(2, "little")
        header[14:16] = (
            HEADER_SIZE + len(payload)
        ).to_bytes(2, "little")
        header[16:18] = self.sequence.to_bytes(2, "little")

        self.sequence = (self.sequence + 1) & 0xFFFF

        return bytes(header) + payload

    def send_variable(self, variable):
        if self.mode != MODE_WRITE:
            return

        if self.pack_variables:
            packet = self.build_packet(
                bytes(self.payload),
                0,
                len(self.variables),
            )
        else:
            index = self.variables.index(variable)
            offset = variable["offset"]
            size = get_size(variable["type"])
            value = bytes(self.payload[offset:offset + size])

            packet = self.build_packet(value, index, 1)

        self.hub.sendto(
            packet,
            (self.ip_address, self.port),
        )

        _LOGGER.info(
            "TX PLC=%s:%d list=%d packed=%s payload=%s",
            self.ip_address,
            self.port,
            self.list_id,
            self.pack_variables,
            packet[HEADER_SIZE:].hex(),
        )


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
    hub.register(coordinator)

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
        entry.data,
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
        hub = coordinator.hub

        hub.unregister(coordinator)

        if not hub.coordinators:
            await hub.async_stop()
            hass.data[DOMAIN]["hubs"].pop(hub.port, None)

    return True
