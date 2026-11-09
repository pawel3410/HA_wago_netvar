import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .codec import to_bool
from .entity import NetVarEntity, add_platform_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    """Konfiguracja platformy switch z YAML."""
    add_platform_entities(hass, async_add_entities, "switch", NetVarSwitch)


class NetVarSwitch(NetVarEntity, SwitchEntity, RestoreEntity):
    """Przełącznik NetVar (stan optymistyczny: PLC nie potwierdza zapisu).

    restore_value: po restarcie przywracany jest ostatni stan i wysyłany do PLC.
    """

    _attr_assumed_state = True

    def __init__(self, coordinator, variable):
        super().__init__(coordinator, variable)

        self._attr_device_class = variable.get("device_class")
        self._attr_is_on = to_bool(variable.get("initial_value", False))

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        if not self.variable.get("restore_value"):
            return

        last = await self.async_get_last_state()

        if last is None or last.state not in ("on", "off"):
            return

        state = last.state == "on"

        self.coordinator.set_variable(self.variable, state, restore=True)
        self._attr_is_on = state
        self.coordinator.schedule_startup_send()

    async def _async_set(self, state):
        try:
            self.coordinator.set_variable(self.variable, state)
        except (ValueError, OSError) as err:
            _LOGGER.error(
                "Nie można ustawić %s na %s: %s",
                self.variable["name"],
                state,
                err,
            )
            raise HomeAssistantError(
                f"Nie można wysłać wartości do PLC: {err}"
            ) from err

        self._attr_is_on = state
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        await self._async_set(True)

    async def async_turn_off(self, **kwargs):
        await self._async_set(False)
