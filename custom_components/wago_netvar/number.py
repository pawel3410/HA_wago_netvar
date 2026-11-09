import logging
import math

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import NetVarEntity, add_platform_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    """Konfiguracja platformy number z YAML."""
    add_platform_entities(hass, async_add_entities, "number", NetVarNumber)


class NetVarNumber(NetVarEntity, NumberEntity, RestoreEntity):
    """Encja number NetVar (stan optymistyczny: PLC nie potwierdza zapisu).

    restore_value: po restarcie przywracana jest ostatnia wartość i wysyłana do PLC.
    """

    _attr_assumed_state = True

    def __init__(self, coordinator, variable):
        super().__init__(coordinator, variable)

        # min, max, step i mode są uzupełnione i zweryfikowane w konfiguracji.
        self._attr_native_min_value = variable["min"]
        self._attr_native_max_value = variable["max"]
        self._attr_native_step = variable["step"]
        self._attr_mode = NumberMode(variable["mode"])
        self._attr_native_unit_of_measurement = variable.get(
            "unit_of_measurement"
        )
        self._attr_device_class = variable.get("device_class")
        self._attr_native_value = float(
            variable.get("initial_value", variable["min"])
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        if not self.variable.get("restore_value"):
            return

        last = await self.async_get_last_state()

        if last is None:
            return

        try:
            number = float(last.state)
        except (TypeError, ValueError):
            return  # "unknown" / "unavailable"

        if not math.isfinite(number) or not (
            self._attr_native_min_value <= number <= self._attr_native_max_value
        ):
            return

        self.coordinator.set_variable(self.variable, number, restore=True)
        self._attr_native_value = number
        self.coordinator.schedule_startup_send()

    async def async_set_native_value(self, value):
        number = float(value)

        if not math.isfinite(number) or not (
            self._attr_native_min_value <= number <= self._attr_native_max_value
        ):
            raise HomeAssistantError(
                f"Wartość {value} jest poza zakresem "
                f"{self._attr_native_min_value}..{self._attr_native_max_value}"
            )

        try:
            self.coordinator.set_variable(self.variable, number)
        except (ValueError, OSError) as err:
            _LOGGER.error(
                "Nie można ustawić %s na %s: %s",
                self.variable["name"],
                number,
                err,
            )
            raise HomeAssistantError(
                f"Nie można wysłać wartości do PLC: {err}"
            ) from err

        self._attr_native_value = number
        self.async_write_ha_state()
