import logging
import math

from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import NetVarEntity


_LOGGER = logging.getLogger(__name__)


def _get_yaml_entities(hass):
    """Tworzenie encji number z konfiguracji YAML."""
    entities = []

    devices = hass.data.get(DOMAIN, {}).get("devices", {})

    for device in devices.values():
        if device.get("source") != "yaml":
            continue

        coordinator = device["coordinator"]

        for variable in coordinator.variables:
            if variable["entity"] == "number":
                entities.append(
                    NetVarNumber(coordinator, variable)
                )

    return entities


async def async_setup_platform(
    hass: HomeAssistant,
    config,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    """Konfiguracja platformy number z YAML."""
    async_add_entities(_get_yaml_entities(hass))


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
):
    """Konfiguracja platformy number z wpisu konfiguracyjnego."""
    device = hass.data.get(DOMAIN, {}).get("devices", {}).get(
        entry.entry_id
    )

    if not device:
        return

    coordinator = device["coordinator"]

    entities = [
        NetVarNumber(coordinator, variable)
        for variable in coordinator.variables
        if variable["entity"] == "number"
    ]

    async_add_entities(entities)


class NetVarNumber(NetVarEntity, NumberEntity):
    """Encja number dla zmiennych NetVar."""

    def __init__(self, coordinator, variable):
        super().__init__(coordinator, variable)

        self._attr_native_min_value = float(
            variable.get("min", 0)
        )

        self._attr_native_max_value = float(
            variable.get("max", 100)
        )

        self._attr_native_step = float(
            variable.get("step", 1)
        )

        self._attr_native_unit_of_measurement = variable.get(
            "unit_of_measurement"
        )

        self._attr_device_class = variable.get("device_class")

        initial_value = float(
            variable.get("initial_value", 0)
        )

        if not math.isfinite(initial_value):
            initial_value = self._attr_native_min_value

        self._attr_native_value = min(
            max(
                initial_value,
                self._attr_native_min_value,
            ),
            self._attr_native_max_value,
        )

    def _update_value(self, value):
        try:
            number = float(value)

        except (TypeError, ValueError, OverflowError):
            return

        if not math.isfinite(number):
            return

        self._attr_native_value = min(
            max(
                number,
                self._attr_native_min_value,
            ),
            self._attr_native_max_value,
        )

    async def async_set_native_value(self, value):
        try:
            number = float(value)

        except (TypeError, ValueError, OverflowError) as err:
            raise HomeAssistantError(
                "Nieprawidłowa wartość numeryczna"
            ) from err

        if not math.isfinite(number):
            raise HomeAssistantError(
                "Wartość numeryczna musi być skończona"
            )

        if number < self._attr_native_min_value:
            raise HomeAssistantError(
                "Wartość jest poniżej minimum"
            )

        if number > self._attr_native_max_value:
            raise HomeAssistantError(
                "Wartość jest powyżej maksimum"
            )

        try:
            self.coordinator.set_variable(
                self.variable,
                number,
            )

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
