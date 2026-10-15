from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Definiujemy czujniki przypisane do różnych COB-ID
    async_add_entities([
        # Sensor z ramki o cob_id = 1, bajt 0, długość 4 bajty (REAL)
        NetVarSensor(coordinator, name="Temperatura Salon", cob_id=1, byte_offset=0, size=4, var_type="REAL"),
        
        # Sensor z ramki o cob_id = 2, bajt 4, długość 2 bajty (INT)
        NetVarSensor(coordinator, name="Licznik Energii", cob_id=2, byte_offset=4, size=2, var_type="INT")
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
        # Rejestrujemy encję do konkretnego cob_id
        self._coordinator.register_listener(self._cob_id, self._handle_update)

    async def async_will_remove_from_hass(self):
        self._coordinator.unregister_listener(self._cob_id, self._handle_update)

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
