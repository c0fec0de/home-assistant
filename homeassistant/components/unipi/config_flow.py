"""Config Flow For UniPi Integration."""
import ipaddress
import re

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import (  # pylint: disable=unused-import
    CONF_NAME,
    DEFAULT_HOST,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
    TIMEOUT,
)


def host_valid(host):
    """Return True if hostname or IP address is valid."""
    try:
        if ipaddress.ip_address(host).version == (4 or 6):
            return True
    except ValueError:
        disallowed = re.compile(r"[^a-zA-Z\d\-]")
        return all(x and not disallowed.search(x) for x in host.split("."))


async def check_connection(host, port):
    """Load UniPi Information."""
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(f"ws://{host}:{port}/ws") as websocket:
                await websocket.send_str('{"cmd": "all"}')
                msg = await websocket.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    for item in msg.json():
                        if (
                            isinstance(item, dict)
                            and "dev" in item
                            and "circuit" in item
                        ):
                            return True
    except Exception:  # pylint: disable=broad-except
        pass
    raise ConnectionError()


class UniPiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config Flow For UniPi Integration."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
        """Initialize."""
        self.name = DEFAULT_NAME
        self.host = DEFAULT_HOST
        self.port = DEFAULT_PORT

    async def async_step_user(self, user_input=None):
        """Handle The User Step."""
        errors = {}

        if user_input is not None:
            if host_valid(user_input[CONF_HOST]):
                self.name = user_input[CONF_NAME]
                self.host = user_input[CONF_HOST]
                self.port = user_input[CONF_PORT]
                try:
                    await check_connection(self.host, self.port)
                except ConnectionError:
                    errors[CONF_HOST] = "connection_error"
                else:
                    await self.async_set_unique_id(self.name.lower())
                    self._abort_if_unique_id_configured()
                    # Create Configuration Entry
                    title = self.name
                    data = {
                        CONF_NAME: self.name,
                        CONF_HOST: self.host,
                        CONF_PORT: self.port,
                    }
                    return self.async_create_entry(title=title, data=data)
            else:
                errors[CONF_HOST] = "invalid_host"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=self.name): str,
                    vol.Required(CONF_HOST, default=self.host): str,
                    vol.Required(CONF_PORT, default=self.port): str,
                }
            ),
            errors=errors,
        )
