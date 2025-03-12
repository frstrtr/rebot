"""Utility functions for the P2P server."""

# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
# server/p2p/utils.py

import json
from twisted.internet import endpoints, error, reactor, protocol


def split_json_objects(message):
    """Split concatenated JSON objects in the message."""
    json_strings = []
    depth = 0
    start = 0
    for i, char in enumerate(message):
        if char == "{":
            if depth == 0:
                start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                json_strings.append(message[start : i + 1])
    return json_strings


def decode_nested_json(data):
    """Decode nested JSON strings in the data."""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                try:
                    decoded_value = json.loads(value)
                    data[key] = decode_nested_json(decoded_value)
                except json.JSONDecodeError:
                    data[key] = (
                        value.encode().decode("unicode_escape").replace("\\", "")
                    )
            elif isinstance(value, dict):
                data[key] = decode_nested_json(value)
            elif isinstance(value, list):
                data[key] = [decode_nested_json(item) for item in value]
    elif isinstance(data, list):
        return [decode_nested_json(item) for item in data]
    elif isinstance(data, str):
        try:
            decoded_value = json.loads(data)
            return decode_nested_json(decoded_value)
        except json.JSONDecodeError:
            return data.encode().decode("unicode_escape").replace("\\", "")
    return data


def find_available_port(start_port):
    """Find an available port starting from the given port."""
    port = start_port
    while True:
        try:
            endpoint = endpoints.TCP4ServerEndpoint(reactor, port)
            endpoint.listen(protocol.Factory())
            return port
        except error.CannotListenError:
            port += 1
