"""Constants for ebus component."""
from homeassistant.const import ENERGY_KILO_WATT_HOUR, PRESSURE_BAR, TEMP_CELSIUS, TIME_SECONDS

DOMAIN = "ebusd"
CONF_CIRCUIT = "circuit"
DEFAULT_NAME = "ebusd"
DEFAULT_PORT = 8888

UNITMAP = {
    'temp': TEMP_CELSIUS,
    'tempok': TEMP_CELSIUS,
    'seconds': TIME_SECONDS,
    'pressure': PRESSURE_BAR,
    'kwh': ENERGY_KILO_WATT_HOUR,
}
