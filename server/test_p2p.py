import unittest
import json
from unittest.mock import MagicMock
from p2p import P2PProtocol, P2PFactory

class TestP2PProtocol(unittest.TestCase):
    def setUp(self):
        self.factory = P2PFactory(uuid="test-uuid")
        self.protocol = P2PProtocol()
        self.protocol.factory = self.factory
        self.protocol.transport = MagicMock()
        self.protocol.transport.getPeer = MagicMock(return_value=MagicMock(host="127.0.0.1", port=9000))

    def test_split_json_objects(self):
        message = '{"key1": "value1"}{"key2": "value2"}'
        expected = ['{"key1": "value1"}', '{"key2": "value2"}']
        
        result = self.protocol.split_json_objects(message)
        
        self.assertEqual(result, expected)

    def test_decode_nested_json(self):
        data = {
            "key1": '{"nested_key1": "nested_value1"}',
            "key2": ['{"nested_key2": "nested_value2"}']
        }
        expected = {
            "key1": {"nested_key1": "nested_value1"},
            "key2": [{"nested_key2": "nested_value2"}]
        }
        
        result = self.protocol.decode_nested_json(data)
        
        self.assertEqual(result, expected)

if __name__ == "__main__":
    unittest.main()