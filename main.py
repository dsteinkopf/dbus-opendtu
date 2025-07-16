#!/usr/bin/env python3
"""Main entry point for dbus-opendtu application."""

import logging
import os
import sys
from typing import NoReturn

if sys.version_info.major == 2:
    import gobject
else:
    from gi.repository import GLib as gobject

# D-Bus setup for Venus OS
from dbus.mainloop.glib import DBusGMainLoop

# Import our modules
from config import ConfigManager, ConfigurationError
from dbus_service import create_dbus_services, VenusDBusService, DBusServiceError
from dtu_client import DTUConnectionError, DTUDataError


def setup_logging(config_manager: ConfigManager) -> None:
    """Set up logging configuration.
    
    Args:
        config_manager: Configuration manager to get logging level from
    """
    try:
        dtu_config = config_manager.get_dtu_config()
        logging_level = getattr(logging, dtu_config.logging_level.upper(), logging.ERROR)
    except (ConfigurationError, AttributeError):
        logging_level = logging.ERROR
    
    # Configure logging with file and console handlers
    log_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "current.log")
    
    logging.basicConfig(
        format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=logging_level,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    logging.info(f"Logging configured at level: {logging.getLevelName(logging_level)}")


def main() -> NoReturn:
    """Main application entry point."""
    try:
        # Load configuration
        config_manager = ConfigManager()
        
        # Set up logging
        setup_logging(config_manager)
        
        logging.info("Starting dbus-opendtu service")
        
        # Set up D-Bus main loop
        DBusGMainLoop(set_as_default=True)
        
        # Create and start D-Bus services
        services = create_dbus_services(config_manager)
        
        logging.info(f"Created {len(services)} D-Bus service(s)")
        logging.info("Connected to D-Bus, switching to GObject main loop")
        
        # Start the main event loop
        main_loop = gobject.MainLoop()
        main_loop.run()
        
    except ConfigurationError as e:
        logging.critical(f"Configuration error: {e}")
        sys.exit(1)
        
    except DBusServiceError as e:
        logging.critical(f"D-Bus service error: {e}")
        sys.exit(1)
        
    except DTUConnectionError as e:
        logging.critical(f"DTU connection error: {e}")
        sys.exit(1)
        
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt, shutting down")
        
    except Exception as e:
        logging.critical(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
        
    finally:
        # Cleanup
        try:
            VenusDBusService.shutdown_all_services()
            logging.info("Service shutdown complete")
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")


if __name__ == "__main__":
    main()