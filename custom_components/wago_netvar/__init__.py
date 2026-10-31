
import asyncio
import ipaddress
import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
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
        offset = int(result["offset"])
        if float(result["offset"]) != offset:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise vol.Invalid("Variable offset must be an integer")

    if offset < 0:
        raise vol.Invalid("Variable offset cannot be negative")

    result["offset"] = offset
    result["type"] = str(result["type"]).upper()
    result["entity"] = str(result["entity"])

    if result["type"] not in TYPE_SIZES:
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

    result.setdefault(
        "initial_value",
        False if result["type"] == "BOOL" else 0,
    )
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
    result.setdefault("transmit_checksum", False)

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

    if not isinstance(result["transmit_checksum"], bool):
        raise vol.Invalid("transmit_checksum must be boolean")

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

    def handle_packet(self, data, addr):
        if len(data) < HEADER_SIZE:
            _LOGGER.debug(
                "Ignored short UDP packet from %s",
                addr[0],
            )
            return

        if data[0:4] != MAGIC:
            _LOGGER.debug("Ignored packet with invalid magic")
            return

        list_id = int.from_bytes(data[8:10], "little")
        variable_index = int.from_bytes(data[10:12], "little")
        variable_count = int.from_bytes(data[12:14], "little")
        total_length = int.from_bytes(data[14:16], "little")
        sequence = int.from_bytes(data[16:18], "little")
        checksum = int.from_bytes(data[18:20], "little")

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
            "RX %s:%d list=%d index=%d count=%d "
            "cycle=%d checksum=0x%04X payload=%s",
            addr[0],
            self.port,
            list_id,
            variable_index,
            variable_count,
            sequence,
            checksum,
            payload.hex(),
        )

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
        self.transmit_checksum = config["transmit_checksum"]

        self.variables = config["variables"]
        self.buffer_size = config["buffer_size"]

        self.payload = bytearray(self.buffer_size)

        # Variables received at least once.
        self.received = set()

        # Variables received in the current sequence.
        self.cycle_received = set()

        self.last_sequence = None
        self.current_sequence = None
        self.last_checksum = 0

        self.listeners = []
        self.tx_sequence = 0

        if self.mode == MODE_WRITE:
            for variable in self.variables:
                encoded = encode_value(
                    variable["initial_value"],
                    variable["type"],
                )

                offset = variable["offset"]
                self.payload[offset:offset + len(encoded)] = encoded

    @property
    def expected_count(self):
        return len(self.variables)

    @property
    def cycle_count(self):
        return len(self.cycle_received)

    @property
    def packet_complete(self):
        if self.mode != MODE_READ:
            return True

        if self.current_sequence is None:
            return False

        return self.cycle_count == self.expected_count

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

    def _start_cycle(self, sequence):
        self.current_sequence = sequence
        self.cycle_received = set()

    def _begin_or_continue_cycle(self, sequence):
        """Keep frames with the same sequence in one cycle.

        Sequence is a 16-bit counter. A forward change starts a new cycle.
        A change that moves backwards is treated as a PLC restart.
        The modular comparison also handles the normal 65535 -> 0 wrap.
        """
        sequence &= 0xFFFF

        if self.current_sequence is None:
            self._start_cycle(sequence)
            return

        if sequence == self.current_sequence:
            return

        previous_sequence = self.current_sequence
        delta = (sequence - previous_sequence) & 0xFFFF

        self.last_sequence = previous_sequence
        self._start_cycle(sequence)

        if delta < 0x8000:
            if delta > 1:
                _LOGGER.debug(
                    "List %d sequence advanced from %d to %d "
                    "(%d sequence values skipped)",
                    self.list_id,
                    previous_sequence,
                    sequence,
                    delta - 1,
                )
        else:
            _LOGGER.info(
                "List %d sequence moved backwards from %d to %d; "
                "starting a new cycle after PLC restart",
                self.list_id,
                previous_sequence,
                sequence,
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

        self._begin_or_continue_cycle(sequence)

        offset = variable["offset"]
        self.payload[offset:offset + size] = payload

        self.received.add(variable_index)
        self.cycle_received.add(variable_index)
        self.last_checksum = checksum

        # Publish immediately after every valid frame.
        self.notify({variable_index})

        _LOGGER.debug(
            "List %d cycle %d: received %d/%d variables",
            self.list_id,
            sequence,
            self.cycle_count,
            self.expected_count,
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

        self._begin_or_continue_cycle(sequence)

        self.payload[:] = payload

        all_indices = set(range(len(self.variables)))

        self.received = set(all_indices)
        self.cycle_received = set(all_indices)
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

        encoded = encode_value(value, variable["type"])
        offset = variable["offset"]

        old_value = bytes(
            self.payload[offset:offset + len(encoded)]
        )

        self.payload[offset:offset + len(encoded)] = encoded

        if not self.send_variable(variable):
            self.payload[offset:offset + len(encoded)] = old_value
            raise ValueError(
                "NetVar packet was not sent. "
                "Check checksum configuration and UDP transport."
            )

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

        header[16:18] = self.tx_sequence.to_bytes(2, "little")

        # Checksum generation is not implemented.
        header[18:20] = b"\x00\x00"

        self.tx_sequence = (self.tx_sequence + 1) & 0xFFFF

        return bytes(header) + payload

    def send_variable(self, variable):
        if self.mode != MODE_WRITE:
            return False

        if self.transmit_checksum:
            _LOGGER.error(
                "Cannot send list %d with transmit_checksum enabled: "
                "checksum algorithm is not verified",
                self.list_id,
            )
            return False

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

            value = bytes(
                self.payload[offset:offset + size]
            )

            packet = self.build_packet(
                value,
                index,
                1,
            )

        sent = self.hub.sendto(
            packet,
            (self.ip_address, self.port),
        )

        if not sent:
            return False

        _LOGGER.info(
            "TX PLC=%s:%d list=%d packed=%s payload=%s",
            self.ip_address,
            self.port,
            self.list_id,
            self.pack_variables,
            packet[HEADER_SIZE:].hex(),
        )

        return True


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
