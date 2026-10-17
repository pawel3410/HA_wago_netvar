from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify
from .const import DOMAIN

async def async_setup_platform(hass: HomeAssistant, config: dict, async_add_entities: AddEntitiesCallback, discovery_info=None) -> None:
    if DOMAIN not in hass.data:
        return

    entities = []
    for list_id, data in hass.data[DOMAIN].items():
        if list_id == "hubs":
            continue
            
        coordinator = data["coordinator"]
        for switch_conf in data["switches"]:
            entities.append(
                NetVarSwitch(
                    coordinator=coordinator,
                    name=switch_conf["name"],
                    list_id=list_id,
                    byte_offset=switch_conf["byte_offset"],
                    bit_offset=switch_conf["bit_offset"],
                    device_class=switch_conf.get("device_class"),
                    icon=switch_conf.get("icon"),
                    force_update=switch_conf.get("force_update", False),
                )
            )
    async_add_entities(entities)

class NetVarSwitch(SwitchEntity):
    def __init__(self, coordinator, name, list_id, byte_offset, bit_offset, device_class, icon, force_update):
        self._coordinator = coordinator
        self._attr_name = name
        self._list_id = list_id
        self._byte_offset = byte_offset
        self._bit_offset = bit_offset
        
        self._attr_force_update = force_update
        self._attr_unique_id = f"{DOMAIN}_{list_id}_{slugify(name)}"
        
        self._attr_device_class = device_class
        self._attr_icon = icon
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
