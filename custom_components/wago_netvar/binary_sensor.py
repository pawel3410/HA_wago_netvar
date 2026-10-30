
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import NetVarEntity


def _get_yaml_entities(hass):
    entities = []

    devices = hass.data.get(DOMAIN, {}).get("devices", {})

    for device in devices.values():
        if device.get("source") != "yaml":
            continue

        coordinator = device["coordinator"]

        for variable in coordinator.variables:
            if variable["entity"] == "binary_sensor":
                entities.append(
                    NetVarBinarySensor(coordinator, variable)
                )

    return entities


async def async_setup_platform(
    hass: HomeAssistant,
    config,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    async_add_entities(_get_yaml_entities(hass))


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
):
    device = hass.data.get(DOMAIN, {}).get("devices", {}).get(
        entry.entry_id
    )

    if not device:
        return

    coordinator = device["coordinator"]

    entities = [
        NetVarBinarySensor(coordinator, variable)
        for variable in coordinator.variables
        if variable["entity"] == "binary_sensor"
    ]

    async_add_entities(entities)


class NetVarBinarySensor(NetVarEntity, BinarySensorEntity):
    def __init__(self, coordinator, variable):
        super().__init__(coordinator, variable)

        self._attr_device_class = variable.get("device_class")
        self._attr_is_on = None

    def _update_value(self, value):
        self._attr_is_on = bool(value)
