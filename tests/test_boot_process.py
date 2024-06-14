import unittest
from unittest.mock import patch, MagicMock
import os
from src.boot_process import load_secrets  # Importing load_secrets from src.boot_process
from requests.exceptions import ConnectionError, Timeout
from src.boot_process import check_internet_connection
import requests


class TestLoadSecrets(unittest.TestCase):

    @patch('os.getenv', MagicMock(return_value='test_api_key'))
    def test_load_secrets_success(self):
        result = load_secrets()
        self.assertTrue(result)

    @patch('os.getenv', MagicMock(return_value=None))
    def test_load_secrets_missing_key(self):
        result = load_secrets()
        self.assertFalse(result)

class TestCheckInternetConnection(unittest.TestCase):

    @patch('requests.get')
    def test_check_internet_connection_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = check_internet_connection()
        self.assertTrue(result)

    @patch('requests.get')
    def test_check_internet_connection_connection_error(self, mock_get):
        mock_get.side_effect = ConnectionError()

        result = check_internet_connection()
        self.assertFalse(result)

    @patch('requests.get')
    def test_check_internet_connection_timeout(self, mock_get):
        mock_get.side_effect = Timeout()

        result = check_internet_connection()
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()