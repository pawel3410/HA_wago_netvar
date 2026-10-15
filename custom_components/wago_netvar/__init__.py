import asyncio
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import (
    DOMAIN,
    CONF_IP_ADDRESS,
    CONF_PORT,
    CONF_COB_ID,
    CONF_VAR_COUNT,
    CONF_BIG_ENDIAN,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    
    ip_address = entry.data[CONF_IP_ADDRESS]
    port = entry.data.get(CONF_PORT, 1202)
    cob_id = entry.data[CONF_COB_ID]
    var_count = entry.data.get(CONF_VAR_COUNT, 1)
    big_endian = entry.data.get(CONF_BIG_ENDIAN, True)

    coordinator = NetVarCoordinator(hass, ip_address, port, cob_id, var_count, big_endian)
    await coordinator.async_setup()
    
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "switch", "number"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, ["sensor", "switch", "number"])

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
        _LOGGER.info("NetVar UDP nasłuchuje na porcie %d (COB-ID: %d, Liczba zmiennych: %d)", self.port, self.cob_id, self.var_count)

    async def async_stop(self):
        if self.transport:
            self.transport.close()

    def _handle_packet(self, data: bytes, addr):
        if len(data) >= 20 and data[0:4] == b"\x00\x2D\x53\x33":
            endian = "big" if self.big_endian else "little"
            pkt_cob_id = int.from_bytes(data[8:10], endian)
            
            if pkt_cob_id == self.cob_id:
                payload = data[20:]
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
        """Wysyła ramkę UDP z liczbą zmiennych (var_count) na bajtach 12-13"""
        if not self.transport or not self.ip_address:
            return
        
        payload_bytes = bytes(self.tx_payload)
        header = bytearray(20)
        header[0:4] = b"\x00\x2D\x53\x33"
        total_len = 20 + len(payload_bytes)
        
        endian = "big" if self.big_endian else "little"
        
        header[8:10] = self.cob_id.to_bytes(2, endian)
        header[12:14] = self.var_count.to_bytes(2, endian)  # <--- Liczba zmiennych w ramce (bajty 12-13)
        header[14:16] = total_len.to_bytes(2, endian)
        header[16:18] = self.sequence_counter.to_bytes(2, endian)
        self.sequence_counter = (self.sequence_counter + 1) % 65536

        packet = bytes(header) + payload_bytes
        self.transport.sendto(packet, (self.ip_address, self.port))
