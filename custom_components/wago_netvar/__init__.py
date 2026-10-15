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
    vol.Required("cob_id"): int,
    vol.Optional("var_count", default=1): int,
    vol.Optional("big_endian", default=True): bool,
    vol.Optional("sensors", default=[]): vol.All(cv.ensure_list, [SENSOR_SCHEMA]),
    vol.Optional("switches", default=[]): vol.All(cv.ensure_list, [SWITCH_SCHEMA]),
    vol.Optional("numbers", default=[]): vol.All(cv.ensure_list, [NUMBER_SCHEMA]),
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.All(cv.ensure_list, [DEVICE_SCHEMA])
}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    
    if DOMAIN not in config:
        return True

    for device_conf in config[DOMAIN]:
        ip_address = device_conf["ip_address"]
        port = device_conf["port"]
        cob_id = device_conf["cob_id"]
        var_count = device_conf["var_count"]
        big_endian = device_conf["big_endian"]

        coordinator = NetVarCoordinator(hass, ip_address, port, cob_id, var_count, big_endian)
        await coordinator.async_setup()

        hass.data[DOMAIN][cob_id] = {
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
    def __init__(self, callback):
        self.callback = callback
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.callback(data, addr)

class NetVarCoordinator:
    def __init__(self, hass: HomeAssistant, ip_address: str, port: int, cob_id: int, var_count: int, big_endian: bool):
        self.hass = hass
        self.ip_address = ip_address
        self.port = port
        self.cob_id = cob_id
        self.var_count = var_count
        self.big_endian = big_endian
        self.transport = None
        self.protocol = None
        self.listeners = []
        self.tx_payload = bytearray()
        self.sequence_counter = 0

    async def async_setup(self):
        loop = asyncio.get_running_loop()
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: NetVarUDPProtocol(self._handle_packet),
            local_addr=('0.0.0.0', self.port)
        )
        _LOGGER.info("NetVar UDP nasłuchuje na porcie %d (COB-ID: %d)", self.port, self.cob_id)

    async def async_stop(self):
        if self.transport:
            self.transport.close()

    def _handle_packet(self, data: bytes, addr):
        if len(data) >= 20 and data[0:4] == b"\x00\x2D\x53\x33":
            pkt_cob_id = int.from_bytes(data[8:10], "little")
            pkt_var_count = int.from_bytes(data[12:14], "little")
            pkt_total_len = int.from_bytes(data[14:16], "little")
            pkt_sequence = int.from_bytes(data[16:18], "little")
            payload = data[20:]

            _LOGGER.info(
                "Odebrano pakiet UDP [RX] od %s | COB-ID: %d | Var Count: %d | Total Len: %d | Seq: %d | Payload (hex): %s",
                addr[0], pkt_cob_id, pkt_var_count, pkt_total_len, pkt_sequence, payload.hex()
            )
            
            if pkt_cob_id == self.cob_id:
                if len(self.tx_payload) < len(payload):
                    self.tx_payload = bytearray(payload)
                else:
                    self.tx_payload[:len(payload)] = payload

                for listener in self.listeners:
                    listener(payload)
        else:
            _LOGGER.warning("Odebrano nieznany lub za krótki pakiet UDP od %s (długość: %d)", addr[0], len(data))

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
        if not self.transport or not self.ip_address:
            return
        
        payload_bytes = bytes(self.tx_payload)
        header = bytearray(20)
        header[0:4] = b"\x00\x2D\x53\x33"
        total_len = 20 + len(payload_bytes)
        
        header[8:10] = self.cob_id.to_bytes(2, "little")
        header[12:14] = self.var_count.to_bytes(2, "little")
        header[14:16] = total_len.to_bytes(2, "little")
        header[16:18] = self.sequence_counter.to_bytes(2, "little")
        
        current_seq = self.sequence_counter
        self.sequence_counter = (self.sequence_counter + 1) % 65536

        packet = bytes(header) + payload_bytes
        self.transport.sendto(packet, (self.ip_address, self.port))

        _LOGGER.info(
            "Wysłano pakiet UDP [TX] do %s:%d | COB-ID: %d | Var Count: %d | Total Len: %d | Seq: %d | Payload (hex): %s",
            self.ip_address, self.port, self.cob_id, self.var_count, total_len, current_seq, payload_bytes.hex()
        )
