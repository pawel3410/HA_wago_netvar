
from homeassistant.components.sensor import SensorEntity
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
            if variable["entity"] == "sensor":
                entities.append(
                    NetVarSensor(coordinator, variable)
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
        NetVarSensor(coordinator, variable)
        for variable in coordinator.variables
        if variable["entity"] == "sensor"
    ]

    async_add_entities(entities)


class NetVarSensor(NetVarEntity, SensorEntity):
    def __init__(self, coordinator, variable):
        super().__init__(coordinator, variable)

        self._attr_device_class = variable.get("device_class")
        self._attr_state_class = variable.get("state_class")

        self._attr_native_unit_of_measurement = variable.get(
            "unit_of_measurement"
        )

        self._attr_suggested_display_precision = variable.get(
            "suggested_display_precision"
        )

        self._zero_as_unavailable = variable.get(
            "zero_as_unavailable",
            False,
        )

        self._attr_native_value = None

    def _update_value(self, value):
        if self._zero_as_unavailable and value == 0:
            self._attr_native_value = None
        else:
            self._attr_native_value = value
