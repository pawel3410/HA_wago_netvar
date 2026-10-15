import struct
from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify
from .const import DOMAIN

async def async_setup_platform(hass: HomeAssistant, config: dict, async_add_entities: AddEntitiesCallback, discovery_info=None) -> None:
    if DOMAIN not in hass.data:
        return

    entities = []
    for cob_id, data in hass.data[DOMAIN].items():
        coordinator = data["coordinator"]
        for num_conf in data["numbers"]:
            entities.append(
                NetVarNumber(
                    coordinator=coordinator,
                    name=num_conf["name"],
                    cob_id=cob_id,
                    byte_offset=num_conf["byte_offset"],
                    var_type=num_conf["var_type"],
                    min_val=num_conf["min"],
                    max_val=num_conf["max"],
                    step=num_conf["step"],
                    device_class=num_conf.get("device_class"),
                    unit_of_measurement=num_conf.get("unit_of_measurement"),
                    icon=num_conf.get("icon"),
                    force_update=num_conf.get("force_update", False),
                )
            )
    async_add_entities(entities)

class NetVarNumber(NumberEntity):
    def __init__(self, coordinator, name, cob_id, byte_offset, var_type, min_val, max_val, step, device_class, unit_of_measurement, icon, force_update):
        self._coordinator = coordinator
        self._attr_name = name
        self._cob_id = cob_id
        self._byte_offset = byte_offset
        self._var_type = var_type
        
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step
        
        self._attr_force_update = force_update
        self._attr_unique_id = f"{DOMAIN}_{cob_id}_{slugify(name)}"
        
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_icon = icon
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
