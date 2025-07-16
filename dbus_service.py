"""D-Bus service implementation for OpenDTU integration with Venus OS."""

import dbus
import logging
import os
import platform
import sys
from typing import Dict, Any, Optional, Callable, Union

if sys.version_info.major == 2:
    import gobject
else:
    from gi.repository import GLib as gobject

# Import Victron VE.Bus library
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService

from config import ConfigManager, InverterConfig, DTUConfig, ConfigurationError
from dtu_client import DTUClient, DTUConnectionError, DTUDataError
from constants import (
    DBUS_SERVICE_NAME, PRODUCT_ID, FIRMWARE_VERSION, HARDWARE_VERSION,
    DBUS_PATHS, DEFAULT_SIGN_OF_LIFE_INTERVAL
)


class DBusServiceError(Exception):
    """Raised when D-Bus service operations fail."""
    pass


class VenusDBusService:
    """Venus OS D-Bus service for OpenDTU integration."""
    
    # Class-level registry for multiple instances
    _registry: list['VenusDBusService'] = []
    
    def __init__(
        self,
        inverter_number: int,
        config_manager: ConfigManager,
        dtu_client: DTUClient,
        is_test: bool = False
    ) -> None:
        """Initialize Venus D-Bus service for a specific inverter.
        
        Args:
            inverter_number: The inverter index (0-based)
            config_manager: Configuration manager instance
            dtu_client: DTU client instance
            is_test: Whether this is a test instance
        """
        self.inverter_number = inverter_number
        self.config_manager = config_manager
        self.dtu_client = dtu_client
        self.is_test = is_test
        
        if not is_test:
            self._registry.append(self)
            
        self._last_update = 0
        self._dbus_service: Optional[VeDbusService] = None
        
        # Load configurations
        try:
            self.dtu_config = config_manager.get_dtu_config()
            self.inverter_config = config_manager.get_inverter_config(inverter_number)
        except ConfigurationError as e:
            raise DBusServiceError(f"Configuration error for inverter {inverter_number}: {e}")
        
        if not is_test:
            self._setup_dbus_service()
            self._setup_periodic_update()
    
    def _setup_dbus_service(self) -> None:
        """Set up the D-Bus service with all required paths."""
        try:
            # Connect to D-Bus
            dbus_conn = dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus(private=True)
            
            # Create service name with device instance
            service_name = f"{DBUS_SERVICE_NAME}.http_{self.inverter_config.device_instance:02d}"
            self._dbus_service = VeDbusService(service_name, dbus_conn)
            
            logging.debug(f"Created D-Bus service: {service_name}")
            
            # Add management paths
            self._add_management_paths()
            
            # Add mandatory device paths
            self._add_device_paths()
            
            # Add measurement paths
            self._add_measurement_paths()
            
            logging.info(f"D-Bus service setup complete for inverter {self.inverter_number}")
            
        except Exception as e:
            raise DBusServiceError(f"Failed to setup D-Bus service: {e}")
    
    def _add_management_paths(self) -> None:
        """Add D-Bus management paths."""
        if not self._dbus_service:
            raise DBusServiceError("D-Bus service not initialized")
            
        self._dbus_service.add_path('/Mgmt/ProcessName', __file__)
        self._dbus_service.add_path('/Mgmt/ProcessVersion', f'Unknown version, running on Python {platform.python_version()}')
        self._dbus_service.add_path('/Mgmt/Connection', 'OpenDTU HTTP JSON service')
    
    def _add_device_paths(self) -> None:
        """Add mandatory device identification paths."""
        if not self._dbus_service:
            raise DBusServiceError("D-Bus service not initialized")
            
        try:
            # Get inverter information from DTU
            serial = self.dtu_client.get_serial_number(self.inverter_number)
            name = self.dtu_client.get_name(self.inverter_number)
            
        except DTUDataError as e:
            logging.warning(f"Failed to get inverter info: {e}, using defaults")
            serial = f"unknown_{self.inverter_number}"
            name = self.dtu_config.custom_name
        
        # Add device identification paths
        self._dbus_service.add_path('/DeviceInstance', self.inverter_config.device_instance)
        self._dbus_service.add_path('/ProductId', PRODUCT_ID)
        self._dbus_service.add_path('/ProductName', 'OpenDTU')
        self._dbus_service.add_path('/CustomName', name)
        self._dbus_service.add_path('/Connected', 1)
        self._dbus_service.add_path('/Latency', None)
        self._dbus_service.add_path('/FirmwareVersion', FIRMWARE_VERSION)
        self._dbus_service.add_path('/HardwareVersion', HARDWARE_VERSION)
        self._dbus_service.add_path('/Position', self.inverter_config.ac_position)
        self._dbus_service.add_path('/Serial', serial)
        self._dbus_service.add_path('/UpdateIndex', 0)
        self._dbus_service.add_path('/StatusCode', 0)  # Required for VRM PV-inverter detection
    
    def _add_measurement_paths(self) -> None:
        """Add measurement data paths with formatters."""
        if not self._dbus_service:
            raise DBusServiceError("D-Bus service not initialized")
            
        # Format functions for display
        _kwh = lambda p, v: f"{round(v, 2)}KWh" if v is not None else "N/A"
        _a = lambda p, v: f"{round(v, 1)}A" if v is not None else "N/A"
        _w = lambda p, v: f"{round(v, 1)}W" if v is not None else "N/A"
        _v = lambda p, v: f"{round(v, 1)}V" if v is not None else "N/A"
        
        # Create paths with formatters
        paths_with_formatters = {
            '/Ac/Energy/Forward': {'initial': None, 'textformat': _kwh},
            '/Ac/Power': {'initial': None, 'textformat': _w},
            '/Ac/L1/Voltage': {'initial': None, 'textformat': _v},
            '/Ac/L2/Voltage': {'initial': None, 'textformat': _v},
            '/Ac/L3/Voltage': {'initial': None, 'textformat': _v},
            '/Ac/L1/Current': {'initial': None, 'textformat': _a},
            '/Ac/L2/Current': {'initial': None, 'textformat': _a},
            '/Ac/L3/Current': {'initial': None, 'textformat': _a},
            '/Ac/L1/Power': {'initial': None, 'textformat': _w},
            '/Ac/L2/Power': {'initial': None, 'textformat': _w},
            '/Ac/L3/Power': {'initial': None, 'textformat': _w},
            '/Ac/L1/Energy/Forward': {'initial': None, 'textformat': _kwh},
            '/Ac/L2/Energy/Forward': {'initial': None, 'textformat': _kwh},
            '/Ac/L3/Energy/Forward': {'initial': None, 'textformat': _kwh},
        }
        
        # Add paths to D-Bus service
        for path, settings in paths_with_formatters.items():
            self._dbus_service.add_path(
                path,
                settings['initial'],
                gettextcallback=settings['textformat'],
                writeable=True,
                onchangecallback=self._handle_changed_value
            )
    
    def _handle_changed_value(self, path: str, value: Any) -> bool:
        """Handle D-Bus path value changes.
        
        Args:
            path: The D-Bus path that changed
            value: The new value
            
        Returns:
            True to accept the change
        """
        logging.debug(f"D-Bus path {path} changed to {value}")
        return True
    
    def _setup_periodic_update(self) -> None:
        """Set up periodic data updates and sign of life logging."""
        try:
            # Set up periodic data updates
            polling_interval = self.dtu_client.get_polling_interval()
            gobject.timeout_add(polling_interval, self._update_data)
            
            # Set up sign of life logging
            sign_of_life_interval = self.dtu_config.sign_of_life_interval * 60 * 1000  # Convert to ms
            gobject.timeout_add(sign_of_life_interval, self._sign_of_life)
            
            logging.info(f"Periodic updates configured: data={polling_interval}ms, sign_of_life={sign_of_life_interval}ms")
            
        except Exception as e:
            raise DBusServiceError(f"Failed to setup periodic updates: {e}")
    
    def _update_data(self) -> bool:
        """Update inverter data from DTU.
        
        Returns:
            True to continue periodic updates
        """
        try:
            # Only update data for the first inverter (shared data)
            if self.inverter_number == 0:
                self.dtu_client.refresh_data()
            
            # Check if data is up to date
            if not self.dtu_client.is_data_up_to_date(self.inverter_number):
                logging.warning(f"Data for inverter {self.inverter_number} is not up to date")
                if not self.dtu_config.dry_run:
                    self._set_default_values()
                return True
            
            # Get inverter values
            power, total_energy, current, voltage = self.dtu_client.get_inverter_values(self.inverter_number)
            
            if not self.dtu_config.dry_run:
                self._update_dbus_values(power, total_energy, current, voltage)
            else:
                logging.info(f"DRY RUN - Would update inverter {self.inverter_number}: "
                           f"power={power}W, energy={total_energy}kWh, current={current}A, voltage={voltage}V")
            
        except (DTUConnectionError, DTUDataError) as e:
            logging.error(f"Failed to update data for inverter {self.inverter_number}: {e}")
            if not self.dtu_config.dry_run:
                self._set_default_values()
        except Exception as e:
            logging.error(f"Unexpected error updating inverter {self.inverter_number}: {e}")
        
        return True  # Continue periodic updates
    
    def _update_dbus_values(self, power: float, total_energy: float, current: float, voltage: float) -> None:
        """Update D-Bus values with inverter data.
        
        Args:
            power: AC power in watts
            total_energy: Total energy in kWh
            current: AC current in amperes
            voltage: AC voltage in volts
        """
        if not self._dbus_service:
            return
            
        try:
            # Determine which phase this inverter is connected to
            phase = self.inverter_config.phase
            
            # Update total AC values
            if self.dtu_config.use_yield_day:
                # Use yield day instead of total (not implemented in DTU client yet)
                self._dbus_service['/Ac/Energy/Forward'] = total_energy  # Placeholder
            else:
                self._dbus_service['/Ac/Energy/Forward'] = total_energy
            
            self._dbus_service['/Ac/Power'] = power
            
            # Update phase-specific values
            self._dbus_service[f'/Ac/{phase}/Voltage'] = voltage
            self._dbus_service[f'/Ac/{phase}/Current'] = current
            self._dbus_service[f'/Ac/{phase}/Power'] = power
            self._dbus_service[f'/Ac/{phase}/Energy/Forward'] = total_energy
            
            # Set other phases to zero
            for other_phase in ['L1', 'L2', 'L3']:
                if other_phase != phase:
                    self._dbus_service[f'/Ac/{other_phase}/Voltage'] = 0
                    self._dbus_service[f'/Ac/{other_phase}/Current'] = 0
                    self._dbus_service[f'/Ac/{other_phase}/Power'] = 0
                    self._dbus_service[f'/Ac/{other_phase}/Energy/Forward'] = 0
            
            # Update index to signal new data
            current_index = self._dbus_service['/UpdateIndex']
            self._dbus_service['/UpdateIndex'] = (current_index + 1) % 256
            
            logging.debug(f"Updated D-Bus values for inverter {self.inverter_number} on {phase}: "
                         f"power={power}W, energy={total_energy}kWh")
            
        except Exception as e:
            logging.error(f"Failed to update D-Bus values: {e}")
    
    def _set_default_values(self) -> None:
        """Set default/zero values when data is unavailable."""
        if not self._dbus_service:
            return
            
        try:
            self._dbus_service['/Ac/Energy/Forward'] = 0
            self._dbus_service['/Ac/Power'] = 0
            
            for phase in ['L1', 'L2', 'L3']:
                self._dbus_service[f'/Ac/{phase}/Voltage'] = 0
                self._dbus_service[f'/Ac/{phase}/Current'] = 0
                self._dbus_service[f'/Ac/{phase}/Power'] = 0
                self._dbus_service[f'/Ac/{phase}/Energy/Forward'] = 0
            
            logging.debug(f"Set default values for inverter {self.inverter_number}")
            
        except Exception as e:
            logging.error(f"Failed to set default values: {e}")
    
    def _sign_of_life(self) -> bool:
        """Log sign of life message.
        
        Returns:
            True to continue periodic logging
        """
        logging.info(f"--- Sign of life for inverter {self.inverter_number} ---")
        return True
    
    def get_values_for_inverter(self) -> tuple[float, float, float, float]:
        """Get current values for this inverter (for testing).
        
        Returns:
            Tuple of (power, total_energy, current, voltage)
        """
        return self.dtu_client.get_inverter_values(self.inverter_number)
    
    def set_test_data(self, test_data: Dict[str, Any]) -> None:
        """Set test data (for testing)."""
        self.dtu_client.set_test_data(test_data)
    
    def set_dtu_variant(self, variant: str) -> None:
        """Set DTU variant (for testing)."""
        if hasattr(self.dtu_client, 'config'):
            self.dtu_client.config.dtu_variant = variant
    
    def is_data_up_to_date(self) -> bool:
        """Check if data is up to date (for testing)."""
        return self.dtu_client.is_data_up_to_date(self.inverter_number)
    
    @classmethod
    def get_all_services(cls) -> list['VenusDBusService']:
        """Get all registered service instances."""
        return cls._registry.copy()
    
    @classmethod
    def shutdown_all_services(cls) -> None:
        """Shutdown all registered services."""
        for service in cls._registry:
            try:
                # Cleanup could be added here if needed
                logging.info(f"Shutting down service for inverter {service.inverter_number}")
            except Exception as e:
                logging.error(f"Error shutting down service: {e}")
        cls._registry.clear()


def create_dbus_services(config_manager: ConfigManager) -> list[VenusDBusService]:
    """Create D-Bus services for all configured inverters.
    
    Args:
        config_manager: Configuration manager instance
        
    Returns:
        List of created D-Bus services
        
    Raises:
        DBusServiceError: If services cannot be created
    """
    try:
        dtu_config = config_manager.get_dtu_config()
        template_config = config_manager.get_template_config()
        
        # Create DTU client
        dtu_client = DTUClient(dtu_config, template_config)
        
        # Validate configuration
        config_manager.validate_configuration()
        
        # Get number of inverters from DTU or config
        try:
            num_inverters = dtu_client.get_number_of_inverters()
        except DTUDataError:
            logging.warning("Could not get inverter count from DTU, using config value")
            num_inverters = dtu_config.number_of_inverters
        
        # Create services for all inverters
        services = []
        for i in range(num_inverters):
            try:
                service = VenusDBusService(i, config_manager, dtu_client)
                services.append(service)
                logging.info(f"Created D-Bus service for inverter {i}")
            except Exception as e:
                logging.error(f"Failed to create service for inverter {i}: {e}")
                # Continue with other inverters
        
        if not services:
            raise DBusServiceError("No D-Bus services could be created")
        
        return services
        
    except Exception as e:
        raise DBusServiceError(f"Failed to create D-Bus services: {e}")