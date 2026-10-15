import asyncio
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    
    ip_address = entry.data.get("ip_address")
    port = entry.data.get("port", 1202)
    big_endian = entry.data.get("big_endian", True)

    coordinator = NetVarCoordinator(hass, ip_address, port, big_endian)
    await coordinator.async_setup()
    
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "switch"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, ["sensor", "switch"])

class NetVarUDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, callback):
        self.callback = callback
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.callback(data, addr)

class NetVarCoordinator:
    def __init__(self, hass: HomeAssistant, ip_address: str, port: int, big_endian: bool):
        self.hass = hass
        self.ip_address = ip_address
        self.port = port
        self.big_endian = big_endian
        self.transport = None
        self.protocol = None
        # Słownik: kluczem jest cob_id, wartością lista funkcji zwrotnych (encji)
        self.listeners = {}
        self.sequence_counter = 0

    async def async_setup(self):
        loop = asyncio.get_running_loop()
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: NetVarUDPProtocol(self._handle_packet),
            local_addr=('0.0.0.0', self.port)
        )
        _LOGGER.info("NetVar UDP serwer nasłuchuje na porcie %d", self.port)

    async def async_stop(self):
        if self.transport:
            self.transport.close()

    def _handle_packet(self, data: bytes, addr):
        if len(data) >= 20 and data[0:4] == b"\x00\x2D\x53\x33":
            endian = "big" if self.big_endian else "little"
            pkt_cob_id = int.from_bytes(data[8:10], endian)
            
            # Jeśli mamy zarejestrowane encje na ten konkretny cob_id, przekazujemy im payload
            if pkt_cob_id in self.listeners:
                payload = data[20:]
                for listener in self.listeners[pkt_cob_id]:
                    listener(payload)

    def register_listener(self, cob_id: int, callback):
        if cob_id not in self.listeners:
            self.listeners[cob_id] = []
        if callback not in self.listeners[cob_id]:
            self.listeners[cob_id].append(callback)

    def unregister_listener(self, cob_id: int, callback):
        if cob_id in self.listeners and callback in self.listeners[cob_id]:
            self.listeners[cob_id].remove(callback)

    def send_packet(self, cob_id: int, payload_bytes: bytes):
        if not self.transport or not self.ip_address:
            return
        
        header = bytearray(20)
        header[0:4] = b"\x00\x2D\x53\x33"
        total_len = 20 + len(payload_bytes)
        
        endian = "big" if self.big_endian else "little"
        header[8:10] = cob_id.to_bytes(2, endian)
        header[14:16] = total_len.to_bytes(2, endian)
        header[16:18] = self.sequence_counter.to_bytes(2, endian)
        self.sequence_counter = (self.sequence_counter + 1) % 65536

        packet = bytes(header) + payload_bytes
        self.transport.sendto(packet, (self.ip_address, self.port))
