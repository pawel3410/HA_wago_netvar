from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify
from .const import DOMAIN
import struct

async def async_setup_platform(hass: HomeAssistant, config: dict, async_add_entities: AddEntitiesCallback, discovery_info=None) -> None:
    if DOMAIN not in hass.data:
        return

    entities = []
    for list_id, data in hass.data[DOMAIN].items():
        if list_id == "hubs":
            continue
            
        coordinator = data["coordinator"]
        for sensor_conf in data["sensors"]:
            entities.append(
                NetVarSensor(
                    coordinator=coordinator,
                    name=sensor_conf["name"],
                    list_id=list_id,
                    byte_offset=sensor_conf["byte_offset"],
                    size=sensor_conf["size"],
                    var_type=sensor_conf["var_type"],
                    device_class=sensor_conf.get("device_class"),
                    state_class=sensor_conf.get("state_class"),
                    unit_of_measurement=sensor_conf.get("unit_of_measurement"),
                    icon=sensor_conf.get("icon"),
                    force_update=sensor_conf.get("force_update", False),
                    suggested_display_precision=sensor_conf.get("suggested_display_precision"),
                    entity_category=sensor_conf.get("entity_category"),
                    enabled_by_default=sensor_conf.get("enabled_by_default", True),
                    zero_as_unavailable=sensor_conf.get("zero_as_unavailable", True),
                )
            )
    async_add_entities(entities)

class NetVarSensor(SensorEntity):
    def __init__(self, coordinator, name, list_id, byte_offset, size, var_type, device_class, state_class, unit_of_measurement, icon, force_update, suggested_display_precision, entity_category, enabled_by_default, zero_as_unavailable=True):
        self._coordinator = coordinator
        self._attr_name = name
        self._list_id = list_id
        self._byte_offset = byte_offset
        self._size = size
        self._var_type = var_type
        
        self._attr_force_update = force_update
        self._attr_unique_id = f"{DOMAIN}_{list_id}_{slugify(name)}"
        
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_icon = icon
        self._attr_suggested_display_precision = suggested_display_precision
        self._attr_entity_category = entity_category
        self._attr_entity_registry_enabled_default = enabled_by_default
        self._zero_as_unavailable = zero_as_unavailable
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
            if self._zero_as_unavailable and val == 0.0:
                self._attr_native_value = None
            else:
                self._attr_native_value = val
        else:
            val = int.from_bytes(raw_data, endian, signed=True)
            if self._zero_as_unavailable and val == 0:
                self._attr_native_value = None
            else:
                self._attr_native_value = val

        self.schedule_update_ha_state()
