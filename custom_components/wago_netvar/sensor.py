from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import NetVarEntity


def _get_yaml_entities(hass):
    """Tworzenie encji z konfiguracji YAML."""
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

        for sensor_type in (
            "rx_packets",
            "tx_packets",
            "rx_errors",
            "tx_errors",
            "rejected_packets",
        ):
            entities.append(
                NetVarDiagnosticSensor(coordinator, sensor_type)
            )

    return entities


async def async_setup_platform(
    hass: HomeAssistant,
    config,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    """Konfiguracja platformy sensor z YAML."""
    async_add_entities(_get_yaml_entities(hass))


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
):
    """Konfiguracja platformy sensor z wpisu konfiguracyjnego."""
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

    for sensor_type in (
        "rx_packets",
        "tx_packets",
        "rx_errors",
        "tx_errors",
        "rejected_packets",
    ):
        entities.append(
            NetVarDiagnosticSensor(coordinator, sensor_type)
        )

    async_add_entities(entities)


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

        self._zero_as_unavailable = variable.get(
            "zero_as_unavailable",
            False,
        )

        self._attr_native_value = None

    def _update_value(self, value):
        """Aktualizacja wartości czujnika."""
        if self._zero_as_unavailable and value == 0:
            self._attr_native_value = None
        else:
            self._attr_native_value = value


class NetVarDiagnosticSensor(SensorEntity):
    """Czujnik diagnostyczny listy NetVar."""

    def __init__(self, coordinator, sensor_type):
        self.coordinator = coordinator
        self._sensor_type = sensor_type

        self._attr_name = (
            f"NetVar List {coordinator.list_id} {sensor_type}"
        )

        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.ip_address}_"
            f"{coordinator.port}_{coordinator.list_id}_"
            f"{sensor_type}"
        )

        self._attr_icon = "mdi:counter"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_should_poll = False
        self._attr_native_value = 0

    @property
    def native_value(self):
        return getattr(self.coordinator, self._sensor_type, 0)

    async def async_added_to_hass(self):
        self.coordinator.register_listener(
            self._handle_update
        )

    async def async_will_remove_from_hass(self):
        self.coordinator.unregister_listener(
            self._handle_update
        )

    def _handle_update(self, payload, updated_indices):
        self.schedule_update_ha_state()
