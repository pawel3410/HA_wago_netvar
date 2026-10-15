import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    CONF_IP_ADDRESS,
    CONF_PORT,
    CONF_COB_ID,
    CONF_VAR_COUNT,
    CONF_BIG_ENDIAN,
)

class WagoNetVarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Obsługa konfiguracji integracji Wago NetVar przez interfejs UI."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title=f"NetVar (COB-ID: {user_input[CONF_COB_ID]})",
                data=user_input
            )

        schema = vol.Schema({
            vol.Required(CONF_IP_ADDRESS): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Required(CONF_COB_ID, default=1): int,
            vol.Optional(CONF_VAR_COUNT, default=1): int,
            vol.Optional(CONF_BIG_ENDIAN, default=True): bool,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
