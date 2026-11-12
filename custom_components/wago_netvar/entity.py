import logging

from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import Entity

from .codec import DOMAIN, MODE_READ, decode_value, variable_size

_LOGGER = logging.getLogger(__name__)


def get_coordinators(hass):
    """Koordynatory wszystkich list skonfigurowanych w YAML."""
    devices = hass.data.get(DOMAIN, {}).get("devices", {})

    return [device["coordinator"] for device in devices.values()]


def add_platform_entities(
    hass, async_add_entities, entity_type, entity_class, extra=None
):
    """Tworzy encje danego rodzaju dla wszystkich zmiennych.

    extra: funkcja (koordynator) -> lista dodatkowych encji (np. diagnostyka).
    """
    entities = []

    for coordinator in get_coordinators(hass):
        entities.extend(
            entity_class(coordinator, variable)
            for variable in coordinator.variables
            if variable["entity"] == entity_type
        )

        if extra is not None:
            entities.extend(extra(coordinator))

    async_add_entities(entities)


class NetVarEntity(Entity):
    """Bazowa encja dla zmiennych NetVar."""

    _attr_should_poll = False

    def __init__(self, coordinator, variable):
        self.coordinator = coordinator
        self.variable = variable

        self._variable_index = next(
            index
            for index, item in enumerate(coordinator.variables)
            if item is variable
        )

        self._attr_name = variable["name"]

        # unique_id zmiennej (z nazwy albo podany ręcznie) jest sprawdzany pod
        # kątem powtórzeń przy walidacji listy.
        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.ip_address}_{coordinator.port}_"
            f"{coordinator.list_id}_{coordinator.mode}_{variable['unique_id']}"
        )

        self._attr_icon = variable.get("icon")
        self._attr_force_update = variable.get("force_update", False)
        self._attr_entity_registry_enabled_default = variable.get(
            "enabled_by_default", True
        )
        self._attr_entity_registry_visible_default = variable.get(
            "visible_by_default", True
        )

        if variable.get("entity_category"):
            self._attr_entity_category = EntityCategory(
                variable["entity_category"]
            )

    @property
    def available(self):
        """Dostępność: write zawsze, read po odbiorze danych (i w czasie timeout)."""
        if self.coordinator.mode != MODE_READ:
            return True

        return self.coordinator.is_available(self._variable_index)

    async def async_added_to_hass(self):
        """Rejestracja słuchacza aktualizacji po dodaniu encji (tylko tryb read)."""
        await super().async_added_to_hass()

        if self.coordinator.mode == MODE_READ:
            self.coordinator.register_listener(self._handle_update)

    async def async_will_remove_from_hass(self):
        """Wyrejestrowanie słuchacza przed usunięciem encji."""
        self.coordinator.unregister_listener(self._handle_update)
        await super().async_will_remove_from_hass()

    def _get_value(self, payload):
        """Wyodrębnienie wartości zmiennej z bufora listy."""
        offset = self.variable["offset"]
        size = variable_size(self.variable)

        if len(payload) < offset + size:
            return None

        return decode_value(
            payload[offset:offset + size],
            self.variable["type"],
            self.variable.get("length"),
        )

    def _handle_update(self, payload, updated_indices):
        """Obsługa aktualizacji danych lub dostępności z koordynatora."""
        if self._variable_index not in updated_indices:
            return

        try:
            value = self._get_value(payload)

            if value is not None:
                self._update_value(value)

        except (ValueError, TypeError, OverflowError) as err:
            self.coordinator.count("rx_errors")
            self.coordinator.warn_throttled(
                ("decode", self._variable_index),
                "Nie można zdekodować zmiennej %s na liście %d: %s",
                self.variable["name"],
                self.coordinator.list_id,
                err,
            )

        self.async_write_ha_state()

    def _update_value(self, value):
        """Aktualizacja stanu encji (podklasy encji read)."""
