"""UniPi sensors."""
from homeassistant.components.sensor import DEVICE_CLASSES
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

from . import UniPiEntity
from .const import API, DOMAIN


async def async_setup_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry, async_add_entities
):
    """Set up the UniPi component."""

    api = hass.data[DOMAIN][config_entry.entry_id][API]
    entities = []
    for circuit in api.get_circuits("ai"):
        entities.append(UniPiSensor(api, "ai", circuit, "Analog Input"))
    for circuit in api.get_circuits("temp"):
        entities.append(UniPiTempSensor(api, "temp", circuit, "Temperature"))
    async_add_entities(entities)


class UniPiSensor(UniPiEntity):
    """UniPi Sensor."""

    @property
    def state(self):
        """Return the state."""
        return self._api.get_value(self._dev, self._circuit)

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:gauge"

    @property
    def device_class(self) -> str:
        """Device Class."""
        info = self._api.get_info(self._dev, self._circuit)
        device_class = info and info.get("mode", "").lower()
        if device_class and device_class in DEVICE_CLASSES:
            return device_class
        return None

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit the value is expressed in."""
        info = self._api.get_info(self._dev, self._circuit)
        return info and info.get("unit", None)


class UniPiTempSensor(UniPiEntity):
    """UniPi Temperature Sensor."""

    @property
    def state(self):
        """Return the state."""
        return self._api.get_value(self._dev, self._circuit)

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:thermometer"

    @property
    def device_class(self) -> str:
        """Device Class."""
        return "temperature"

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit the value is expressed in."""
        return "°C"
