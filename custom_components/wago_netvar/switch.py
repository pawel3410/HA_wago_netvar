
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import NetVarEntity


_LOGGER = logging.getLogger(__name__)


def _get_yaml_entities(hass):
    entities = []

    devices = hass.data.get(DOMAIN, {}).get("devices", {})

    for device in devices.values():
        if device.get("source") != "yaml":
            continue

        coordinator = device["coordinator"]

        for variable in coordinator.variables:
            if variable["entity"] == "switch":
                entities.append(
                    NetVarSwitch(coordinator, variable)
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
        NetVarSwitch(coordinator, variable)
        for variable in coordinator.variables
        if variable["entity"] == "switch"
    ]

    async_add_entities(entities)


class NetVarSwitch(NetVarEntity, SwitchEntity):
    def __init__(self, coordinator, variable):
        super().__init__(coordinator, variable)

        self._attr_device_class = variable.get("device_class")
        self._attr_is_on = bool(
            variable.get("initial_value", False)
        )

    def _update_value(self, value):
        self._attr_is_on = bool(value)

    async def async_turn_on(self, **kwargs):
        try:
            self.coordinator.set_variable(
                self.variable,
                True,
            )

        except (ValueError, OSError) as err:
            _LOGGER.error(
                "Cannot turn on %s: %s",
                self.variable["name"],
                err,
            )
            raise HomeAssistantError(
                f"Cannot send value to PLC: {err}"
            ) from err

        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        try:
            self.coordinator.set_variable(
                self.variable,
                False,
            )

        except (ValueError, OSError) as err:
            _LOGGER.error(
                "Cannot turn off %s: %s",
                self.variable["name"],
                err,
            )
            raise HomeAssistantError(
                f"Cannot send value to PLC: {err}"
            ) from err

        self._attr_is_on = False
        self.async_write_ha_state()
