#!/usr/bin/env python3
"""
Test script to verify BitMEX API connection and get index price
"""
import asyncio
import json
import sys
import websockets
import hmac
import hashlib
import time

async def test_bitmex():
    # Load config
    with open('dealer_config.json', 'r') as f:
        config = json.load(f)
    
    api_key = config['bitmex']['api_key']
    api_secret = config['bitmex']['api_secret']
    product = config['bitmex']['product']
    testnet = config['bitmex'].get('testnet', False)
    
    ws_url = 'wss://testnet.bitmex.com/realtime' if testnet else 'wss://www.bitmex.com/realtime'
    
    print(f"Testing BitMEX API connection...")
    print(f"Product: {product}")
    print(f"API Key: {api_key[:10]}...")
    print(f"Testnet: {testnet}")
    
    def generate_signature(verb, path, expires, data=''):
        """Generate BitMEX API signature"""
        message = verb + path + str(expires) + data
        signature = hmac.new(
            api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    index_price = None
    connected = False
    
    try:
        async with websockets.connect(ws_url) as ws:
            print("✅ Connected to BitMEX WebSocket")
            connected = True
            
            # Authenticate
            expires = int(time.time()) + 5
            signature = generate_signature('GET', '/realtime', expires)
            auth_message = {
                'op': 'authKey',
                'args': [api_key, expires, signature]
            }
            await ws.send(json.dumps(auth_message))
            print("✅ Authentication request sent")
            
            # Subscribe to quote data
            subscribe_msg = {
                'op': 'subscribe',
                'args': [f'quote:{product}']
            }
            await ws.send(json.dumps(subscribe_msg))
            print(f"✅ Subscribed to quote:{product}")
            
            # Wait for messages
            await asyncio.sleep(2)
            
            # Read messages
            try:
                async for message in ws:
                    data = json.loads(message)
                    
                    if 'info' in data:
                        print(f"ℹ️  Info: {data['info']}")
                    elif 'error' in data:
                        print(f"❌ Error: {data['error']}")
                    elif 'table' in data and data['table'] == 'quote':
                        quotes = data.get('data', [])
                        for quote in quotes:
                            if quote.get('symbol') == product:
                                bid = quote.get('bidPrice')
                                ask = quote.get('askPrice')
                                if bid and ask:
                                    index_price = (float(bid) + float(ask)) / 2.0
                                    print(f"✅ Index Price received: {index_price}")
                                    return True
                    
                    # Timeout after 15 seconds
                    await asyncio.sleep(0.1)
            except asyncio.TimeoutError:
                pass
            
            if index_price:
                print(f"\n✅ SUCCESS: Index Price = {index_price}")
                return True
            else:
                print("\n⚠️  No index price received")
                return False
                
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    result = asyncio.run(test_bitmex())
    sys.exit(0 if result else 1)

