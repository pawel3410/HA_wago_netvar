import asyncio
import logging
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv
from .const import DOMAIN, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)

SENSOR_SCHEMA = vol.Schema({
    vol.Required("name"): cv.string,
    vol.Required("byte_offset"): int,
    vol.Required("size"): int,
    vol.Required("var_type"): cv.string,
    vol.Optional("device_class"): cv.string,
    vol.Optional("state_class"): cv.string,
    vol.Optional("unit_of_measurement"): cv.string,
    vol.Optional("icon"): cv.string,
    vol.Optional("force_update", default=False): cv.boolean,
})

SWITCH_SCHEMA = vol.Schema({
    vol.Required("name"): cv.string,
    vol.Required("byte_offset"): int,
    vol.Required("bit_offset"): int,
    vol.Optional("device_class"): cv.string,
    vol.Optional("icon"): cv.string,
    vol.Optional("force_update", default=False): cv.boolean,
})

NUMBER_SCHEMA = vol.Schema({
    vol.Required("name"): cv.string,
    vol.Required("byte_offset"): int,
    vol.Required("var_type"): cv.string,
    vol.Optional("min", default=0.0): vol.Coerce(float),
    vol.Optional("max", default=100.0): vol.Coerce(float),
    vol.Optional("step", default=1.0): vol.Coerce(float),
    vol.Optional("device_class"): cv.string,
    vol.Optional("unit_of_measurement"): cv.string,
    vol.Optional("icon"): cv.string,
    vol.Optional("force_update", default=False): cv.boolean,
})

DEVICE_SCHEMA = vol.Schema({
    vol.Required("ip_address"): cv.string,
    vol.Optional("port", default=DEFAULT_PORT): int,
    vol.Required("list_id"): int,
    vol.Optional("var_count", default=1): int,
    vol.Optional("big_endian", default=False): bool,
    vol.Optional("sensors", default=[]): vol.All(cv.ensure_list, [SENSOR_SCHEMA]),
    vol.Optional("switches", default=[]): vol.All(cv.ensure_list, [SWITCH_SCHEMA]),
    vol.Optional("numbers", default=[]): vol.All(cv.ensure_list, [NUMBER_SCHEMA]),
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.All(cv.ensure_list, [DEVICE_SCHEMA])
}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("hubs", {})
    
    if DOMAIN not in config:
        return True

    hubs = hass.data[DOMAIN]["hubs"]

    for device_conf in config[DOMAIN]:
        ip_address = device_conf["ip_address"]
        port = device_conf["port"]
        list_id = device_conf["list_id"]
        var_count = device_conf["var_count"]
        big_endian = device_conf["big_endian"]

        # Utwórz jeden wspólny hub dla danego portu UDP, jeśli jeszcze nie istnieje
        if port not in hubs:
            hub = NetVarPortHub(hass, port)
            await hub.async_setup()
            hubs[port] = hub
        else:
            hub = hubs[port]

        coordinator = NetVarCoordinator(hass, ip_address, port, list_id, var_count, big_endian, hub)
        hub.register_coordinator(list_id, coordinator)

        hass.data[DOMAIN][list_id] = {
            "coordinator": coordinator,
            "sensors": device_conf["sensors"],
            "switches": device_conf["switches"],
            "numbers": device_conf["numbers"],
        }

    platforms = set()
    for device_conf in config[DOMAIN]:
        if device_conf.get("sensors"):
            platforms.add("sensor")
        if device_conf.get("switches"):
            platforms.add("switch")
        if device_conf.get("numbers"):
            platforms.add("number")

    for platform in platforms:
        hass.async_create_task(
            discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
        )

    return True


class NetVarUDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, hub):
        self.hub = hub
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.hub.transport = transport

    def datagram_received(self, data, addr):
        self.hub.handle_packet(data, addr)

    def error_received(self, exc):
        _LOGGER.error("Błąd protokołu UDP: %s", exc)


class NetVarPortHub:
    """Zarządza jednym socketem UDP na danym porcie i rozdziela pakiety do odpowiednich list."""
    def __init__(self, hass: HomeAssistant, port: int):
        self.hass = hass
        self.port = port
        self.transport = None
        self.protocol = None
        self.coordinators = {}

    async def async_setup(self):
        loop = asyncio.get_running_loop()
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: NetVarUDPProtocol(self),
            local_addr=('0.0.0.0', self.port)
        )
        _LOGGER.info("NetVar UDP nasłuchuje współdzielenie na porcie %d", self.port)

    async def async_stop(self):
        if self.transport:
            self.transport.close()

    def register_coordinator(self, list_id: int, coordinator):
        self.coordinators[list_id] = coordinator

    def handle_packet(self, data: bytes, addr):
        if len(data) >= 20 and data[0:4] == b"\x00\x2D\x53\x33":
            pkt_list_id = int.from_bytes(data[8:10], "little")
            pkt_var_count = int.from_bytes(data[12:14], "little")
            pkt_total_len = int.from_bytes(data[14:16], "little")
            pkt_sequence = int.from_bytes(data[16:18], "little")
            payload = data[20:]

            _LOGGER.info(
                "Odebrano pakiet UDP [RX] od %s | Port: %d | List-ID: %d | Var Count: %d | Total Len: %d | Seq: %d | Payload (hex): %s",
                addr[0], self.port, pkt_list_id, pkt_var_count, pkt_total_len, pkt_sequence, payload.hex()
            )
            
            if pkt_list_id in self.coordinators:
                self.coordinators[pkt_list_id]._handle_packet(payload)
            else:
                _LOGGER.debug("Odebrano pakiet dla nieskonfigurowanego List-ID: %d na porcie %d", pkt_list_id, self.port)
        else:
            _LOGGER.warning("Odebrano nieznany lub za krótki pakiet UDP od %s na porcie %d (długość: %d)", addr[0], self.port, len(data))

    def sendto(self, data: bytes, addr):
        if self.transport:
            self.transport.sendto(data, addr)


class NetVarCoordinator:
    def __init__(self, hass: HomeAssistant, ip_address: str, port: int, list_id: int, var_count: int, big_endian: bool, hub: NetVarPortHub):
        self.hass = hass
        self.ip_address = ip_address
        self.port = port
        self.list_id = list_id
        self.var_count = var_count
        self.big_endian = big_endian
        self.hub = hub
        self.listeners = []
        self.tx_payload = bytearray()
        self.sequence_counter = 0

    def _handle_packet(self, payload: bytes):
        if len(self.tx_payload) < len(payload):
            self.tx_payload = bytearray(payload)
        else:
            self.tx_payload[:len(payload)] = payload

        for listener in self.listeners:
            listener(payload)

    def register_listener(self, callback):
        if callback not in self.listeners:
            self.listeners.append(callback)

    def unregister_listener(self, callback):
        if callback in self.listeners:
            self.listeners.remove(callback)

    def update_payload_bytes(self, offset: int, data: bytes):
        required_len = offset + len(data)
        if len(self.tx_payload) < required_len:
            self.tx_payload.extend(b'\x00' * (required_len - len(self.tx_payload)))
            
        for i, b in enumerate(data):
            self.tx_payload[offset + i] = b

    def send_frame(self):
        if not self.hub or not self.ip_address:
            return
        
        payload_bytes = bytes(self.tx_payload)
        header = bytearray(20)
        header[0:4] = b"\x00\x2D\x53\x33"
        total_len = 20 + len(payload_bytes)
        
        header[8:10] = self.list_id.to_bytes(2, "little")
        header[12:14] = self.var_count.to_bytes(2, "little")
        header[14:16] = total_len.to_bytes(2, "little")
        header[16:18] = self.sequence_counter.to_bytes(2, "little")
        
        current_seq = self.sequence_counter
        self.sequence_counter = (self.sequence_counter + 1) % 65536

        packet = bytes(header) + payload_bytes
        self.hub.sendto(packet, (self.ip_address, self.port))

        _LOGGER.info(
            "Wysłano pakiet UDP [TX] do %s:%d | Port: %d | List-ID: %d | Var Count: %d | Total Len: %d | Seq: %d | Payload (hex): %s",
            self.ip_address, self.port, self.port, self.list_id, self.var_count, total_len, current_seq, payload_bytes.hex()
        )
