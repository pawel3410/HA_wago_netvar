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

        if coordinator.mode == "read":
            entities.append(
                NetVarPacketStatusSensor(coordinator)
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

    if coordinator.mode == "read":
        entities.append(
            NetVarPacketStatusSensor(coordinator)
        )

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


class NetVarPacketStatusSensor(SensorEntity):
    def __init__(self, coordinator):
        self.coordinator = coordinator

        self._attr_name = (
            f"NetVar List {coordinator.list_id} packet status"
        )

        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.ip_address}_"
            f"{coordinator.port}_{coordinator.list_id}_"
            "packet_status"
        )

        self._attr_icon = "mdi:package-check"
        self._attr_entity_category = None
        self._attr_should_poll = False

    @property
    def native_value(self):
        if self.coordinator.packet_complete:
            return "complete"

        return "incomplete"

    @property
    def extra_state_attributes(self):
        coordinator = self.coordinator

        received = sorted(coordinator.cycle_received)
        expected = coordinator.expected_count

        missing = sorted(
            set(range(expected)) - coordinator.cycle_received
        )

        return {
            "list_id": coordinator.list_id,
            "sequence": coordinator.current_sequence,
            "received_count": len(received),
            "expected_count": expected,
            "received_indices": received,
            "missing_indices": missing,
            "ever_received_count": len(coordinator.received),
            "packed": coordinator.pack_variables,
            "checksum_field": f"0x{coordinator.last_checksum:04X}",
        }

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
