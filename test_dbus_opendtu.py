#!/usr/bin/env python3
"""Test suite for dbus-opendtu application."""

import json
import time
import unittest
from typing import Dict, Any

from config import ConfigManager, DTUConfig, ConfigurationError
from dtu_client import DTUClient, DTUDataError
from dbus_service import VenusDBusService


# Test data from original file
OPENDTU_TEST_DATA = '''
{
  "inverters": [
    {
      "serial": "112181311701",
      "name": "Holzpalast Süd",
      "data_age": 11559,
      "reachable": false,
      "producing": false,
      "limit_relative": 100,
      "limit_absolute": 350,
      "0": {
        "Power": {"v": 1, "u": "W"},
        "Voltage": {"v": 235.1999969, "u": "V"},
        "Current": {"v": 1, "u": "A"},
        "Power DC": {"v": 1.200000048, "u": "W"},
        "YieldDay": {"v": 482, "u": "Wh"},
        "YieldTotal": {"v": 111.3209991, "u": "kWh"},
        "Frequency": {"v": 49.99000168, "u": "Hz"},
        "Temperature": {"v": 21.60000038, "u": "°C"},
        "PowerFactor": {"v": 0, "u": "%"},
        "ReactivePower": {"v": 0, "u": "var"},
        "Efficiency": {"v": 0, "u": "%"}
      },
      "1": {
        "Power": {"v": 1.200000048, "u": "W"},
        "Voltage": {"v": 24.10000038, "u": "V"},
        "Current": {"v": 0.050000001, "u": "A"},
        "YieldDay": {"v": 482, "u": "Wh"},
        "YieldTotal": {"v": 111.3209991, "u": "kWh"},
        "Irradiation": {"v": 0.292682916, "u": "%"}
      },
      "events": 3
    }
  ]
}
'''

AHOY_TEST_DATA = '''
{
  "menu": {
    "name": ["Live", "Serial / Control", "Settings", "-", "REST API", "-", "Update", "System", "-", "Documentation"],
    "link": ["/live", "/serial", "/setup", null, "/api", null, "/update", "/system", null, "https://ahoydtu.de"],
    "trgt": [null, null, null, null, "_blank", null, null, null, null, "_blank"]
  },
  "generic": {
    "version": "0.5.70",
    "build": "d8e255d",
    "wifi_rssi": -72,
    "ts_uptime": 1602,
    "esp_type": "ESP8266"
  },
  "inverter": [
    {
      "enabled": true,
      "name": "hoymiles1",
      "channels": 1,
      "power_limit_read": 100,
      "last_alarm": "Inverter start",
      "ts_last_success": 1675243378,
      "ch": [
        [234.9, 0.1, 22.5, 50.04, 1, 7.5, 96.802, 16, 23.6, 95.339, 0],
        [33, 0.71, 23.6, 16, 96.802, 6.743]
      ],
      "ch_names": ["AC", "einzel"]
    }
  ],
  "refresh_interval": 5,
  "ch0_fld_units": ["V", "A", "W", "Hz", "", "°C", "kWh", "Wh", "W", "%", "var"],
  "ch0_fld_names": ["U_AC", "I_AC", "P_AC", "F_AC", "PF_AC", "Temp", "YieldTotal", "YieldDay", "P_DC", "Efficiency", "Q_AC"],
  "fld_units": ["V", "A", "W", "Wh", "kWh", "%"],
  "fld_names": ["U_DC", "I_DC", "P_DC", "YieldDay", "YieldTotal", "Irradiation"]
}
'''


class TestDTUClient(unittest.TestCase):
    """Test cases for DTU client functionality."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        self.dtu_config = DTUConfig(
            host="test.example.com",
            dtu_variant="opendtu",
            max_age_ts=600,
            esp8266_polling_interval=10000
        )
        self.dtu_client = DTUClient(self.dtu_config)
    
    def test_opendtu_reachable_detection(self) -> None:
        """Test OpenDTU reachable status detection."""
        # Test unreachable
        test_data = json.loads(OPENDTU_TEST_DATA)
        self.dtu_client.set_test_data(test_data)
        self.assertFalse(self.dtu_client.is_data_up_to_date(0))
        
        # Test reachable as string "1"
        test_data = json.loads(OPENDTU_TEST_DATA.replace('"reachable":false', '"reachable":"1"'))
        self.dtu_client.set_test_data(test_data)
        self.assertTrue(self.dtu_client.is_data_up_to_date(0))
        
        # Test reachable as integer 1
        test_data = json.loads(OPENDTU_TEST_DATA.replace('"reachable":false', '"reachable":1'))
        self.dtu_client.set_test_data(test_data)
        self.assertTrue(self.dtu_client.is_data_up_to_date(0))
        
        # Test reachable as boolean true
        test_data = json.loads(OPENDTU_TEST_DATA.replace('"reachable":false', '"reachable":true'))
        self.dtu_client.set_test_data(test_data)
        self.assertTrue(self.dtu_client.is_data_up_to_date(0))
    
    def test_opendtu_producing_values(self) -> None:
        """Test OpenDTU producing status affects values."""
        # Test not producing (should return 0 for power and current)
        test_data = json.loads(OPENDTU_TEST_DATA)
        self.dtu_client.set_test_data(test_data)
        
        # Make it reachable but not producing
        test_data['inverters'][0]['reachable'] = True
        test_data['inverters'][0]['producing'] = False
        self.dtu_client.set_test_data(test_data)
        
        power, total_energy, current, voltage = self.dtu_client.get_inverter_values(0)
        self.assertEqual(power, 0)
        self.assertEqual(current, 0)
        self.assertEqual(total_energy, 111.3209991)
        self.assertEqual(voltage, 235.1999969)
        
        # Test producing
        test_data['inverters'][0]['producing'] = "1"
        self.dtu_client.set_test_data(test_data)
        
        power, total_energy, current, voltage = self.dtu_client.get_inverter_values(0)
        self.assertEqual(power, 1)
        self.assertEqual(current, 1)
        self.assertEqual(total_energy, 111.3209991)
        self.assertEqual(voltage, 235.1999969)
    
    def test_ahoy_field_extraction(self) -> None:
        """Test Ahoy DTU field extraction."""
        self.dtu_config.dtu_variant = 'ahoy'
        self.dtu_client = DTUClient(self.dtu_config)
        
        test_data = json.loads(AHOY_TEST_DATA)
        self.dtu_client.set_test_data(test_data)
        
        power, total_energy, current, voltage = self.dtu_client.get_inverter_values(0)
        self.assertEqual(power, 22.5)
        self.assertEqual(total_energy, 96.802)
        self.assertEqual(current, 0.1)
        self.assertEqual(voltage, 234.9)
    
    def test_ahoy_timestamp_validation(self) -> None:
        """Test Ahoy DTU timestamp validation."""
        self.dtu_config.dtu_variant = 'ahoy'
        self.dtu_client = DTUClient(self.dtu_config)
        
        # Test old timestamp (should be outdated)
        test_data = json.loads(AHOY_TEST_DATA)
        self.dtu_client.set_test_data(test_data)
        self.assertFalse(self.dtu_client.is_data_up_to_date(0))
        
        # Test recent timestamp (should be up to date)
        recent_timestamp = int(time.time() - 10)  # 10 seconds ago
        test_data = json.loads(AHOY_TEST_DATA.replace('"ts_last_success":1675243378', f'"ts_last_success":{recent_timestamp}'))
        self.dtu_client.set_test_data(test_data)
        self.assertTrue(self.dtu_client.is_data_up_to_date(0))
    
    def test_polling_interval_esp8266(self) -> None:
        """Test ESP8266 polling interval detection."""
        self.dtu_config.dtu_variant = 'ahoy'
        self.dtu_client = DTUClient(self.dtu_config)
        
        test_data = json.loads(AHOY_TEST_DATA)
        self.dtu_client.set_test_data(test_data)
        
        # Should use ESP8266 interval
        interval = self.dtu_client.get_polling_interval()
        self.assertEqual(interval, 10000)
        
        # Test ESP32
        test_data = json.loads(AHOY_TEST_DATA.replace('"esp_type":"ESP8266"', '"esp_type":"ESP32"'))
        self.dtu_client.set_test_data(test_data)
        
        interval = self.dtu_client.get_polling_interval()
        self.assertEqual(interval, 5000)


class TestVenusDBusService(unittest.TestCase):
    """Test cases for Venus D-Bus service functionality."""
    
    def setUp(self) -> None:
        """Set up test fixtures."""
        # Create minimal config for testing
        self.dtu_config = DTUConfig(
            host="test.example.com",
            dtu_variant="opendtu",
            max_age_ts=600
        )
        self.dtu_client = DTUClient(self.dtu_config)
        
        # Create a mock config manager
        self.config_manager = MockConfigManager()
        
    def test_service_creation(self) -> None:
        """Test basic service creation."""
        # Test service can be created without errors
        service = VenusDBusService(0, self.config_manager, self.dtu_client, is_test=True)
        self.assertIsNotNone(service)
        self.assertEqual(service.inverter_number, 0)
    
    def test_get_values_delegation(self) -> None:
        """Test that service delegates value requests to DTU client."""
        service = VenusDBusService(0, self.config_manager, self.dtu_client, is_test=True)
        
        # Set test data
        test_data = json.loads(OPENDTU_TEST_DATA)
        test_data['inverters'][0]['reachable'] = True
        test_data['inverters'][0]['producing'] = True
        service.set_test_data(test_data)
        
        values = service.get_values_for_inverter()
        self.assertEqual(len(values), 4)  # power, total_energy, current, voltage


class MockConfigManager:
    """Mock configuration manager for testing."""
    
    def get_dtu_config(self) -> DTUConfig:
        return DTUConfig(
            host="test.example.com",
            dtu_variant="opendtu",
            max_age_ts=600
        )
    
    def get_inverter_config(self, inverter_number: int):
        from config import InverterConfig
        return InverterConfig(
            device_instance=34 + inverter_number,
            ac_position=1,
            phase="L1"
        )


def run_tests() -> None:
    """Run all tests."""
    unittest.main(verbosity=2)


if __name__ == "__main__":
    run_tests()