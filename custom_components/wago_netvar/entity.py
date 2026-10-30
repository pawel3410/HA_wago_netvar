from homeassistant.helpers.entity import Entity
from homeassistant.util import slugify

from .const import DOMAIN, MODE_READ
from .codec import decode_value, get_size


class NetVarEntity(Entity):
    def __init__(self, coordinator, variable):
        self.coordinator = coordinator
        self.variable = variable

        self._variable_index = next(
            index
            for index, item in enumerate(coordinator.variables)
            if item is variable
        )

        self._attr_name = variable["name"]
        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.ip_address}_"
            f"{coordinator.port}_{coordinator.list_id}_"
            f"{slugify(variable['name'])}"
        )

        self._attr_icon = variable.get("icon")
        self._attr_force_update = variable.get("force_update", False)
        self._attr_entity_registry_enabled_default = variable.get(
            "enabled_by_default", True
        )

        category = variable.get("entity_category")
        if category:
            from homeassistant.helpers.entity import EntityCategory
            self._attr_entity_category = EntityCategory(category)

        self._attr_available = coordinator.mode != MODE_READ

    @property
    def available(self):
        if self.coordinator.mode != MODE_READ:
            return True

        return self._variable_index in self.coordinator.received

    async def async_added_to_hass(self):
        if self.coordinator.mode == MODE_READ:
            self.coordinator.register_listener(self._handle_update)

    async def async_will_remove_from_hass(self):
        self.coordinator.unregister_listener(self._handle_update)

    def _get_value(self, payload):
        offset = self.variable["offset"]
        size = get_size(self.variable["type"])

        if len(payload) < offset + size:
            return None

        return decode_value(
            payload[offset:offset + size],
            self.variable["type"],
        )

    def _handle_update(self, payload):
        if self.coordinator.mode != MODE_READ:
            return

        if self._variable_index not in self.coordinator.received:
            return

        value = self._get_value(payload)

        if value is not None:
            self._update_value(value)

    def _update_value(self, value):
        raise NotImplementedError
