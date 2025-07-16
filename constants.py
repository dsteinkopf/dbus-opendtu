"""Constants for dbus-opendtu application."""

from typing import Dict, Any

# D-Bus Service Configuration
DBUS_SERVICE_NAME = "com.victronenergy.pvinverter"
PRODUCT_ID = 0xFFFF  # ID assigned by Victron Support
FIRMWARE_VERSION = 0.1
HARDWARE_VERSION = 0

# Timing Constants (in seconds)
DEFAULT_MAX_AGE_TS = 600  # Maximum age for timestamp validation
DEFAULT_POLLING_INTERVAL = 5000  # Default polling interval in ms
ESP8266_POLLING_INTERVAL = 10000  # Reduced polling for ESP8266
DEFAULT_SIGN_OF_LIFE_INTERVAL = 1  # Minutes between sign of life logs

# HTTP Configuration
DEFAULT_HTTP_TIMEOUT = 2.5  # HTTP request timeout in seconds
DTU_API_ENDPOINTS = {
    'opendtu': '/api/livedata/status',
    'ahoy': '/api/live'
}

# D-Bus Paths Configuration
DBUS_PATHS = {
    '/Ac/Energy/Forward': {'initial': None, 'unit': 'KWh'}, 
    '/Ac/Power': {'initial': None, 'unit': 'W'},        
    '/Ac/L1/Voltage': {'initial': None, 'unit': 'V'},
    '/Ac/L2/Voltage': {'initial': None, 'unit': 'V'},
    '/Ac/L3/Voltage': {'initial': None, 'unit': 'V'},
    '/Ac/L1/Current': {'initial': None, 'unit': 'A'},
    '/Ac/L2/Current': {'initial': None, 'unit': 'A'},
    '/Ac/L3/Current': {'initial': None, 'unit': 'A'},
    '/Ac/L1/Power': {'initial': None, 'unit': 'W'},
    '/Ac/L2/Power': {'initial': None, 'unit': 'W'},
    '/Ac/L3/Power': {'initial': None, 'unit': 'W'},
    '/Ac/L1/Energy/Forward': {'initial': None, 'unit': 'KWh'},
    '/Ac/L2/Energy/Forward': {'initial': None, 'unit': 'KWh'},
    '/Ac/L3/Energy/Forward': {'initial': None, 'unit': 'KWh'},
}

# Supported DTU Variants
SUPPORTED_DTU_VARIANTS = {'opendtu', 'ahoy', 'template'}

# Default Configuration Values
DEFAULT_CONFIG = {
    'SignOfLifeLog': DEFAULT_SIGN_OF_LIFE_INTERVAL,
    'Deviceinstance': 34,
    'CustomName': 'Generic-REST',
    'AcPosition': 1,
    'NumberOfInverters': 1,
    'DTU': 'opendtu',
    'useYieldDay': 0,
    'ESP8266PollingIntervall': ESP8266_POLLING_INTERVAL,
    'Logging': 'ERROR',
    'MagAgeTsLastSuccess': DEFAULT_MAX_AGE_TS,
    'DryRun': 0,
}