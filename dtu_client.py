"""DTU client for communicating with OpenDTU and AhoyDTU devices."""

import logging
import time
from typing import Dict, Any, Optional, Union
from urllib.parse import urljoin, urlunparse
import requests

from config import DTUConfig, TemplateConfig, ConfigurationError
from constants import DEFAULT_HTTP_TIMEOUT, DTU_API_ENDPOINTS


class DTUConnectionError(Exception):
    """Raised when DTU connection fails."""
    pass


class DTUDataError(Exception):
    """Raised when DTU data is invalid or incomplete."""
    pass


def get_nested_value(data: Dict[str, Any], path: list[str]) -> Union[float, int, str]:
    """Safely extract nested values from data structure.
    
    Args:
        data: The data dictionary to extract from
        path: List of keys to navigate through nested structure
        
    Returns:
        The value at the specified path
        
    Raises:
        DTUDataError: If the path cannot be found or accessed
    """
    try:
        value = data
        for key in path:
            if isinstance(value, dict):
                value = value[key]
            elif isinstance(value, list):
                try:
                    index = int(key)
                    value = value[index]
                except (ValueError, IndexError) as e:
                    raise DTUDataError(f"Invalid list index '{key}' in path {path}: {e}")
            else:
                raise DTUDataError(f"Cannot navigate path {path}: expected dict or list at '{key}'")
        return value
    except (KeyError, TypeError) as e:
        raise DTUDataError(f"Path {path} not found in data: {e}")


def get_ahoy_field_by_name(meter_data: Dict[str, Any], inverter_number: int, field_name: str) -> Union[float, int]:
    """Extract specific field from Ahoy DTU data by field name.
    
    Args:
        meter_data: The meter data from Ahoy DTU
        inverter_number: The inverter index
        field_name: The name of the field to extract
        
    Returns:
        The field value
        
    Raises:
        DTUDataError: If field cannot be found
    """
    try:
        field_names = meter_data['ch0_fld_names']
        if field_name not in field_names:
            raise DTUDataError(f"Field '{field_name}' not found in ch0_fld_names")
            
        data_index = field_names.index(field_name)
        ac_channel_index = 0
        
        inverter_data = meter_data['inverter'][inverter_number]
        channel_data = inverter_data['ch'][ac_channel_index]
        
        if data_index >= len(channel_data):
            raise DTUDataError(f"Data index {data_index} out of range for channel data")
            
        return channel_data[data_index]
    except (KeyError, IndexError, TypeError) as e:
        raise DTUDataError(f"Failed to extract Ahoy field '{field_name}': {e}")


class DTUClient:
    """Client for communicating with DTU devices."""
    
    def __init__(self, config: DTUConfig, template_config: Optional[TemplateConfig] = None) -> None:
        """Initialize DTU client.
        
        Args:
            config: Main DTU configuration
            template_config: Template configuration (required if DTU variant is 'template')
        """
        self.config = config
        self.template_config = template_config
        self._cached_data: Optional[Dict[str, Any]] = None
        self._test_data: Optional[Dict[str, Any]] = None
        
        if config.dtu_variant == 'template' and template_config is None:
            raise ConfigurationError("Template configuration required for 'template' DTU variant")
    
    def _build_url(self) -> str:
        """Build proper URL for DTU API endpoint.
        
        Returns:
            Complete URL for the DTU API
            
        Raises:
            ConfigurationError: If DTU variant is unsupported
        """
        if self.config.dtu_variant == 'opendtu':
            endpoint = DTU_API_ENDPOINTS['opendtu']
        elif self.config.dtu_variant == 'ahoy':
            endpoint = DTU_API_ENDPOINTS['ahoy']
        elif self.config.dtu_variant == 'template':
            if not self.template_config:
                raise ConfigurationError("Template configuration missing")
            endpoint = self.template_config.api_path
        else:
            raise ConfigurationError(f"Unsupported DTU variant: {self.config.dtu_variant}")
        
        # Build URL components
        scheme = 'http'  # HTTPS support could be added later
        netloc = self.config.host
        
        # Add authentication if provided
        if self.config.username and self.config.password:
            netloc = f"{self.config.username}:{self.config.password}@{self.config.host}"
        elif self.config.username:
            netloc = f"{self.config.username}@{self.config.host}"
        
        # Construct URL
        url = urlunparse((scheme, netloc, endpoint, '', '', ''))
        logging.debug(f"Built DTU URL: {url.replace(self.config.password, '***') if self.config.password else url}")
        
        return url
    
    def refresh_data(self) -> None:
        """Fetch fresh data from DTU device.
        
        Raises:
            DTUConnectionError: If connection to DTU fails
            DTUDataError: If response data is invalid
        """
        if self._test_data:
            logging.debug("Using test data instead of refreshing from DTU")
            return
            
        url = self._build_url()
        
        try:
            logging.debug(f"Fetching data from DTU: {url}")
            response = requests.get(url, timeout=DEFAULT_HTTP_TIMEOUT)
            response.raise_for_status()
            
        except requests.exceptions.Timeout:
            raise DTUConnectionError(f"Timeout connecting to DTU at {self.config.host}")
        except requests.exceptions.ConnectionError:
            raise DTUConnectionError(f"Failed to connect to DTU at {self.config.host}")
        except requests.exceptions.HTTPError as e:
            raise DTUConnectionError(f"HTTP error from DTU: {e}")
        except requests.exceptions.RequestException as e:
            raise DTUConnectionError(f"Request error: {e}")
        
        try:
            meter_data = response.json()
        except ValueError as e:
            raise DTUDataError(f"Failed to parse JSON response from DTU: {e}")
        
        if not meter_data:
            raise DTUDataError("Empty response from DTU")
        
        self._cached_data = meter_data
        logging.debug("Successfully refreshed DTU data")
    
    def get_data(self) -> Dict[str, Any]:
        """Get cached DTU data, refreshing if necessary.
        
        Returns:
            The DTU data dictionary
            
        Raises:
            DTUConnectionError: If connection fails
            DTUDataError: If data is invalid
        """
        if self._test_data:
            return self._test_data
            
        if self._cached_data is None:
            self.refresh_data()
            
        if self._cached_data is None:
            raise DTUDataError("No data available from DTU")
            
        return self._cached_data
    
    def set_test_data(self, test_data: Dict[str, Any]) -> None:
        """Set test data for testing purposes.
        
        Args:
            test_data: Test data to use instead of real DTU data
        """
        self._test_data = test_data
        logging.debug("Test data set for DTU client")
    
    def clear_test_data(self) -> None:
        """Clear test data and return to normal operation."""
        self._test_data = None
        logging.debug("Test data cleared for DTU client")
    
    def get_number_of_inverters(self) -> int:
        """Get the number of inverters from DTU data.
        
        Returns:
            Number of inverters detected
            
        Raises:
            DTUDataError: If inverter count cannot be determined
        """
        data = self.get_data()
        
        try:
            if self.config.dtu_variant == 'ahoy':
                count = len(data['inverter'])
            elif self.config.dtu_variant == 'opendtu':
                count = len(data['inverters'])
            else:  # template
                count = 1
                
            logging.info(f"Number of inverters found: {count}")
            return count
            
        except (KeyError, TypeError) as e:
            raise DTUDataError(f"Failed to determine number of inverters: {e}")
    
    def get_polling_interval(self) -> int:
        """Get appropriate polling interval based on DTU type and ESP variant.
        
        Returns:
            Polling interval in milliseconds
        """
        if self.config.dtu_variant == 'ahoy':
            data = self.get_data()
            try:
                # Check for ESP8266 and reduce polling
                esp_type = data.get('generic', {}).get('esp_type') or data.get('system', {}).get('esp_type', 'ESP32')
                
                if esp_type == 'ESP8266':
                    interval = self.config.esp8266_polling_interval
                    logging.info(f"ESP8266 detected, using polling interval: {interval}ms")
                    return interval
                else:
                    return 5000  # Default for ESP32
            except (KeyError, TypeError):
                logging.warning("Could not determine ESP type, using default polling interval")
                return 5000
                
        elif self.config.dtu_variant == 'opendtu':
            return 5000
        elif self.config.dtu_variant == 'template':
            return self.template_config.polling_interval if self.template_config else 5000
        else:
            return 5000
    
    def is_data_up_to_date(self, inverter_number: int) -> bool:
        """Check if DTU data is up to date based on timestamp.
        
        Args:
            inverter_number: The inverter index to check
            
        Returns:
            True if data is up to date, False otherwise
        """
        if self.config.max_age_ts < 0:
            # Check is disabled by configuration
            return True
            
        data = self.get_data()
        current_time = time.time()
        
        try:
            if self.config.dtu_variant == 'ahoy':
                ts_last_success = data['inverter'][inverter_number]['ts_last_success']
                age_seconds = current_time - ts_last_success
                return age_seconds <= self.config.max_age_ts
                
            elif self.config.dtu_variant == 'opendtu':
                # For OpenDTU, check if inverter is reachable and producing
                inverter_data = data['inverters'][inverter_number]
                reachable = inverter_data.get('reachable', False)
                
                # Handle different boolean representations
                if isinstance(reachable, str):
                    reachable = reachable.lower() in ('true', '1', 'yes')
                elif isinstance(reachable, int):
                    reachable = bool(reachable)
                    
                return bool(reachable)
                
            else:  # template
                # For template, assume data is always up to date if we got it
                return True
                
        except (KeyError, IndexError, TypeError) as e:
            logging.warning(f"Failed to check data timestamp for inverter {inverter_number}: {e}")
            return False
    
    def get_inverter_values(self, inverter_number: int) -> tuple[float, float, float, float]:
        """Get power, total energy, current, and voltage values for an inverter.
        
        Args:
            inverter_number: The inverter index
            
        Returns:
            Tuple of (power, total_energy, current, voltage)
            
        Raises:
            DTUDataError: If values cannot be extracted
        """
        data = self.get_data()
        
        try:
            if self.config.dtu_variant == 'ahoy':
                power = get_ahoy_field_by_name(data, inverter_number, 'P_AC')
                total_energy = get_ahoy_field_by_name(data, inverter_number, 'YieldTotal')
                current = get_ahoy_field_by_name(data, inverter_number, 'I_AC')
                voltage = get_ahoy_field_by_name(data, inverter_number, 'U_AC')
                
            elif self.config.dtu_variant == 'opendtu':
                inverter_data = data['inverters'][inverter_number]
                producing = inverter_data.get('producing', False)
                
                # Handle different boolean representations for producing
                if isinstance(producing, str):
                    producing = producing.lower() in ('true', '1', 'yes')
                elif isinstance(producing, int):
                    producing = bool(producing)
                
                if producing:
                    power = inverter_data['0']['Power']['v']
                    current = inverter_data['0']['Current']['v']
                else:
                    power = 0
                    current = 0
                    
                total_energy = inverter_data['0']['YieldTotal']['v']
                voltage = inverter_data['0']['Voltage']['v']
                
            elif self.config.dtu_variant == 'template':
                if not self.template_config:
                    raise DTUDataError("Template configuration missing")
                    
                power = get_nested_value(data, self.template_config.power_path) * self.template_config.power_multiplier
                total_energy = get_nested_value(data, self.template_config.total_path) * self.template_config.total_multiplier
                current = get_nested_value(data, self.template_config.current_path)
                voltage = get_nested_value(data, self.template_config.voltage_path)
                
            else:
                raise DTUDataError(f"Unsupported DTU variant: {self.config.dtu_variant}")
                
            return (float(power), float(total_energy), float(current), float(voltage))
            
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise DTUDataError(f"Failed to extract inverter values for inverter {inverter_number}: {e}")
    
    def get_serial_number(self, inverter_number: int) -> str:
        """Get serial number for an inverter.
        
        Args:
            inverter_number: The inverter index
            
        Returns:
            Serial number string
            
        Raises:
            DTUDataError: If serial number cannot be determined
        """
        data = self.get_data()
        
        try:
            if self.config.dtu_variant == 'ahoy':
                serial = data['inverter'][inverter_number]['name']
                if not serial:
                    raise DTUDataError("Ahoy inverter name is empty")
                    
            elif self.config.dtu_variant == 'opendtu':
                serial = data['inverters'][inverter_number]['serial']
                if not serial:
                    raise DTUDataError("OpenDTU inverter serial is empty")
                    
            elif self.config.dtu_variant == 'template':
                if not self.template_config:
                    raise DTUDataError("Template configuration missing")
                serial = self.template_config.serial_number
                
            else:
                raise DTUDataError(f"Unsupported DTU variant: {self.config.dtu_variant}")
                
            return str(serial)
            
        except (KeyError, IndexError, TypeError) as e:
            raise DTUDataError(f"Failed to get serial number for inverter {inverter_number}: {e}")
    
    def get_name(self, inverter_number: int) -> str:
        """Get name for an inverter.
        
        Args:
            inverter_number: The inverter index
            
        Returns:
            Inverter name string
        """
        try:
            data = self.get_data()
            
            if self.config.dtu_variant == 'ahoy':
                name = data['inverter'][inverter_number]['name']
            elif self.config.dtu_variant == 'opendtu':
                name = data['inverters'][inverter_number]['name']
            else:
                name = self.config.custom_name
                
            if not name:
                name = self.config.custom_name
                
            logging.info(f"Name of inverter {inverter_number}: {name}")
            return str(name)
            
        except (KeyError, IndexError, TypeError) as e:
            logging.warning(f"Failed to get name for inverter {inverter_number}: {e}, using custom name")
            return self.config.custom_name