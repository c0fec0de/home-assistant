"""EBUS Data Container."""
import asyncio
import collections
import logging
import time

import ebus

from .const import WAIT_MAX

_LOGGER = logging.getLogger(__name__)


class Data:
    """Data Container."""

    def __init__(self, host, port, circuitmap, poll_interval, timeout):
        """Container."""
        self.host = host
        self.port = port
        self.circuitmap = ebus.CircuitMap(circuitmap)
        self.writer = ebus.Connection(host, port, autoconnect=True)
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.fields = ebus.Fields()
        self.units = ebus.UNITS
        self.decoder = ebus.Decoder(self.fields, self.units)
        self.status = {}
        self.statussensor = None
        self.monitors = []
        self.states = {}
        self.attrs = {}
        self.available = {}
        self.lastseen = {}
        self.observers = collections.defaultdict(list)

    async def async_setup(self):
        """Connect and start monitoring and query."""
        if self.poll_interval:
            asyncio.ensure_future(self.async_query())
        asyncio.ensure_future(self.async_monitor())
        asyncio.ensure_future(self.async_statusmonitor())

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

    def add_observer(self, circuit, field, method):
        """
        Add entity as observer.

        This is a hookup for all entities, to register their update method.
        `method` is called, whenever self.states[circuit] changes.
        """
        self.observers[(circuit, field)].append(method)

    async def update(self, value):
        """Update `value`."""
        circuitfield = value.circuit, value.field
        self.states[circuitfield] = value.value
        self.attrs[circuitfield] = value.attrs
        self.available[circuitfield] = True
        self.lastseen[circuitfield] = time.time()
        for method in self.observers[circuitfield]:
            await method()

    async def async_write(self, call):
        """Call write methon on ebusd."""
        circuit = call.data.get("circuit", self.circuit)
        name = call.data.get("name")
        value = call.data.get("value")
        try:
            await self.writer.write(name, circuit, value)
        except RuntimeError as err:
            _LOGGER.error(
                f"ebusd_write(circuit={circuit}, name={name}, " f"value={value}) FAILED"
            )
            _LOGGER.error(err)

    async def async_monitor(self):
        """Monitor."""
        connection = ebus.Connection(self.host, self.port)
        connection.wait = 1
        while True:
            try:
                # listen
                await connection.connect()
                await ebus.commands.start_listening(connection, verbose=True)
                _LOGGER.info("Monitor: started.")
                connection.wait = 1
                while True:
                    # handle changed values
                    line = await connection.readline()
                    _LOGGER.debug(f"Monitor: {line!r}")
                    try:
                        # decode
                        for value in self.decoder.decode(line):
                            await self.update(value)
                            _LOGGER.info(
                                f"Monitor: {value.circuit}: "
                                f"{value.field.title}={value.value}"
                            )
                    except (ValueError, ebus.decoder.FormatError) as err:
                        _LOGGER.error(f"Monitor: Decode failed: {err}")
                    except ebus.decoder.UnknownError as err:
                        _LOGGER.warn(f"Monitor: Decode failed: {err}")
            except OSError as err:
                await _handle_abort(self, connection, "Monitor", err)
            finally:
                await connection.disconnect()

    async def async_query(self):
        """Query."""
        connection = ebus.Connection(self.host, self.port)
        connection.wait = 1
        while True:
            try:
                await connection.connect()
                _LOGGER.info("Query  : started.")
                await asyncio.sleep(self.poll_interval)
                connection.wait = 1
                while True:
                    await _query(self, connection)
                    # report
                    idle = self.timeout
                    for (circuit, field), available in self.available.items():
                        if not field.status and available:
                            lastseen = self.lastseen[(circuit, field)]
                            ago = int(time.time() - lastseen)
                            idle = min(idle, max(self.timeout - ago, 0))
                    _LOGGER.info(f"Query  : wait for {idle}s")
                    await asyncio.sleep(idle)
            except OSError as err:
                await _handle_abort(self, connection, "Query  ", err)
            finally:
                await connection.disconnect()

    async def async_statusmonitor(self):
        """Status Monitor."""
        connection = ebus.Connection(self.host, self.port)
        _LOGGER.info("Status : started.")
        while True:
            try:
                await connection.connect()
                self.status = await ebus.commands.info(connection)
                if self.statussensor:
                    self.statussensor.update()
                    await self.statussensor.async_update_ha_state()
                await asyncio.sleep(self.poll_interval)
            except OSError as err:
                await _handle_abort(self, connection, "Status ", err)
            finally:
                await connection.disconnect()


async def _query(data, connection):
    for circuitfield in tuple(data.states):
        circuit, field = circuitfield
        # skip if not outdated
        if (data.lastseen[circuitfield] or 0) > (time.time() - data.timeout):
            continue
        # skip non-available ones
        if data.available[circuitfield] is False:
            continue
        # skip auto-update
        if data.available[circuitfield] and field.status:
            continue
        # slow-down
        await asyncio.sleep(data.poll_interval)
        try:
            # read field
            line = await ebus.commands.read(
                connection, field.name, circuit=circuit, ttl=0, verbose=True
            )
            _LOGGER.debug(f"Query  : {line!r}")
        except ebus.connection.CommandError as err:
            if str(err) != "no signal":
                data.available[circuitfield] = False
                _LOGGER.warn(
                    f"{circuit} {field.name} ({field.title}) "
                    "not available on this EBUS installation"
                )
            continue
        # decode
        try:
            for value in data.decoder.decode(line):
                await data.update(value)
                _LOGGER.info(
                    f"Query  : {value.circuit}: " f"{value.field.title}={value.value}"
                )
        except (ValueError, ebus.decoder.FormatError) as err:
            data.available[circuitfield] = False
            _LOGGER.error(f"Monitor: Decode failed: {err}")
        except ebus.decoder.UnknownError as err:
            data.available[circuitfield] = False
            _LOGGER.warn(f"Monitor: Decode failed: {err}")


async def _handle_abort(data, connection, name, err):
    if connection.wait == WAIT_MAX:
        data.reset_states()
        for methods in data.observers.values():
            for method in methods:
                await method()
        _LOGGER.error(
            f"{name}: {err}, will retry every {connection.wait}s, " "states reset"
        )
        connection.wait += 1
    else:
        _LOGGER.error(f"{name}: {err}, retry in {connection.wait}s")
        connection.wait = min(2 * connection.wait, WAIT_MAX)
    await asyncio.sleep(connection.wait)
