from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NetVarSwitch(coordinator, "PLC Switch 1", byte_offset=4, bit_offset=0)])
    return True

class NetVarSwitch(SwitchEntity):
    def __init__(self, coordinator, name, byte_offset, bit_offset):
        self._coordinator = coordinator
        self._attr_name = name
        self._byte_offset = byte_offset
        self._bit_offset = bit_offset
        self._is_on = False
        self.current_payload = bytearray(100) # bufor lokalny stanu

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
        self._coordinator.send_packet(bytes(self.current_payload))

    async def async_turn_off(self, **kwargs):
        mask = 1 << self._bit_offset
        if len(self.current_payload) <= self._byte_offset:
            self.current_payload.extend(b'\x00' * (self._byte_offset + 1 - len(self.current_payload)))
        self.current_payload[self._byte_offset] &= ~mask
        self._coordinator.send_packet(bytes(self.current_payload))
