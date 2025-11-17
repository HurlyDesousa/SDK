#!/usr/bin/env python3
"""
Test BitMEX API authentication following official documentation
Based on: https://www.bitmex.com/app/apiKeysUsage
"""
import asyncio
import json
import time
import hmac
import hashlib
import aiohttp

async def test_bitmex_auth():
    """Test BitMEX API authentication with /user endpoint"""
    # Load config
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
    
    base_url = 'https://testnet.bitmex.com' if testnet else 'https://www.bitmex.com'
    
    # According to BitMEX docs: https://www.bitmex.com/app/apiKeysUsage
    # Signature = HMAC-SHA256(verb + path + expires + body, secret)
    # For GET requests, body is empty string
    # IMPORTANT: The path must include /api/v1, not just the endpoint!
    
    path = '/api/v1/user'  # Full path including /api/v1
    verb = 'GET'
    expires = int(time.time()) + 60  # Expires in 60 seconds
    body = ''  # Empty for GET requests
    
    # Generate signature following official format
    # Format: verb + path + expires + body
    message = verb + path + str(expires) + body
    signature = hmac.new(
        api_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        'api-expires': str(expires),
        'api-key': api_key,
        'api-signature': signature,
        'Content-Type': 'application/json'
    }
    
    print("=" * 60)
    print("BitMEX API Authentication Test")
    print("=" * 60)
    print(f"API Key: {api_key[:15]}...")
    print(f"API Secret: {api_secret[:15]}...")
    print(f"Endpoint: {base_url}{path}")
    print(f"Testnet: {testnet}")
    print()
    print("Signature Details:")
    print(f"  Verb: {verb}")
    print(f"  Path: {path}")
    print(f"  Expires: {expires}")
    print(f"  Body: '{body}' (empty for GET)")
    print(f"  Message: {verb}{path}{expires}{body}")
    print(f"  Signature: {signature[:32]}...")
    print()
    
    try:
        async with aiohttp.ClientSession() as session:
            # Use full URL
            url = base_url + path
            async with session.get(
                url,
                headers=headers
            ) as response:
                response_text = await response.text()
                
                print("Response:")
                print(f"  Status: {response.status}")
                
                if response.status == 200:
                    result = json.loads(response_text)
                    print(f"  ✅ Authentication SUCCESSFUL!")
                    print()
                    print("User Information:")
                    print(f"    Username: {result.get('username', 'N/A')}")
                    print(f"    Email: {result.get('email', 'N/A')}")
                    print(f"    ID: {result.get('id', 'N/A')}")
                    print(f"    Firstname: {result.get('firstname', 'N/A')}")
                    print(f"    Lastname: {result.get('lastname', 'N/A')}")
                    print()
                    print("✅ API key is valid and authenticated!")
                    return True
                else:
                    print(f"  ❌ Authentication FAILED")
                    print(f"  Response: {response_text}")
                    
                    # Try to parse error
                    try:
                        if response_text:
                            error_data = json.loads(response_text)
                            if 'error' in error_data:
                                error_msg = error_data['error']
                                if isinstance(error_msg, dict):
                                    print(f"  Error Message: {error_msg.get('message', 'N/A')}")
                                    print(f"  Error Name: {error_msg.get('name', 'N/A')}")
                                else:
                                    print(f"  Error: {error_msg}")
                    except:
                        pass
                    
                    return False
                    
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = asyncio.run(test_bitmex_auth())
    exit(0 if success else 1)

