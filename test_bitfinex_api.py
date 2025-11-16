#!/usr/bin/env python3
"""
Test script to verify Bitfinex API connection and get index price
"""
import asyncio
import json
import sys
from Providers.bfxapi.bfxapi.client import Client

async def test_bitfinex():
    # Load config
    with open('dealer_config.json', 'r') as f:
        config = json.load(f)
    
    api_key = config['bitfinex']['api_key']
    api_secret = config['bitfinex']['api_secret']
    product = config['bitfinex']['product']
    
    print(f"Testing Bitfinex API connection...")
    print(f"Product: {product}")
    print(f"API Key: {api_key[:10]}...")
    
    # Create client
    client = Client(API_KEY=api_key, API_SECRET=api_secret, logLevel='INFO')
    
    index_price = None
    connected = False
    
    def on_authenticated(auth_message=None):
        nonlocal connected
        connected = True
        print("✅ Authenticated with Bitfinex!")
    
    def on_status_update(status):
        nonlocal index_price
        if status and 'deriv_price' in status:
            index_price = status['deriv_price']
            print(f"✅ Index Price received: {index_price}")
    
    def on_error(error):
        print(f"❌ Error: {error}")
    
    # Set up event handlers
    client.ws.on('authenticated', on_authenticated)
    client.ws.on('status_update', on_status_update)
    client.ws.on('error', on_error)
    
    async def subscribe_after_auth(auth_message=None):
        """Subscribe to derivative status after authentication"""
        try:
            print("Subscribing to derivative status...")
            await client.ws.subscribe_derivative_status(product)
            print("✅ Subscribed to derivative status")
        except Exception as e:
            print(f"Error subscribing to derivative status: {e}")
    
    client.ws.on('authenticated', subscribe_after_auth)
    
    try:
        # Start connection using get_task_executable (like the dealer does)
        print("Connecting to Bitfinex...")
        task = asyncio.create_task(client.ws.get_task_executable())
        
        # Wait a bit for connection and data
        await asyncio.sleep(10)
        
        if connected:
            print("✅ Connection successful!")
        else:
            print("⚠️  Connection status unknown")
        
        if index_price:
            print(f"✅ Index Price: {index_price}")
        else:
            print("⚠️  No index price received yet")
        
        # Wait a bit more for status updates
        await asyncio.sleep(5)
        
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
    finally:
        try:
            await client.ws.stop()
        except:
            pass

if __name__ == '__main__':
    result = asyncio.run(test_bitfinex())
    sys.exit(0 if result else 1)

