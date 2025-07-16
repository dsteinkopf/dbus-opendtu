#!/usr/bin/env python3
"""
Legacy entry point for dbus-opendtu.

This file is maintained for backward compatibility.
The application has been refactored into multiple modules.
Please use main.py for the new modular version.
"""

import sys
import warnings

# Issue deprecation warning
warnings.warn(
    "dbus-opendtu.py is deprecated. Please use main.py instead. "
    "The code has been refactored into multiple modules for better maintainability.",
    DeprecationWarning,
    stacklevel=2
)

# Import and run the new main function
try:
    from main import main
    if __name__ == "__main__":
        main()
except ImportError as e:
    print(f"Error importing refactored modules: {e}")
    print("Please ensure all required modules are present:")
    print("- constants.py")
    print("- config.py") 
    print("- dtu_client.py")
    print("- dbus_service.py")
    print("- main.py")
    sys.exit(1)
