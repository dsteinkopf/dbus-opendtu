"""Configuration management for dbus-opendtu."""

import configparser
import logging
import os
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass
from constants import DEFAULT_CONFIG, SUPPORTED_DTU_VARIANTS


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


@dataclass
class InverterConfig:
    """Configuration for a single inverter."""
    device_instance: int
    ac_position: int
    phase: str
    
    def __post_init__(self) -> None:
        """Validate inverter configuration after initialization."""
        if self.phase not in ['L1', 'L2', 'L3']:
            raise ConfigurationError(f"Invalid phase '{self.phase}'. Must be L1, L2, or L3")
        if self.ac_position not in [0, 1, 2]:
            raise ConfigurationError(f"Invalid AC position '{self.ac_position}'. Must be 0, 1, or 2")


@dataclass  
class DTUConfig:
    """Main DTU configuration."""
    host: str
    dtu_variant: str
    username: str = ""
    password: str = ""
    custom_name: str = "Generic-REST"
    number_of_inverters: int = 1
    use_yield_day: bool = False
    max_age_ts: int = 600
    dry_run: bool = False
    esp8266_polling_interval: int = 10000
    sign_of_life_interval: int = 1
    logging_level: str = "ERROR"
    
    def __post_init__(self) -> None:
        """Validate DTU configuration after initialization."""
        if self.dtu_variant not in SUPPORTED_DTU_VARIANTS:
            raise ConfigurationError(f"Unsupported DTU variant '{self.dtu_variant}'. "
                                   f"Supported variants: {SUPPORTED_DTU_VARIANTS}")
        if not self.host:
            raise ConfigurationError("Host is required")


@dataclass
class TemplateConfig:
    """Configuration for template DTU variant."""
    power_path: list[str]
    power_multiplier: float
    total_path: list[str] 
    total_multiplier: float
    voltage_path: list[str]
    current_path: list[str]
    api_path: str
    serial_number: str
    polling_interval: int


class ConfigManager:
    """Manages configuration loading and validation."""
    
    def __init__(self, config_path: Optional[str] = None) -> None:
        """Initialize configuration manager.
        
        Args:
            config_path: Path to config.ini file. If None, uses default location.
        """
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.ini")
        
        self.config_path = config_path
        self._config = configparser.ConfigParser()
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from file with proper error handling."""
        try:
            self._config.read(self.config_path)
        except configparser.Error as e:
            raise ConfigurationError(f"Failed to parse config file '{self.config_path}': {e}")
        except FileNotFoundError:
            raise ConfigurationError(f"Config file not found: {self.config_path}")
        except PermissionError:
            raise ConfigurationError(f"Permission denied reading config file: {self.config_path}")
    
    def _get_required_value(self, section: str, key: str) -> str:
        """Get a required configuration value with proper error handling."""
        try:
            return self._config[section][key]
        except KeyError:
            raise ConfigurationError(f"Required configuration key '{key}' missing from section '{section}'")
    
    def _get_optional_value(self, section: str, key: str, default: Any = None) -> str:
        """Get an optional configuration value with default fallback."""
        try:
            return self._config[section][key]
        except KeyError:
            return default
    
    def _get_int_value(self, section: str, key: str, default: Optional[int] = None) -> int:
        """Get an integer configuration value with validation."""
        value = self._get_optional_value(section, key, default)
        if value is None:
            if default is None:
                raise ConfigurationError(f"Required integer key '{key}' missing from section '{section}'")
            return default
            
        try:
            return int(value)
        except ValueError:
            raise ConfigurationError(f"Invalid integer value for '{key}' in section '{section}': {value}")
    
    def _get_bool_value(self, section: str, key: str, default: bool = False) -> bool:
        """Get a boolean configuration value with validation."""
        value = self._get_optional_value(section, key, str(int(default)))
        return value in ('1', 'True', 'true', 'yes', '1')
    
    def get_dtu_config(self) -> DTUConfig:
        """Load and validate main DTU configuration."""
        try:
            return DTUConfig(
                host=self._get_required_value('DEFAULT', 'Host'),
                dtu_variant=self._get_optional_value('DEFAULT', 'DTU', 'opendtu'),
                username=self._get_optional_value('DEFAULT', 'Username', ''),
                password=self._get_optional_value('DEFAULT', 'Password', ''),
                custom_name=self._get_optional_value('DEFAULT', 'CustomName', 'Generic-REST'),
                number_of_inverters=self._get_int_value('DEFAULT', 'NumberOfInverters', 1),
                use_yield_day=self._get_bool_value('DEFAULT', 'useYieldDay', False),
                max_age_ts=self._get_int_value('DEFAULT', 'MagAgeTsLastSuccess', 600),
                dry_run=self._get_bool_value('DEFAULT', 'DryRun', False),
                esp8266_polling_interval=self._get_int_value('DEFAULT', 'ESP8266PollingIntervall', 10000),
                sign_of_life_interval=self._get_int_value('DEFAULT', 'SignOfLifeLog', 1),
                logging_level=self._get_optional_value('DEFAULT', 'Logging', 'ERROR')
            )
        except ConfigurationError:
            raise
        except Exception as e:
            raise ConfigurationError(f"Unexpected error loading DTU configuration: {e}")
    
    def get_inverter_config(self, inverter_number: int) -> InverterConfig:
        """Load and validate configuration for a specific inverter."""
        section = f'INVERTER{inverter_number}'
        
        try:
            return InverterConfig(
                device_instance=self._get_int_value(section, 'DeviceInstance'),
                ac_position=self._get_int_value(section, 'AcPosition'),
                phase=self._get_required_value(section, 'Phase')
            )
        except ConfigurationError:
            raise
        except Exception as e:
            raise ConfigurationError(f"Unexpected error loading inverter {inverter_number} configuration: {e}")
    
    def get_template_config(self) -> Optional[TemplateConfig]:
        """Load template configuration if DTU variant is 'template'."""
        dtu_config = self.get_dtu_config()
        if dtu_config.dtu_variant != 'template':
            return None
            
        try:
            section = 'TEMPLATE'
            return TemplateConfig(
                power_path=self._get_required_value(section, 'CUST_Power').split('/'),
                power_multiplier=float(self._get_required_value(section, 'CUST_Power_Mult')),
                total_path=self._get_required_value(section, 'CUST_Total').split('/'),
                total_multiplier=float(self._get_required_value(section, 'CUST_Total_Mult')),
                voltage_path=self._get_required_value(section, 'CUST_Voltage').split('/'),
                current_path=self._get_required_value(section, 'CUST_Current').split('/'),
                api_path=self._get_required_value(section, 'CUST_API_PATH'),
                serial_number=self._get_required_value(section, 'CUST_SN'),
                polling_interval=self._get_int_value(section, 'CUST_POLLING')
            )
        except ConfigurationError:
            raise
        except ValueError as e:
            raise ConfigurationError(f"Invalid template configuration value: {e}")
        except Exception as e:
            raise ConfigurationError(f"Unexpected error loading template configuration: {e}")
    
    def validate_configuration(self) -> None:
        """Validate the entire configuration for consistency."""
        dtu_config = self.get_dtu_config()
        
        # Validate all inverter configurations
        for i in range(dtu_config.number_of_inverters):
            try:
                self.get_inverter_config(i)
            except ConfigurationError as e:
                raise ConfigurationError(f"Invalid configuration for inverter {i}: {e}")
        
        # Validate template config if needed
        if dtu_config.dtu_variant == 'template':
            template_config = self.get_template_config()
            if template_config is None:
                raise ConfigurationError("Template configuration missing for DTU variant 'template'")
        
        logging.info("Configuration validation successful")