"""UniPi sensors."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

from . import UniPiEntity
from .const import API, DOMAIN


async def async_setup_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry, async_add_entities
):
    """Set up the UniPi component."""

    api = hass.data[DOMAIN][config_entry.entry_id][API]
    async_add_entities(
        [
            UniPiBinarySensor(api, "input", circuit, "Digital Input")
            for circuit in api.get_circuits("input")
        ]
    )


class UniPiBinarySensor(UniPiEntity, BinarySensorEntity):
    """UniPi Binary Sensor."""

    @property
    def is_on(self):
        """Return the state."""
        return bool(self._api.get_value(self._dev, self._circuit))

    @property
    def icon(self) -> str:
        """Return the icon."""
        if self.is_on:
            return "mdi:electric-switch-closed"
        return "mdi:electric-switch"
