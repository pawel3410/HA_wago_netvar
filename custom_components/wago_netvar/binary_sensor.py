from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import NetVarEntity, add_platform_entities


async def async_setup_platform(
    hass: HomeAssistant,
    config,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    """Konfiguracja platformy binary_sensor z YAML."""
    add_platform_entities(
        hass, async_add_entities, "binary_sensor", NetVarBinarySensor
    )


class NetVarBinarySensor(NetVarEntity, BinarySensorEntity):
    """Czujnik binarny NetVar."""

    def __init__(self, coordinator, variable):
        super().__init__(coordinator, variable)

        self._attr_device_class = variable.get("device_class")
        self._attr_is_on = None

    def _update_value(self, value):
        self._attr_is_on = bool(value)
