"""The UniPi integration."""
import asyncio
import json
import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from .const import CONF_WEBSOCKET, DATA_UNIPI, DOMAIN

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({vol.Required(CONF_WEBSOCKET): cv.string})},
    extra=vol.ALLOW_EXTRA,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry):
    """Set up a config entry for Unipi."""
    return True


async def async_setup(hass, config):
    """Platform Setup."""
    hass.data[DATA_UNIPI] = conn = Connection(config[DOMAIN].get(CONF_WEBSOCKET))
    conn.connect()
    return True


class _MessageDispatcher(object):
    def __init__(self):
        super().__init__()
        self._registry = {}

    def register(self, dev, circuit, callback):
        self._registry[(dev, circuit)] = callback

    def _lookup(self, message):
        dev = message["dev"]
        circuit = message["circuit"]
        try:
            return self._registry[(dev, circuit)]
        except KeyError:
            return None

    async def async_dispatch(self, message):
        callback = self._lookup(message)
        if callback:
            _LOGGER.info("handling %s", message)
            await callback(message)
        elif message["dev"] not in ("ai", "wd"):
            _LOGGER.info("ignoring %s", message)


class Connection(object):
    """Websocket Gateway."""

    _initcmds = [
        # {"cmd": "filter", "devs": ["ai", "input"]},
    ]

    def __init__(self, ws_url):
        """Initialize."""
        self._ws_url = ws_url
        self._dispatcher = _MessageDispatcher()
        self._ws = None

    def connect(self):
        """Connect."""
        asyncio.ensure_future(self._ws_listen())

    def add_device(self, dev, circuit, async_callback):
        """Register new device."""
        self._dispatcher.register(dev, circuit, async_callback)

    async def _ws_open(self):
        import websockets as wslib

        try:
            if not self._ws:
                self._ws = await wslib.connect(self._ws_url)
                for initcmd in self._initcmds:
                    await self._ws.send(json.dumps(initcmd))
                _LOGGER.info("Connected successfully to %s", self._ws_url)
        except Exception as ws_exc:  # pylint: disable=broad-except
            _LOGGER.error("Failed to connect to %s", ws_exc)

    async def async_send_rest_request(self, sub):
        """Send request."""
        import requests

        url = self._rest_url + "/" + sub
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, requests.get, url)
        if response.status_code == 200:
            return response.json()
        else:
            _LOGGER.error("Requesting %r failed" % (url))

    async def async_ws_send(self, data):
        """Send 'data'."""
        await self._ws_open()
        if self._ws:
            try:
                _LOGGER.debug("Send: %s", data)
                await self._ws.send(json.dumps(data))
            except Exception as ws_exc:  # pylint: disable=broad-except
                _LOGGER.error("Send failed: %s", ws_exc)
                try:
                    await self._ws.close()
                finally:
                    self._ws = None
        else:
            _LOGGER.error("Send failed, connection is broken.")

    async def _ws_receive(self):
        """Read from websocket."""
        result = None

        await self._ws_open()
        if self._ws:
            try:
                result = await self._ws.recv()
                _LOGGER.debug("Receive: %s", result)
            except Exception as ws_exc:  # pylint: disable=broad-except
                _LOGGER.error("Receive failed: %s", ws_exc)
                try:
                    await self._ws.close()
                finally:
                    self._ws = None

        return result

    async def _ws_listen(self):
        """Listen on websocket."""
        try:
            while True:
                result = await self._ws_receive()

                if result:
                    data = json.loads(result)
                    await self._ws_process_message(data)
                else:
                    _LOGGER.error("Listen failed, trying again in 1 second")
                    await asyncio.sleep(1)
        finally:
            if self._ws:
                await self._ws.close()
                self._ws = None

    async def _ws_process_message(self, message):
        try:
            messages = message if isinstance(message, list) else [message]
            for message in messages:
                await self._dispatcher.async_dispatch(message)
        except:  # noqa: E722  # pylint: disable=bare-except
            _LOGGER.exception("Exception in callback, ignoring")
