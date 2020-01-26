"""One Wire Temperature Sensor."""

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_ADDRESS, CONF_NAME, TEMP_CELSIUS
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity

from .const import DATA_UNIPI

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_ADDRESS): cv.string, vol.Optional(CONF_NAME): cv.string}
)


async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up binary sensor(s) for KNX platform."""
    conn = hass.data[DATA_UNIPI]
    name = config.get(CONF_NAME)
    address = config.get(CONF_ADDRESS)
    entity = TempSensor(conn, name, address)
    async_add_devices([entity])


class TempSensor(Entity):
    """Temperature Sensor."""

    def __init__(self, conn, name, address):
        """Uni Pi Digital Input."""
        self._conn = conn
        self._name = name
        self._address = address
        self._state = None
        self._async_register_callback()

    def _async_register_callback(self):
        async def async_update(message):
            if not message["lost"]:
                self._update(message["value"])
            else:
                self._update(None)
            await self.async_update_ha_state()

        self._conn.add_device("temp", self._address, async_update)

    @property
    def name(self):
        """Name."""
        return self._name

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def available(self):
        """Return if device is available."""
        return self._state is not None

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return TEMP_CELSIUS

    @property
    def should_poll(self):
        """Poll is not needed."""
        return False

    def _update(self, value):
        if value is not None:
            self._state = int(value * 10) / 10
        else:
            self._state = None
