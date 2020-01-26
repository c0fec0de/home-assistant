"""Digital Input on Unipi Neuron or Extension Module."""
import logging

import voluptuous as vol

from homeassistant.components.binary_sensor import PLATFORM_SCHEMA, BinarySensorDevice
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_CLASS, CONF_NAME
import homeassistant.helpers.config_validation as cv

from .const import DATA_UNIPI
from .util import norm_circuit

_LOGGER = logging.getLogger(__name__)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): cv.string,
    }
)


async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up Binary Sensor."""
    conn = hass.data[DATA_UNIPI]
    name = config.get(CONF_NAME)
    device_class = config.get(CONF_DEVICE_CLASS)
    circuit = norm_circuit(config.get(CONF_ADDRESS))
    entity = UniPiBinarySensor(conn, name, device_class, circuit)
    async_add_devices([entity])


class UniPiBinarySensor(BinarySensorDevice):
    """UniPi Digital Input."""

    def __init__(self, conn, name, device_class, circuit):
        """Unipi Digital Input."""
        self._conn = conn
        self._name = name
        self._device_class = device_class
        self._circuit = circuit
        self._state = False
        self._async_register_callback()

    def _async_register_callback(self):
        async def async_update(message):
            await self._async_update(message["value"])
            await self.async_update_ha_state()

        self._conn.add_device("input", self._circuit, async_update)

    @property
    def name(self):
        """Name."""
        return self._name

    @property
    def should_poll(self):
        """Poll is not needed."""
        return False

    @property
    def device_class(self):
        """Device Class."""
        return self._device_class

    @property
    def is_on(self):
        """State."""
        return self._state

    async def _async_update(self, value):
        self._state = bool(value)
