
import ipaddress

import voluptuous as vol

from homeassistant import config_entries

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    MODE_READ,
    MODE_WRITE,
    TYPE_SIZES,
    READ_ENTITIES,
    WRITE_ENTITIES,
)
from . import validate_device


def _validate_ip_address(value):
    value = str(value).strip()

    try:
        ipaddress.ip_address(value)
    except ValueError:
        raise vol.Invalid("Invalid IP address")

    return value


class WagoNetVarConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Configuration flow for Wago NetVar."""

    VERSION = 1

    def __init__(self):
        self._data = {}
        self._variables = []

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            self._data = dict(user_input)
            self._variables = []

            return await self.async_step_variables()

        schema = vol.Schema(
            {
                vol.Required("ip_address"): _validate_ip_address,

                vol.Required(
                    "port",
                    default=DEFAULT_PORT,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=65535),
                ),

                vol.Required("list_id"): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0, max=65535),
                ),

                vol.Required(
                    "mode",
                    default=MODE_READ,
                ): vol.In([MODE_READ, MODE_WRITE]),

                vol.Required(
                    "pack_variables",
                    default=True,
                ): bool,

                vol.Required(
                    "transmit_checksum",
                    default=False,
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_variables(self, user_input=None):
        return self.async_show_menu(
            step_id="variables",
            menu_options=[
                "add_variable",
                "finish",
            ],
        )

    async def async_step_add_variable(self, user_input=None):
        errors = {}

        if user_input is not None:
            variable = {
                "name": user_input["name"].strip(),
                "offset": user_input["offset"],
                "type": user_input["type"],
                "entity": user_input["entity"],
                "initial_value": user_input["initial_value"],
                "enabled_by_default": user_input[
                    "enabled_by_default"
                ],
                "force_update": user_input["force_update"],
            }

            for key in (
                "device_class",
                "state_class",
                "unit_of_measurement",
                "icon",
                "zero_as_unavailable",
                "min",
                "max",
                "step",
            ):
                if key in user_input:
                    variable[key] = user_input[key]

            if variable["entity"] != "number":
                variable.pop("min", None)
                variable.pop("max", None)
                variable.pop("step", None)

            if variable["entity"] != "sensor":
                variable.pop("zero_as_unavailable", None)

            self._variables.append(variable)

            return await self.async_step_variables()

        if self._data.get("mode") == MODE_READ:
            entity_options = list(READ_ENTITIES)
        else:
            entity_options = list(WRITE_ENTITIES)

        schema = vol.Schema(
            {
                vol.Required("name"): str,

                vol.Required("offset"): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0),
                ),

                vol.Required("type"): vol.In(
                    sorted(TYPE_SIZES.keys())
                ),

                vol.Required("entity"): vol.In(
                    entity_options
                ),

                vol.Required(
                    "initial_value",
                    default="0",
                ): str,

                vol.Optional("device_class"): str,
                vol.Optional("state_class"): str,
                vol.Optional("unit_of_measurement"): str,
                vol.Optional("icon"): str,

                vol.Optional(
                    "enabled_by_default",
                    default=True,
                ): bool,

                vol.Optional(
                    "force_update",
                    default=False,
                ): bool,

                vol.Optional(
                    "zero_as_unavailable",
                    default=False,
                ): bool,

                vol.Optional("min"): vol.Coerce(float),
                vol.Optional("max"): vol.Coerce(float),
                vol.Optional("step"): vol.Coerce(float),
            }
        )

        return self.async_show_form(
            step_id="add_variable",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_finish(self, user_input=None):
        errors = {}

        if user_input is not None:
            if not self._variables:
                errors["base"] = "no_variables"

            else:
                device = dict(self._data)
                device["variables"] = list(self._variables)

                try:
                    device = validate_device(device)

                    await self.async_set_unique_id(
                        f"{device['ip_address']}_"
                        f"{device['port']}_"
                        f"{device['list_id']}"
                    )

                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=(
                            f"Wago NetVar "
                            f"{device['list_id']}"
                        ),
                        data=device,
                    )

                except vol.Invalid:
                    errors["base"] = "invalid_config"

                except (ValueError, TypeError, KeyError):
                    errors["base"] = "invalid_config"

        schema = vol.Schema(
            {
                vol.Required(
                    "confirm",
                    default=True,
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="finish",
            data_schema=schema,
            errors=errors,
        )
