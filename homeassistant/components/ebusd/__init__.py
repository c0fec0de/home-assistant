"""Support for Ebusd daemon for communication with eBUS heating systems."""
import asyncio
import collections
import datetime
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

from .const import CONF_CIRCUIT, CONF_CIRCUITMAP, DEFAULT_NAME, DEFAULT_PORT, DOMAIN

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
                    vol.Optional(CONF_CIRCUITMAP, default={}): vol.All(),
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
    # legacy
    circuit = conf.get(CONF_CIRCUIT, None)
    if circuit:
        circuitmap[circuit] = conf[CONF_NAME]
    # monitored_conditions = conf.get(CONF_MONITORED_CONDITIONS)
    hass.data[DOMAIN] = data = Data(host, port, circuitmap)
    try:
        _LOGGER.debug("setup() started")
        await data.async_setup()

        load_platform(hass, "sensor", DOMAIN, None, config)

        # TODO
        # hass.services.register(DOMAIN, SERVICE_EBUSD_WRITE, data.write)

        _LOGGER.debug("setup() completed")
        return True
    except (socket.timeout, socket.error) as err:
        _LOGGER.error(err)
        return False


class Data:
    """Data Handler."""

    def __init__(self, host, port, circuitmap):
        """Container."""
        self.circuitmap = ebus.CircuitMap(circuitmap)
        self.connection = ebus.Connection(host, port)
        self.monitor = ebus.Connection(host, port)
        self.fields = ebus.Fields()
        self.units = ebus.UNITS
        self.monitors = []
        self.values = {}
        self.available = {}
        self.lastseen = {}
        self.observers = collections.defaultdict(list)

    async def async_setup(self):
        """Connect and start monitoring."""
        await self.connection.connect()
        asyncio.ensure_future(self.async_monitor())

        self.fields.load()

        for circuit in self.circuitmap.iter_circuits():
            for field in self.fields.get(circuit):
                circuitfield = circuit, field
                self.monitors.append(circuitfield)
                self.values[circuitfield] = None
                self.available[circuitfield] = None
                self.lastseen[circuitfield] = None

    async def async_monitor(self):
        """Monitor."""
        monitor = self.monitor
        decoder = ebus.Decoder(self.fields, self.units)
        await monitor.connect()
        await monitor.start_listening(verbose=True)
        while True:
            line = await monitor.receive()
            for item in decoder.decode(line):
                await self._update(item.circuit, item.field, item.value)

    def add_observer(self, circuit, field, method):
        """
        Add observer.

        `method` is called, whenever self.values[circuit] changes.
        """
        self.observers[(circuit, field)].append(method)

    async def _update(self, circuit, field, value):
        self.values[(circuit, field)] = value
        self.available[(circuit, field)] = True
        self.lastseen[(circuit, field)] = datetime.datetime.now()
        for method in self.observers[(circuit, field)]:
            await method()

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
            _LOGGER.error(
                f"ebusd_write(name={name}, circuit={circuit}, value={value}) FAILED"
            )
            _LOGGER.error(err)
