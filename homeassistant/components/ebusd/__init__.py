"""Support for Ebusd daemon for communication with eBUS heating systems."""
import logging
import socket

import voluptuous as vol

from homeassistant.const import (
    CONF_HOST,
    CONF_MONITORED_CONDITIONS,
    CONF_NAME,
    CONF_PORT,
    CONF_TIMEOUT,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import load_platform

from .const import (
    CONF_CIRCUIT,
    CONF_CIRCUITMAP,
    CONF_POLL_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .data import Data

_LOGGER = logging.getLogger(__name__)


SERVICE_EBUSD_WRITE = "ebusd_write"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            vol.All(
                {
                    vol.Required(CONF_HOST): cv.string,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                    vol.Optional(CONF_CIRCUITMAP, default={}): vol.All(),
                    vol.Required(
                        CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
                    ): cv.positive_int,
                    vol.Required(
                        CONF_TIMEOUT, default=DEFAULT_TIMEOUT
                    ): cv.positive_int,
                    # legacy
                    vol.Optional(CONF_CIRCUIT): cv.string,
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                    vol.Optional(CONF_MONITORED_CONDITIONS, default=[]): cv.ensure_list,
                }
            )
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_entry(hass, entry):
    """Set up a config entry for Unipi."""
    return True


async def async_setup(hass, config):
    """Set up the eBusd component."""
    conf = config[DOMAIN]
    host = conf[CONF_HOST]
    port = conf[CONF_PORT]
    circuitmap = conf[CONF_CIRCUITMAP]
    poll_interval = conf[CONF_POLL_INTERVAL]
    timeout = conf[CONF_TIMEOUT]
    # legacy
    circuit = conf.get(CONF_CIRCUIT, None)
    if circuit:
        circuitmap[circuit] = conf[CONF_NAME]
    # monitored_conditions = conf.get(CONF_MONITORED_CONDITIONS)
    data = Data(host, port, circuitmap, poll_interval, timeout)
    hass.data[DOMAIN] = data
    try:
        await data.async_setup()

        load_platform(hass, "sensor", DOMAIN, None, config)

        # hass.services.register(DOMAIN, SERVICE_EBUSD_WRITE, data.write)

        _LOGGER.debug("setup:   completed")
        return True
    except (socket.timeout, socket.error) as err:
        _LOGGER.error(err)
        return False
