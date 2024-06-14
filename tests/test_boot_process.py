import unittest
from unittest.mock import patch, MagicMock
import os
from src.boot_process import load_secrets  # Importing load_secrets from src.boot_process

class TestLoadSecrets(unittest.TestCase):

    @patch('os.getenv', MagicMock(return_value='test_api_key'))
    def test_load_secrets_success(self):
        result = load_secrets()
        self.assertTrue(result)

    @patch('os.getenv', MagicMock(return_value=None))
    def test_load_secrets_missing_key(self):
        result = load_secrets()
        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()