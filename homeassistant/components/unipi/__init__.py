"""UNIPI Integration."""
import asyncio
import collections
import itertools
import json
import logging
import traceback
from typing import Dict

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import HomeAssistantType

from .const import (
    API,
    CHECKINTERVAL,
    CONF_NAME,
    DOMAIN,
    STARTDELAY,
    TIMEOUT,
    UNDO_UPDATE_LISTENER,
    WRITEINTERVAL,
)

PLATFORMS = ["sensor", "binary_sensor", "light", "switch"]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass, config):
    """Set Up The UniPi Component."""
    return True


async def async_setup_entry(hass, config_entry):
    """Set Up A Config Entry."""
    undo_listener = config_entry.add_update_listener(update_listener)
    api = Api(hass, config_entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = {
        API: api,
        UNDO_UPDATE_LISTENER: undo_listener,
    }

    await api.async_start()

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, component)
        )

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, api.async_stop)

    return True


async def async_unload_entry(hass, config_entry):
    """Unload A Config Entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(config_entry, component)
                for component in PLATFORMS
            ]
        )
    )

    hass.data[DOMAIN][config_entry.entry_id][UNDO_UPDATE_LISTENER]()
    await hass.data[DOMAIN][config_entry.entry_id][API].async_stop()

    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id, None)

    return unload_ok


async def update_listener(hass, config_entry):
    """Handle Options Update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


class Api:
    """API."""

    def __init__(self, hass: HomeAssistantType, entry: ConfigEntry):
        """UNIPI API."""
        self.hass = hass
        self._name = entry.data[CONF_NAME]
        self._host = entry.data[CONF_HOST]
        self._port = entry.data[CONF_PORT]
        self._listeners = collections.defaultdict(list)
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        self._session = aiohttp.ClientSession(timeout=timeout)
        self._connected = asyncio.Event()
        self._broken = asyncio.Event()
        self._values = collections.defaultdict(dict)
        self._infos = collections.defaultdict(dict)
        self._tasks = []

    @property
    def name(self):
        """Name."""
        return self._name

    @callback
    def subscribe(self, entity, ident):
        """Subscribe an entity from API fetches."""
        listeners = self._listeners[ident]
        listeners.append(entity)
        _LOGGER.debug(
            "%s: attach: %s %s listeners=%d", self._name, ident, entity, len(listeners)
        )

        @callback
        def unsubscribe() -> None:
            """Unsubscribe an entity from API fetches (when disable)."""
            listeners = self._listeners[ident]
            listeners.remove(entity)
            _LOGGER.debug(
                "%s: detach: %s %s listeners=%d",
                self._name,
                ident,
                entity,
                len(listeners),
            )

        return unsubscribe

    async def async_start(self):
        """Start."""
        self._tasks.append(asyncio.create_task(self._async_main()))
        await self._connected.wait()

    async def async_stop(self, *_):
        """Stop."""
        self._set_connected(False)
        asyncio.gather(*[self._await_cancel(task) for task in self._tasks])
        self._tasks.clear()

    async def _async_send(self, cmd):
        """Send Command."""
        _LOGGER.debug("%s: send(%r)", self._name, cmd)
        while True:
            try:
                async with self._session.ws_connect(
                    f"ws://{self._host}:{self._port}/ws"
                ) as websocket:
                    await websocket.send_str(json.dumps(cmd))
                    break
            except Exception:  # pylint: disable=broad-except
                _LOGGER.error("%s: %s", self._name, traceback.format_exc())
                self._set_connected(False)
            await asyncio.sleep(WRITEINTERVAL)

    def get_ident(self, dev, circuit):
        """Get Identifier."""
        return f"{self._name}_{dev}_{circuit}".lower()

    def is_available(self, dev, circuit):
        """Check if Available."""
        return self._values[dev].get(circuit, None) is not None

    def get_value(self, dev, circuit):
        """Get Value."""
        value = self._values[dev].get(circuit, None)
        _LOGGER.info("%s: get_value(%r, %r) = %r", self._name, dev, circuit, value)
        return value

    async def async_set_value(self, dev, circuit, value):
        """Set Value."""
        cmd = {"cmd": "set", "dev": dev, "circuit": circuit, "value": value}
        _LOGGER.info("%s: async_set_value(%r, %r, %r)", self._name, dev, circuit, value)
        await self._async_send(cmd)
        self._values[dev][circuit] = value
        self._notify(self.get_ident(dev, circuit))

    def get_info(self, dev, circuit):
        """Get Info."""
        return self._infos[dev].get(circuit, None)

    def get_circuits(self, dev, filter_=None):
        """Get Circuits of type `dev`."""
        if filter_:
            circuits = [
                circuit for circuit, info in self._infos[dev].items() if filter_(info)
            ]
        else:
            circuits = self._infos[dev]
        return tuple(sorted(circuits))

    def get_unitinfo(self):
        """Get Unit Information."""
        for dev in ("neuron", "axon"):
            circuits = self.get_circuits(dev)
            if circuits:
                return self.get_info(dev, circuits[0])

    def _set_connected(self, connected):
        if connected:
            self._connected.set()
            self._broken.clear()
        else:
            self._connected.clear()
            self._broken.set()
            self._values.clear()

    @staticmethod
    async def _await_cancel(task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _async_main(self):
        """Observe UNIPI."""
        _LOGGER.info("%s: start", self._name)
        while True:
            self._broken.clear()
            listener = asyncio.create_task(self._async_connection(listen=True))
            checker = asyncio.create_task(self._async_connection(startdelay=STARTDELAY))
            await self._broken.wait()
            _LOGGER.info("%s: broken", self._name)
            await self._await_cancel(listener)
            await self._await_cancel(checker)
            _LOGGER.info("%s: try to re-start", self._name)
            await asyncio.sleep(CHECKINTERVAL)

    async def _async_connection(self, listen=False, startdelay=0):
        """Monitor UNIPI."""
        # Create Single Session, to avoid connection sharing
        await asyncio.sleep(startdelay)
        while True:
            timeout = aiohttp.ClientTimeout(total=TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    # Connect to UniPi and retrieve device information first
                    async with session.ws_connect(
                        f"ws://{self._host}:{self._port}/ws"
                    ) as websocket:
                        await websocket.send_str('{"cmd": "all"}')
                        msg = await websocket.receive()
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            if not self._connected.is_set():
                                _LOGGER.info(
                                    "%s: Connect to %s:%s",
                                    self._name,
                                    self._host,
                                    self._port,
                                )
                            self._set_connected(True)
                            if listen:
                                self._update(msg.json())
                                async for msg in websocket:
                                    if msg.type == aiohttp.WSMsgType.TEXT:
                                        self._update(msg.json())
                except Exception as exc:  # pylint: disable=broad-except
                    if self._connected.is_set():
                        _LOGGER.error(
                            "%s: Connection lost %s:%s (%r)",
                            self._name,
                            self._host,
                            self._port,
                            exc,
                        )
                    self._set_connected(False)
                    self._notify()
                await asyncio.sleep(CHECKINTERVAL)

    def _update(self, infos):
        if not isinstance(infos, list):
            infos = [infos]
        for info in infos:
            _LOGGER.debug("%s: _update: %r", self._name, dict(info))
            dev = info.pop("dev")
            circuit = info.pop("circuit")
            self._values[dev][circuit] = info.pop("value", None)
            self._infos[dev][circuit] = info
            self._notify(self.get_ident(dev, circuit))

    def _notify(self, ident=None):
        if ident:
            listeners = self._listeners[ident]
        else:
            listeners = tuple(itertools.chain.from_iterable(self._listeners.values()))
        _LOGGER.debug("%s: notify: %s listeners=%d", self._name, ident, len(listeners))
        for entity in listeners:
            if entity.enabled:
                entity.async_write_ha_state()


class UniPiEntity(Entity):
    """UNIPI Entity."""

    def __init__(self, api: Api, dev: str, circuit: str, category: str):
        """UNIPI Entity."""
        super().__init__()
        self._api = api
        self._dev = dev
        self._circuit = circuit
        self._ident = self._api.get_ident(self._dev, self._circuit)
        self._name = f"{self._api.name} {category} {self._circuit}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._ident

    @property
    def name(self) -> str:
        """Return the name."""
        info = self._api.get_info(self._dev, self._circuit)
        alias = info and info.get("alias", "al_")[len("al_") :]
        return alias or self._name

    @property
    def available(self):
        """Return the available."""
        info = self._api.get_info(self._dev, self._circuit)
        available = self._api.is_available(self._dev, self._circuit)
        return available and not info.get("lost", False)

    @property
    def device_state_attributes(self):
        """Device State Attributes."""
        return self._api.get_info(self._dev, self._circuit)

    async def async_added_to_hass(self):
        """Register state update callback."""
        self.async_on_remove(self._api.subscribe(self, self._ident))

    @property
    def device_info(self) -> Dict[str, any]:
        """Return the device information."""
        unitinfo = self._api.get_unitinfo()
        if unitinfo:
            serial = unitinfo["sn"]
            name = f"{self._api.name} (Serial {serial})"
            return {
                "identifiers": {(DOMAIN, self._api.name), (DOMAIN, int(serial))},
                "name": name,
                "manufacturer": "unipi technology",
                "model": unitinfo["model"],
            }

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    async def _async_set(self, value):
        await self._api.async_set_value(self._dev, self._circuit, value)
