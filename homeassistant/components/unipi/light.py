"""UniPi sensors."""
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    SUPPORT_BRIGHTNESS,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import HomeAssistantType

from . import UniPiEntity
from .const import API, DOMAIN


def _is_notrelay(info):
    return info["relay_type"] != "physical"


async def async_setup_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry, async_add_entities
):
    """Set up the UniPi component."""

    api = hass.data[DOMAIN][config_entry.entry_id][API]
    entities = []
    for circuit in api.get_circuits("led"):
        entities.append(UniPiLight(api, "led", circuit, "LED"))
    for circuit in api.get_circuits("relay", filter_=_is_notrelay):
        entities.append(UniPiLight(api, "relay", circuit, "Digital Output"))
    for circuit in api.get_circuits("ao"):
        entities.append(UniPiAnalogOut(api, "ao", circuit, "Analog Output"))
    async_add_entities(entities)


class UniPiLight(UniPiEntity, LightEntity):
    """UniPi Light."""

    @property
    def is_on(self):
        """Return the state."""
        return bool(self._api.get_value(self._dev, self._circuit))

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit the value is expressed in."""
        info = self._api.get_info(self._dev, self._circuit)
        return info and info.get("unit", None)

    @property
    def supported_features(self):
        """Flag supported features."""
        return 0

    async def async_turn_on(self, **kwargs):
        """Turn the pin to high/on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs):
        """Turn the pin to low/off."""
        await self._async_set(False)


class UniPiAnalogOut(UniPiLight):
    """UniPi Analog Output."""

    RANGEMAP = {
        "Voltage": 10,
        "Current": 20,
        "Resistance": 100,
    }

    @property
    def _max(self):
        info = self._api.get_info(self._dev, self._circuit)
        return self.RANGEMAP.get(info and info.get("mode", None), None)

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        max_ = self._max
        if max_:
            value = self._api.get_value(self._dev, self._circuit)
            return value * 255 / max_
        return None

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_BRIGHTNESS

    async def async_turn_on(self, **kwargs):
        """Turn the pin to high/on."""
        max_ = self._max
        if max_:
            brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
            await self._async_set(max_ * brightness / 255)
