from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
import struct

async def async_setup_platform(hass: HomeAssistant, config: dict, async_add_entities: AddEntitiesCallback, discovery_info=None) -> None:
    if DOMAIN not in hass.data:
        return

    entities = []
    for cob_id, data in hass.data[DOMAIN].items():
        coordinator = data["coordinator"]
        for sensor_conf in data["sensors"]:
            entities.append(
                NetVarSensor(
                    coordinator=coordinator,
                    name=sensor_conf["name"],
                    cob_id=cob_id,
                    byte_offset=sensor_conf["byte_offset"],
                    size=sensor_conf["size"],
                    var_type=sensor_conf["var_type"],
                    device_class=sensor_conf.get("device_class"),
                    state_class=sensor_conf.get("state_class"),
                    unit_of_measurement=sensor_conf.get("unit_of_measurement"),
                    icon=sensor_conf.get("icon"),
                )
            )
    async_add_entities(entities)

class NetVarSensor(SensorEntity):
    def __init__(self, coordinator, name, cob_id, byte_offset, size, var_type, device_class, state_class, unit_of_measurement, icon):
        self._coordinator = coordinator
        self._attr_name = name
        self._cob_id = cob_id
        self._byte_offset = byte_offset
        self._size = size
        self._var_type = var_type
        
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_icon = icon
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
            val = struct.unpack('>f' if endian == 'big' else '<f', raw_data)[0]
            self._attr_native_value = round(val, 2)
        else:
            self._attr_native_value = int.from_bytes(raw_data, endian, signed=True)

        self.schedule_update_ha_state()
