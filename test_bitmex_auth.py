#!/usr/bin/env python3
"""
Test BitMEX API authentication with a simple endpoint
"""
import asyncio
import json
import time
import hmac
import hashlib
import aiohttp

async def test_bitmex_auth():
    # Load config - try multiple paths
    config = None
    config_paths = ['/app/config.json', 'dealer_config.json', 'config.json']
    for config_path in config_paths:
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                print(f"✅ Loaded config from: {config_path}")
                break
        except FileNotFoundError:
            continue
    
    if config is None:
        print("❌ Error: config.json not found")
        return False
    
    api_key = config['bitmex']['api_key']
    api_secret = config['bitmex']['api_secret']
    testnet = config['bitmex'].get('testnet', False)
    
    base_url = 'https://testnet.bitmex.com/api/v1' if testnet else 'https://www.bitmex.com/api/v1'
    
    # Test with /user endpoint (requires authentication but no special permissions)
    path = '/user'
    verb = 'GET'
    expires = int(time.time()) + 60
    
    def generate_signature(verb, path, expires, data=''):
        # BitMEX signature: verb + path + expires + data (empty string for GET)
        message = verb + path + str(expires) + (str(data) if data else '')
        signature = hmac.new(
            api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    # For GET requests, data is empty string
    signature = generate_signature(verb, path, expires, '')
    
    headers = {
        'api-expires': str(expires),
        'api-key': api_key,
        'api-signature': signature,
        'Content-Type': 'application/json'
    }
    
    print(f"Testing BitMEX API authentication...")
    print(f"API Key: {api_key[:10]}...")
    print(f"Endpoint: {base_url}{path}")
    print(f"Testnet: {testnet}")
    print()
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                base_url + path,
                headers=headers
            ) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    result = json.loads(response_text)
                    print(f"✅ Authentication successful!")
                    print(f"Username: {result.get('username', 'N/A')}")
                    print(f"Email: {result.get('email', 'N/A')}")
                    print(f"ID: {result.get('id', 'N/A')}")
                    print()
                    print("API key is valid and authenticated!")
                    return True
                else:
                    print(f"❌ Authentication failed")
                    print(f"Status Code: {response.status}")
                    print(f"Response: {response_text}")
                    return False
                    
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    asyncio.run(test_bitmex_auth())

