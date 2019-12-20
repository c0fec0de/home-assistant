"""Support for Ebusd daemon for communication with eBUS heating systems."""
import asyncio
import collections
import logging
import socket
import time

import ebus
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

WAIT_MAX = 60

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
    hass.data[DOMAIN] = data = Data(host, port, circuitmap, poll_interval, timeout)
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

    def __init__(self, host, port, circuitmap, poll_interval, timeout):
        """Container."""
        self.circuitmap = ebus.CircuitMap(circuitmap)
        self.query = ebus.Connection(host, port)
        self.writer = ebus.Connection(host, port, autoconnect=True)
        self.monitor = ebus.Connection(host, port)
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.fields = ebus.Fields()
        self.units = ebus.UNITS
        self.decoder = ebus.Decoder(self.fields, self.units)
        self.monitors = []
        self.states = {}
        self.attrs = {}
        self.available = {}
        self.lastseen = {}
        self.observers = collections.defaultdict(list)

    async def async_setup(self):
        """Connect and start monitoring."""
        if self.poll_interval:
            asyncio.ensure_future(self.async_query())
        asyncio.ensure_future(self.async_monitor())

        self.fields.load()
        self.reset_states()

    def reset_states(self):
        """Reset all states."""
        for circuit in self.circuitmap.iter_circuits():
            for field in self.fields.get(circuit):
                circuitfield = circuit, field
                self.monitors.append(circuitfield)
                self.states[circuitfield] = None
                self.attrs[circuitfield] = {}
                self.available[circuitfield] = None
                self.lastseen[circuitfield] = None

    async def async_monitor(self):
        """Monitor."""
        monitor = self.monitor
        wait = 1
        while True:
            try:
                await monitor.connect()
                await monitor.start_listening(verbose=True)
                _LOGGER.info("Monitor: started.")
                wait = 1
                while True:
                    line = await monitor.receive()
                    _LOGGER.debug(f"Monitor: {line!r}")
                    try:
                        for value in self.decoder.decode(line):
                            await self._update(value)
                            _LOGGER.info(
                                f"Monitor: {value.circuit}: {value.field.title}={value.value}"
                            )
                    except (ValueError, ebus.decoder.FormatError) as err:
                        _LOGGER.error(f"Monitor: Decode failed: {err}")
                    except ebus.decoder.UnknownError as err:
                        _LOGGER.warn(f"Monitor: Decode failed: {err}")
            except OSError as err:
                if wait == WAIT_MAX:
                    self.reset_states()
                    for methods in self.observers.values():
                        for method in methods:
                            await method()
                    _LOGGER.error(
                        f"Monitor: {err}, will retry every {wait} seconds, states reset"
                    )
                    wait += 1
                else:
                    _LOGGER.error(f"Monitor: {err}, retry in {wait} seconds")
                    wait = min(2 * wait, WAIT_MAX)
                await asyncio.sleep(wait)
            finally:
                await monitor.disconnect()

    async def async_query(self):
        """Query."""
        query = self.query
        wait = 1
        while True:
            try:
                await query.connect()
                _LOGGER.info("Query:   started.")
                await asyncio.sleep(self.poll_interval)
                wait = 1
                while True:
                    for circuitfield in tuple(self.states):
                        circuit, field = circuitfield
                        if (self.lastseen[circuitfield] or 0) > (
                            time.time() - self.timeout
                        ):  # not outdated
                            continue
                        if (
                            self.available[circuitfield] is False
                        ):  # skip non-available ones
                            continue
                        if (
                            self.available[circuitfield] and field.status
                        ):  # skip auto-update
                            continue
                        try:
                            line = await self.query.read(
                                field.name,
                                circuit=circuit,
                                ttl=self.timeout,
                                verbose=True,
                            )
                            _LOGGER.debug(f"Query:   {line!r}")
                            try:
                                for value in self.decoder.decode(line):
                                    await self._update(value)
                                    _LOGGER.info(
                                        f"Query:   {value.circuit}: {value.field.title}={value.value}"
                                    )
                            except (ValueError, ebus.decoder.FormatError) as err:
                                self.available[circuitfield] = False
                                _LOGGER.error(f"Monitor: Decode failed: {err}")
                            except ebus.decoder.UnknownError as err:
                                self.available[circuitfield] = False
                                _LOGGER.warn(f"Monitor: Decode failed: {err}")
                        except ebus.connection.CommandError:
                            self.available[circuitfield] = False
                            _LOGGER.warn(
                                f"{circuit} {field.name} ({field.title}) not available on this EBUS installation"
                            )
                        # slow-down
                        await asyncio.sleep(self.poll_interval)
                    idle = self.timeout
                    for (circuit, field), available in self.available.items():
                        if field.status:
                            ago = int(time.time() - self.lastseen[(circuit, field)])
                            _LOGGER.debug(
                                f"Query:   {circuit} {field.name} ({field.title}): monitored and seen {ago}s ago"
                            )
                        elif available:
                            ago = int(time.time() - self.lastseen[(circuit, field)])
                            idle = min(idle, max(self.timeout - ago, 0))
                            _LOGGER.debug(
                                f"Query:   {circuit} {field.name} ({field.title}): seen {ago}s ago"
                            )
                        else:
                            _LOGGER.debug(
                                f"Query:   {circuit} {field.name} ({field.title}): Not available, SKIP"
                            )
                    _LOGGER.info(f"Query:   wait for {idle}s")
                    await asyncio.sleep(idle)
            except OSError as err:
                if wait == WAIT_MAX:
                    _LOGGER.error(f"Query:   {err}, will retry every {wait} seconds")
                    wait += 1
                else:
                    _LOGGER.error(f"Query:   {err}, retry in {wait} seconds")
                    wait = min(2 * wait, WAIT_MAX)
                await asyncio.sleep(wait)
            finally:
                await query.disconnect()

    def add_observer(self, circuit, field, method):
        """
        Add observer.

        `method` is called, whenever self.states[circuit] changes.
        """
        self.observers[(circuit, field)].append(method)

    async def _update(self, value):
        circuitfield = value.circuit, value.field
        self.states[circuitfield] = value.value
        self.attrs[circuitfield] = value.attrs
        self.available[circuitfield] = True
        self.lastseen[circuitfield] = time.time()
        for method in self.observers[circuitfield]:
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
            await self.writer.write(name, circuit, value)
        except RuntimeError as err:
            _LOGGER.error(
                f"ebusd_write(name={name}, circuit={circuit}, value={value}) FAILED"
            )
            _LOGGER.error(err)
