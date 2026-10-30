import json

import voluptuous as vol

from homeassistant import config_entries

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    MODE_READ,
    MODE_WRITE,
)
from . import validate_device


class WagoNetVarConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Configuration flow for Wago NetVar."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            try:
                variables = json.loads(
                    user_input["variables_json"]
                )

                if not isinstance(variables, list):
                    raise ValueError(
                        "Variables must be a JSON list"
                    )

                device = {
                    "ip_address": user_input["ip_address"],
                    "port": user_input["port"],
                    "list_id": user_input["list_id"],
                    "mode": user_input["mode"],
                    "pack_variables": user_input["pack_variables"],
                    "variables": variables,
                }

                device = validate_device(device)

                await self.async_set_unique_id(
                    f"{device['ip_address']}_"
                    f"{device['port']}_"
                    f"{device['list_id']}"
                )

                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Wago NetVar {device['list_id']}",
                    data=device,
                )

            except Exception:
                errors["base"] = "invalid_config"

        schema = vol.Schema(
            {
                vol.Required("ip_address"): str,
                vol.Optional(
                    "port",
                    default=DEFAULT_PORT,
                ): vol.Coerce(int),
                vol.Required("list_id"): vol.Coerce(int),
                vol.Required(
                    "mode",
                    default=MODE_READ,
                ): vol.In([MODE_READ, MODE_WRITE]),
                vol.Required(
                    "pack_variables",
                    default=True,
                ): bool,
                vol.Required("variables_json"): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
