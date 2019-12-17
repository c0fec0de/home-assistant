"""Support for Ebusd daemon for communication with eBUS heating systems."""
from datetime import timedelta
import logging
import socket

import ebus
import voluptuous as vol

from homeassistant.const import (
    CONF_HOST,
    CONF_MONITORED_CONDITIONS,
    CONF_NAME,
    CONF_PORT,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import load_platform
from homeassistant.util import Throttle

from .const import DOMAIN, CONF_CIRCUIT, CONF_CIRCUITMAP, DEFAULT_PORT, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)


# SERVICE_EBUSD_WRITE = "ebusd_write"

# MONITOR_SCHEMA = vol.Schema(
#     {
#         vol.Required(CONF_KNX_EXPOSE_TYPE): cv.string,
#         vol.Optional(CONF_ENTITY_ID): cv.entity_id,
#         vol.Required(CONF_KNX_EXPOSE_ADDRESS): cv.string,
#     }
# )

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            vol.All(
                {
                    vol.Required(CONF_HOST): cv.string,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                    vol.Optional(CONF_CIRCUIT): cv.string,
                    vol.Optional(CONF_MONITORED_CONDITIONS, default=[]): cv.ensure_list,
                    # vol.Optional(CONF_CIRCUITMAP, default={}): cv.ensure_list,
                }
            )
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Set up the eBusd component."""
    conf = config[DOMAIN]
    host = conf[CONF_HOST]
    name = conf[CONF_NAME]
    circuit = conf[CONF_CIRCUIT]
    monitored_conditions = conf.get(CONF_MONITORED_CONDITIONS)
    circuitmap = {}
    hass.data[DOMAIN] = data = Data(host, port, name, circuit, monitored_conditions, circuitmap)

    try:
        _LOGGER.debug("setup started")
        await data.async_connect()

#         sensor_config = {
#             CONF_MONITORED_CONDITIONS: monitored_conditions,
#             "client_name": name,
#             "sensor_types": SENSOR_TYPES[circuit],
#         }
#         load_platform(hass, "sensor", DOMAIN, sensor_config, config)

        # TODO
        # hass.services.register(DOMAIN, SERVICE_EBUSD_WRITE, data.write)

        _LOGGER.debug("setup completed")
        return True
    except (socket.timeout, socket.error):
        return False


class Data:

    """Data Handler."""

    def __init__(self, host, port, name, circuit, monitored_conditions, circuitmap):
        self.host = host
        self.port = port
        self.name = name
        self.circuit = circuit
        self.monitored_conditions = monitored_conditions
        self.circuitmap = circuitmap
        self.connection = ebus.Connection(host, port)

    async def async_connect(self):
        await self.connection.connect()

    #     @Throttle(MIN_TIME_BETWEEN_UPDATES)
    #     def update(self, name, stype):
    #         """Call the Ebusd API to update the data."""
    #         try:
    #             _LOGGER.debug("Opening socket to ebusd %s", name)
    #             command_result = ebusdpy.read(
    #                 self._address, self._circuit, name, stype, CACHE_TTL
    #             )
    #             if command_result is not None:
    #                 if "ERR:" in command_result:
    #                     _LOGGER.warning(command_result)
    #                 else:
    #                     self.value[name] = command_result
    #         except RuntimeError as err:
    #             _LOGGER.error(err)
    #             raise RuntimeError(err)

    async def async_write(self, call):
        """Call write methon on ebusd."""
        circuit = call.data.get("circuit", self.circuit)
        name = call.data.get("name")
        value = call.data.get("value")

        try:
            await self.connection.write(name, circuit, value)
        except RuntimeError as err:
            _LOGGER.error(f"ebusd_write(name={name}, circuit={circuit}, value={value}) FAILED")
            _LOGGER.error(err)
