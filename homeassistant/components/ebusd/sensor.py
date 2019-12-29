"""EBUS daemon sensors."""
# import datetime
import logging

from homeassistant.helpers.entity import Entity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Ebus sensor."""
    data = hass.data[DOMAIN]

    data.statussensor = StatusSensor(data)
    entities = [data.statussensor]
    for circuit, field in data.monitors:
        entities.append(GenericSensor(data, circuit, field))
    add_entities(entities, True)


class GenericSensor(Entity):
    """Generic Sensor."""

    def __init__(self, data, circuit, field):
        """Initialize."""
        self._data = data
        self._circuit = circuit
        self._field = field
        hname = data.circuitmap.get_humanname(circuit)
        self._name = f"{hname}: {field.title}" if hname else field.title
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

    @property
    def device_state_attributes(self):
        """Return the device state attributes."""
        return self._attrs

    def update(self):
        """Update internal state."""
        self._state = self._data.states[(self._circuit, self._field)]
        self._attrs = self._data.attrs[(self._circuit, self._field)]
        self._available = self._data.available[(self._circuit, self._field)]


class StatusSensor(Entity):
    """Status Sensor."""

    def __init__(self, data):
        """Initialize."""
        self._data = data

    @property
    def name(self):
        """Name of the sensor."""
        return "EBUS"

    @property
    def should_poll(self):
        """Poll is not needed."""
        return False

    @property
    def state(self):
        """State of the sensor."""
        state = self._data.status.get("signal")
        state = "ok" if state == "acquired" else state
        return state

    @property
    def available(self):
        """Availablity of the sensor."""
        return True

    @property
    def device_state_attributes(self):
        """Return the device state attributes."""
        return dict(
            (k, v)
            for k, v in self._data.status.items()
            if not isinstance(v, (dict, list, tuple))
        )

    def update(self):
        """Update internal state."""
        pass
