"""UniPi sensors."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

from . import UniPiEntity
from .const import API, DOMAIN


def _is_relay(info):
    return info["relay_type"] == "physical"


async def async_setup_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry, async_add_entities
):
    """Set up the UniPi component."""

    api = hass.data[DOMAIN][config_entry.entry_id][API]
    async_add_entities(
        [
            UniPiSwitch(api, "relay", circuit, "Relay")
            for circuit in api.get_circuits("relay", filter_=_is_relay)
        ]
    )


class UniPiSwitch(UniPiEntity, SwitchEntity):
    """UniPi Switch."""

    @property
    def is_on(self):
        """Return the state."""
        return bool(self._api.get_value(self._dev, self._circuit))

    @property
    def icon(self) -> str:
        """Return the icon."""
        if self.is_on is False:
            return "mdi:toggle-switch-off"
        return "mdi:toggle-switch"

    async def async_turn_on(self, **kwargs):
        """Turn the pin to high/on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs):
        """Turn the pin to low/off."""
        await self._async_set(False)
