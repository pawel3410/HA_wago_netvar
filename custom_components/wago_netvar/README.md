================================================================================
KOMPLETNY KOD INTEGRACJI HACS ORAZ DOKUMENTACJA README.MD
================================================================================

1. PLIK: manifest.json
--------------------------------------------------------------------------------
{
  "domain": "wago_netvar",
  "name": "Wago NetVar UDP",
  "documentation": "https://github.com/pawel3410/EspHome_NetVar",
  "requirements": [],
  "codeowners": [],
  "iot_class": "local_push",
  "version": "1.0.0",
  "config_flow": true
}


2. PLIK: const.py
--------------------------------------------------------------------------------
DOMAIN = "wago_netvar"
DEFAULT_PORT = 1202

CONF_IP_ADDRESS = "ip_address"
CONF_PORT = "port"
CONF_COB_ID = "cob_id"
CONF_VAR_COUNT = "var_count"
CONF_BIG_ENDIAN = "big_endian"


3. PLIK: config_flow.py
--------------------------------------------------------------------------------
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    CONF_IP_ADDRESS,
    CONF_PORT,
    CONF_COB_ID,
    CONF_VAR_COUNT,
    CONF_BIG_ENDIAN,
)

class WagoNetVarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(
                title=f"NetVar (COB-ID: {user_input[CONF_COB_ID]})",
                data=user_input
            )

        schema = vol.Schema({
            vol.Required(CONF_IP_ADDRESS): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Required(CONF_COB_ID, default=1): int,
            vol.Optional(CONF_VAR_COUNT, default=1): int,
            vol.Optional(CONF_BIG_ENDIAN, default=True): bool,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )


4. PLIK: __init__.py
--------------------------------------------------------------------------------
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
        _LOGGER.info("NetVar UDP nasłuchuje na porcie %d (COB-ID: %d, Var Count: %d)", self.port, self.cob_id, self.var_count)

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
        if not self.transport or not self.ip_address:
            return
        
        payload_bytes = bytes(self.tx_payload)
        header = bytearray(20)
        header[0:4] = b"\x00\x2D\x53\x33"
        total_len = 20 + len(payload_bytes)
        
        endian = "big" if self.big_endian else "little"
        
        header[8:10] = self.cob_id.to_bytes(2, endian)
        header[12:14] = self.var_count.to_bytes(2, endian)  # Liczba zmiennych na bajtach 12-13
        header[14:16] = total_len.to_bytes(2, endian)
        header[16:18] = self.sequence_counter.to_bytes(2, endian)
        self.sequence_counter = (self.sequence_counter + 1) % 65536

        packet = bytes(header) + payload_bytes
        self.transport.sendto(packet, (self.ip_address, self.port))


5. PLIK: sensor.py (Przykłady odczytu różnych typów zmiennych)
--------------------------------------------------------------------------------
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([
        # Odczyt temperatury (REAL, 4 bajty) z offsetu 0 w ramce cob_id = 1
        NetVarSensor(coordinator, name="Temperatura Salon", cob_id=1, byte_offset=0, size=4, var_type="REAL"),
        
        # Odczyt wilgotności (INT, 2 bajty) z offsetu 4 w ramce cob_id = 1
        NetVarSensor(coordinator, name="Wilgotność", cob_id=1, byte_offset=4, size=2, var_type="INT"),
        
        # Odczyt licznika energii (DINT, 4 bajty) z offsetu 0 w ramce cob_id = 2
        NetVarSensor(coordinator, name="Licznik Energii", cob_id=2, byte_offset=0, size=4, var_type="DINT"),
    ])
    return True

class NetVarSensor(SensorEntity):
    def __init__(self, coordinator, name, cob_id, byte_offset, size, var_type):
        self._coordinator = coordinator
        self._attr_name = name
        self._cob_id = cob_id
        self._byte_offset = byte_offset
        self._size = size
        self._var_type = var_type
        self._attr_native_value = None

    async def async_added_to_hass(self):
        self._coordinator.register_listener(self._handle_update)

    async def async_will_remove_from_hass(self):
        self._coordinator.unregister_listener(self._handle_update)

    def _handle_update(self, payload: bytes):
        if len(payload) < self._byte_offset + self._size:
            return
        
        raw_data = payload[self._byte_offset:self._byte_offset + self._size]
        endian = "big" if self._coordinator.big_endian else "little"

        if self._var_type == "REAL":
            import struct
            val = struct.unpack('>f' if endian == 'big' else '<f', raw_data)[0]
            self._attr_native_value = round(val, 2)
        else:
            self._attr_native_value = int.from_bytes(raw_data, endian, signed=True)

        self.schedule_update_ha_state()


6. PLIK: switch.py (Przykłady wysyłania stanów logicznych BOOL)
--------------------------------------------------------------------------------
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([
        # Sterowanie światłem w ramce cob_id = 1 (bajt 8, bit 0)
        NetVarSwitch(coordinator, name="Światło Salon", cob_id=1, byte_offset=8, bit_offset=0),
        
        # Sterowanie pompą ciepła w ramce cob_id = 1 (bajt 8, bit 1)
        NetVarSwitch(coordinator, name="Pompa Ciepła", cob_id=1, byte_offset=8, bit_offset=1),
    ])
    return True

class NetVarSwitch(SwitchEntity):
    def __init__(self, coordinator, name, cob_id, byte_offset, bit_offset):
        self._coordinator = coordinator
        self._attr_name = name
        self._cob_id = cob_id
        self._byte_offset = byte_offset
        self._bit_offset = bit_offset
        self._is_on = False
        self.current_payload = bytearray(100)

    async def async_added_to_hass(self):
        self._coordinator.register_listener(self._handle_update)

    async def async_will_remove_from_hass(self):
        self._coordinator.unregister_listener(self._handle_update)

    def _handle_update(self, payload: bytes):
        if len(payload) <= self._byte_offset:
            return
        self.current_payload = bytearray(payload)
        mask = 1 << self._bit_offset
        self._is_on = bool(payload[self._byte_offset] & mask)
        self.schedule_update_ha_state()

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs):
        mask = 1 << self._bit_offset
        if len(self.current_payload) <= self._byte_offset:
            self.current_payload.extend(b'\x00' * (self._byte_offset + 1 - len(self.current_payload)))
        self.current_payload[self._byte_offset] |= mask
        self._coordinator.update_payload_bytes(self._byte_offset, bytes([self.current_payload[self._byte_offset]]))
        self._coordinator.send_frame()

    async def async_turn_off(self, **kwargs):
        mask = 1 << self._bit_offset
        if len(self.current_payload) <= self._byte_offset:
            self.current_payload.extend(b'\x00' * (self._byte_offset + 1 - len(self.current_payload)))
        self.current_payload[self._byte_offset] &= ~mask
        self._coordinator.update_payload_bytes(self._byte_offset, bytes([self.current_payload[self._byte_offset]]))
        self._coordinator.send_frame()


7. PLIK: number.py (Przykłady wysyłania wartości numerycznych REAL / INT)
--------------------------------------------------------------------------------
import struct
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([
        # Zadana temperatura (REAL, 4 bajty) na offsecie 10 w ramce cob_id = 1
        NetVarNumber(
            coordinator, 
            name="Zadana Temperatura", 
            cob_id=1, 
            byte_offset=10, 
            var_type="REAL", 
            min_val=10.0, 
            max_val=30.0, 
            step=0.5
        ),
        # Czas opóźnienia (INT, 2 bajty) na offsecie 14 w ramce cob_id = 1
        NetVarNumber(
            coordinator, 
            name="Czas Opóźnienia", 
            cob_id=1, 
            byte_offset=14, 
            var_type="INT", 
            min_val=0, 
            max_val=60, 
            step=1
        ),
    ])
    return True

class NetVarNumber(NumberEntity):
    def __init__(self, coordinator, name, cob_id, byte_offset, var_type, min_val, max_val, step):
        self._coordinator = coordinator
        self._attr_name = name
        self._cob_id = cob_id
        self._byte_offset = byte_offset
        self._var_type = var_type
        
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step
        self._attr_native_value = min_val

    async def async_added_to_hass(self):
        self._coordinator.register_listener(self._handle_update)

    async def async_will_remove_from_hass(self):
        self._coordinator.unregister_listener(self._handle_update)

    def _handle_update(self, payload: bytes):
        size = 4 if self._var_type in ["REAL", "DINT", "UDINT"] else 2
        if len(payload) < self._byte_offset + size:
            return
        
        raw_data = payload[self._byte_offset:self._byte_offset + size]
        endian = "big" if self._coordinator.big_endian else "little"

        if self._var_type == "REAL":
            val = struct.unpack('>f' if endian == 'big' else '<f', raw_data)[0]
            self._attr_native_value = round(val, 2)
        else:
            self._attr_native_value = int.from_bytes(raw_data, endian, signed=True)

        self.schedule_update_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        endian = "big" if self._coordinator.big_endian else "little"
        
        if self._var_type == "REAL":
            encoded_data = struct.pack('>f' if endian == 'big' else '<f', float(value))
        else:
            size = 2 if self._var_type in ["INT", "UINT"] else 4
            signed = self._var_type in ["INT", "DINT"]
            encoded_data = int(value).to_bytes(size, endian, signed=signed)

        self._coordinator.update_payload_bytes(self._byte_offset, encoded_data)
        self._attr_native_value = value
        self.schedule_update_ha_state()
        self._coordinator.send_frame()


8. PLIK: README.md
--------------------------------------------------------------------------------
# Wago NetVar Integration for Home Assistant

Niestandardowa integracja dla Home Assistanta umożliwiająca dwukierunkową komunikację ze sterownikami PLC (Wago / CoDeSys) przez protokół NetVar UDP (.S3).

## Specyfikacja Techniczna Nagłówka Ramki (.S3)
| Pozycja (Bajty) | Nazwa pola | Opis |
| :--- | :--- | :--- |
| `0 - 3` | Magiczny nagłówek | Flaga stała: `0x00, 0x2D, 0x53, 0x33` (.S3) |
| `8 - 9` | `cob_id` | Identyfikator ramki / bloku zmiennych |
| `12 - 13`| `var_count` | Liczba zmiennych wysyłanych w payloadzie ramki |
| `14 - 15`| `total_len` | Całkowita długość pakietu (20 + długość payloadu) |
| `16 - 17`| `sequence` | Licznik sekwencji pakietów |
| `20+` | `Payload` | Właściwe dane zmiennych PLC (upakowane binarnie) |

## Obsługiwane Typy Zmiennych PLC
- `BOOL` (1 bit) -> Switch / Binary Sensor
- `BYTE` / `USINT` / `SINT` (1 bajt) -> Sensor
- `WORD` / `UINT` / `INT` (2 bajty) -> Sensor / Number
- `DWORD` / `UDINT` / `DINT` / `TIME` (4 bajty) -> Sensor / Number
- `REAL` (4 bajty) -> Sensor / Number
- `LREAL` (8 bajtów) -> Sensor
