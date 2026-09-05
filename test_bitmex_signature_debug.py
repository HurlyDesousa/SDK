#!/usr/bin/env python3
"""
Debug BitMEX signature generation - test different formats.

Credentials must be supplied via environment variables; never commit real keys.
"""
import hmac
import hashlib
import os
import time

api_key = os.environ.get("BITMEX_API_KEY", "YOUR_BITMEX_API_KEY")
api_secret = os.environ.get("BITMEX_API_SECRET", "YOUR_BITMEX_API_SECRET")

path = '/user'
verb = 'GET'
expires = int(time.time()) + 60

# Test different signature formats
formats = [
    ("Format 1: verb + path + expires", f"{verb}{path}{expires}"),
    ("Format 2: verb + ' ' + path + expires", f"{verb} {path}{expires}"),
    ("Format 3: verb + path + ' ' + expires", f"{verb}{path} {expires}"),
    ("Format 4: verb + '/' + path + expires", f"{verb}/{path}{expires}"),
]

print("Testing different signature formats:")
print("=" * 60)
for name, message in formats:
    signature = hmac.new(
        api_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    print(f"{name}")
    print(f"  Message: {message}")
    print(f"  Signature: {signature}")
    print()
