"""Digital Output on Unipi Neuron or Extension Module."""
import voluptuous as vol

from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchDevice
from homeassistant.const import CONF_ADDRESS, CONF_NAME
import homeassistant.helpers.config_validation as cv

from .const import CONF_INITIAL, CONF_NEGATE, CONF_TYPE, DATA_UNIPI
from .util import norm_circuit

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_TYPE, default="relay"): cv.string,
        vol.Optional(CONF_INITIAL, default=False): cv.boolean,
        vol.Optional(CONF_NEGATE, default=False): cv.boolean,
    }
)


async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Digital Output Setup."""
    conn = hass.data[DATA_UNIPI]
    circuit = norm_circuit(config.get(CONF_ADDRESS))
    name = config.get(CONF_NAME)
    type_ = config.get(CONF_TYPE)
    negate = config.get(CONF_NEGATE)
    initial = config.get(CONF_INITIAL)

    switch = UniPiSwitch(conn, circuit, name, type_, negate, initial)
    await switch.async_init()
    async_add_devices([switch])


class UniPiSwitch(SwitchDevice):
    """UniPi Digital Output, Relay or LED."""

    def __init__(self, conn, circuit, name, type_, negate, initial):
        """Unipi Digital Output, Relay or LED."""
        self._conn = conn
        self._circuit = circuit
        self._name = name
        self._type = type_
        self._negate = negate
        self._initial = initial
        self._state = None

    async def async_init(self):
        """Initialize."""
        await self._async_update(self._initial)

    @property
    def name(self):
        """Get the name of the pin."""
        return self._name

    @property
    def is_on(self):
        """Return true if pin is high/on."""
        return self._state

    async def async_turn_on(self, **kwargs):
        """Turn the pin to high/on."""
        await self._async_update(True)

    async def async_turn_off(self, **kwargs):
        """Turn the pin to low/off."""
        await self._async_update(False)

    async def _async_update(self, value):
        self._state = bool(value)
        value = 1 if self._state != self._negate else 0
        data = {
            "cmd": "set",
            "dev": self._type,
            "circuit": self._circuit,
            "value": value,
        }
        await self._conn.async_ws_send(data)
