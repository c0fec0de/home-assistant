"""Constants for ebus component."""
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
    PRESSURE_BAR,
    TEMP_CELSIUS,
    TIME_SECONDS,
)

DOMAIN = "ebusd"

UNITMAP = {
    'temp': TEMP_CELSIUS,
    'tempok': TEMP_CELSIUS,
    'seconds': TIME_SECONDS,
    'pressure': PRESSURE_BAR,
    'kwh': ENERGY_KILO_WATT_HOUR,
}
