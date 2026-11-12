from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .codec import DIAGNOSTIC_SENSORS, DOMAIN, TOTAL_SENSORS, format_temporal
from .entity import NetVarEntity, add_platform_entities, get_coordinators


def _diagnostic_sensors(coordinator):
    """Sensory diagnostyczne tworzone automatycznie dla każdej listy."""
    return [
        NetVarDiagnosticSensor(coordinator, sensor_type)
        for sensor_type in DIAGNOSTIC_SENSORS[coordinator.mode]
    ]


async def async_setup_platform(
    hass: HomeAssistant,
    config,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    """Konfiguracja platformy sensor z YAML."""
    add_platform_entities(
        hass, async_add_entities, "sensor", NetVarSensor,
        extra=_diagnostic_sensors,
    )

    # Sumy liczników wszystkich list (jeden zestaw sensorów, niezależnie od liczby list).
    if get_coordinators(hass):
        async_add_entities(
            [NetVarTotalSensor(hass, name, counter)
             for name, counter in TOTAL_SENSORS.items()]
        )


class NetVarSensor(NetVarEntity, SensorEntity):
    """Czujnik NetVar."""

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
        self._attr_suggested_unit_of_measurement = variable.get(
            "suggested_unit_of_measurement"
        )
        self._zero_as_unavailable = variable.get("zero_as_unavailable", False)
        # Typy czasowe (TIME, DATE, TOD, DT) w formacie text są pokazywane jako tekst IEC.
        self._as_text = variable.get("format") == "text"
        self._attr_native_value = None

    def _update_value(self, value):
        """Aktualizacja wartości czujnika."""
        if self._zero_as_unavailable and value == 0:
            self._attr_native_value = None
        elif self._as_text:
            self._attr_native_value = format_temporal(
                self.variable["type"], value
            )
        else:
            self._attr_native_value = value


class NetVarDiagnosticSensor(SensorEntity):
    """Licznik diagnostyczny listy NetVar."""

    _attr_should_poll = False
    _attr_icon = "mdi:counter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, sensor_type):
        self.coordinator = coordinator
        self._sensor_type = sensor_type

        self._attr_name = f"{sensor_type}_{coordinator.list_id}"
        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.ip_address}_{coordinator.port}_"
            f"{coordinator.list_id}_{coordinator.mode}_{sensor_type}"
        )

    @property
    def native_value(self):
        return getattr(self.coordinator, self._sensor_type, 0)

    async def async_added_to_hass(self):
        self.coordinator.register_diagnostic_listener(self._handle_diagnostic)

    async def async_will_remove_from_hass(self):
        self.coordinator.unregister_diagnostic_listener(self._handle_diagnostic)

    def _handle_diagnostic(self):
        self.async_write_ha_state()


class NetVarTotalSensor(SensorEntity):
    """Suma licznika diagnostycznego ze wszystkich list NetVar (np. total_rx_packets)."""

    _attr_should_poll = False
    _attr_icon = "mdi:counter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, hass, name, counter):
        self._hass = hass
        self._counter = counter

        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{name}"

    @property
    def native_value(self):
        return sum(
            getattr(coordinator, self._counter, 0)
            for coordinator in get_coordinators(self._hass)
        )

    async def async_added_to_hass(self):
        for coordinator in get_coordinators(self._hass):
            coordinator.register_diagnostic_listener(self._handle_diagnostic)

    async def async_will_remove_from_hass(self):
        for coordinator in get_coordinators(self._hass):
            coordinator.unregister_diagnostic_listener(self._handle_diagnostic)

    def _handle_diagnostic(self):
        self.async_write_ha_state()
