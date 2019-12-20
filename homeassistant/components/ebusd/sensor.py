"""EBUS daemon sensors."""
# import datetime
import logging

from homeassistant.helpers.entity import Entity

from .const import DOMAIN

# import homeassistant.util.dt as dt_util


# TIME_FRAME1_BEGIN = "time_frame1_begin"
# TIME_FRAME1_END = "time_frame1_end"
# TIME_FRAME2_BEGIN = "time_frame2_begin"
# TIME_FRAME2_END = "time_frame2_end"
# TIME_FRAME3_BEGIN = "time_frame3_begin"
# TIME_FRAME3_END = "time_frame3_end"

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Ebus sensor."""
    data = hass.data[DOMAIN]
    _LOGGER.debug("setup_platform() started")

    entities = []
    for circuit, field in data.monitors:
        entities.append(GenericSensor(data, circuit, field))
    add_entities(sorted(entities, key=lambda sensor: sensor.name), True)
    _LOGGER.debug("setup_platform() done")


class GenericSensor(Entity):
    """Generic Sensor."""

    def __init__(self, data, circuit, field):
        """Initialize."""
        self._data = data
        self._circuit = circuit
        self._field = field
        humanname = data.circuitmap.get_humanname(circuit)
        self._name = f"{humanname}: {field.title}" if humanname else field.title
        self._unit = data.units.get(field.unitname)
        self._state = None
        self._attrs = {}
        self._available = True

        async def async_update():
            self.update()
            await self.async_update_ha_state()

        data.add_observer(circuit, field, async_update)

    @property
    def name(self):
        """Name of the sensor."""
        return self._name

    @property
    def should_poll(self):
        """Poll is not needed."""
        return False

    @property
    def state(self):
        """State of the sensor."""
        return self._state

    @property
    def available(self):
        """Availablity of the sensor."""
        return self._available is True

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._field.icon or (self._unit and self._unit.icon)

    @property
    def unit_of_measurement(self):
        """Return Unit."""
        return self._unit and self._unit.uom

    def update(self):
        """Update internal state."""
        self._state = self._data.states[(self._circuit, self._field)]
        self._attrs = self._data.attrs[(self._circuit, self._field)]
        self._available = self._data.available[(self._circuit, self._field)]

    @property
    def device_state_attributes(self):
        """Return the device state attributes."""
        return self._attrs
