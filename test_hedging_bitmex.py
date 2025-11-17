#!/usr/bin/env python3
"""
Test script to open a 100 contract position on BitMEX XBTUSD to test hedging
"""
import asyncio
import json
import sys
import time
import hmac
import hashlib
import aiohttp
import logging
import os
from urllib.parse import urlencode

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

async def get_bitmex_bbo(api_key, api_secret, product, testnet=False):
    """Get Best Bid/Offer from BitMEX"""
    base_url = 'https://testnet.bitmex.com' if testnet else 'https://www.bitmex.com'
    path = '/api/v1/quote/bucketed'
    verb = 'GET'
    expires = int(time.time()) + 60
    
    # Get latest quote
    params = {
        'symbol': product,
        'binSize': '1m',
        'count': 1,
        'reverse': True
    }
    query_string = urlencode(params)
    full_path = f"{path}?{query_string}"
    
    def generate_signature(verb, path, expires, data=''):
        message = verb + path + str(expires) + (data if data else '')
        signature = hmac.new(
            api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    signature = generate_signature(verb, full_path, expires, '')
    
    headers = {
        'api-expires': str(expires),
        'api-key': api_key,
        'api-signature': signature,
        'Content-Type': 'application/json'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                base_url + full_path,
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and len(data) > 0:
                        return data[0].get('bidPrice'), data[0].get('askPrice')
    except Exception as e:
        logging.warning(f"Error getting BBO from quote API: {e}")
    
    # Fallback: try orderBookL2 endpoint
    path_l2 = '/api/v1/orderBook/L2'
    params_l2 = {'symbol': product, 'depth': 1}
    query_string_l2 = urlencode(params_l2)
    full_path_l2 = f"{path_l2}?{query_string_l2}"
    
    signature_l2 = generate_signature(verb, full_path_l2, expires, '')
    headers_l2 = {
        'api-expires': str(expires),
        'api-key': api_key,
        'api-signature': signature_l2,
        'Content-Type': 'application/json'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                base_url + full_path_l2,
                headers=headers_l2
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    best_bid = None
                    best_ask = None
                    for entry in data:
                        if entry.get('side') == 'Buy':
                            if best_bid is None or entry.get('price', 0) > best_bid:
                                best_bid = entry.get('price')
                        elif entry.get('side') == 'Sell':
                            if best_ask is None or entry.get('price', 0) < best_ask or best_ask is None:
                                best_ask = entry.get('price')
                    return best_bid, best_ask
    except Exception as e:
        logging.warning(f"Error getting BBO from orderBookL2: {e}")
    
    return None, None

async def place_bitmex_order(api_key, api_secret, product, quantity, testnet=False):
    """Place a limit order at BBO (Best Bid/Offer) on BitMEX"""
    base_url = 'https://testnet.bitmex.com' if testnet else 'https://www.bitmex.com'
    path = '/api/v1/order'  # Full path including /api/v1
    verb = 'POST'
    expires = int(time.time()) + 60
    
    # BitMEX requires orders in multiples of 100 for XBTUSD
    quantity_rounded = int(quantity / 100) * 100
    if quantity_rounded == 0 and abs(quantity) > 0:
        quantity_rounded = 100 if quantity > 0 else -100
    
    side = 'Buy' if quantity_rounded > 0 else 'Sell'
    order_qty = abs(quantity_rounded)
    
    # Get BBO prices
    best_bid, best_ask = await get_bitmex_bbo(api_key, api_secret, product, testnet)
    
    if side == 'Buy':
        if best_ask is None or best_ask <= 0:
            print("❌ ERROR: Best ask price not available, cannot place limit order")
            return False
        limit_price = best_ask
    else:  # Sell
        if best_bid is None or best_bid <= 0:
            print("❌ ERROR: Best bid price not available, cannot place limit order")
            return False
        limit_price = best_bid
    
    order_data = {
        'symbol': product,
        'side': side,
        'orderQty': order_qty,
        'ordType': 'Limit',
        'price': limit_price
    }
    
    def generate_signature(verb, path, expires, data_str=''):
        """Generate BitMEX API signature"""
        # BitMEX signature: verb + path + expires + data_string
        # For POST: data_str must be the exact JSON string that will be sent
        message = verb + path + str(expires) + (data_str if data_str else '')
        signature = hmac.new(
            api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    # Generate signature with order data (must match exactly what's sent in body)
    # BitMEX requires the JSON string in the signature to match the request body exactly
    # Sort keys and format without spaces - this must match the JSON sent in the request
    data_str = json.dumps(order_data, separators=(',', ':'), sort_keys=True)
    signature = generate_signature(verb, path, expires, data_str)
    
    # Debug: verify the data string matches what will be sent
    print(f"Debug - Signature message: {verb}{path}{expires}{data_str}")
    
    headers = {
        'api-expires': str(expires),
        'api-key': api_key,
        'api-signature': signature,
        'Content-Type': 'application/json'
    }
    
    print(f"Placing {side} limit order for {order_qty} contracts of {product} at {limit_price} (BBO)...")
    print(f"API Endpoint: {base_url}{path}")
    print(f"Order Data: {order_data}")
    print(f"BBO: Bid={best_bid}, Ask={best_ask}")
    print(f"Signature Data String: {data_str}")
    print(f"Expires: {expires}")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Send raw JSON string to ensure it matches what we signed
            url = base_url + path
            async with session.post(
                url,
                data=data_str,  # Use raw JSON string instead of json= parameter
                headers=headers
            ) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    result = json.loads(response_text)
                    print(f"\n✅ SUCCESS: Order placed!")
                    print(f"Order ID: {result.get('orderID', 'N/A')}")
                    print(f"Symbol: {result.get('symbol', 'N/A')}")
                    print(f"Side: {result.get('side', 'N/A')}")
                    print(f"Quantity: {result.get('orderQty', 'N/A')}")
                    print(f"Status: {result.get('ordStatus', 'N/A')}")
                    print(f"\nThe hedger should now detect this position and hedge it on Leverex.")
                    return True
                else:
                    print(f"\n❌ ERROR: Order failed")
                    print(f"Status Code: {response.status}")
                    print(f"Response: {response_text}")
                    print(f"Headers sent: api-key={api_key[:10]}..., expires={expires}")
                    
                    # Try to parse error
                    try:
                        if response_text:
                            error_data = json.loads(response_text)
                            if 'error' in error_data:
                                error_msg = error_data['error']
                                if isinstance(error_msg, dict):
                                    print(f"Error Message: {error_msg.get('message', 'N/A')}")
                                    print(f"Error Name: {error_msg.get('name', 'N/A')}")
                                else:
                                    print(f"Error: {error_msg}")
                    except:
                        if not response_text:
                            print("⚠️  Empty response - possible causes:")
                            print("  - API key doesn't have order placement permissions")
                            print("  - API key/secret mismatch")
                            print("  - Signature generation issue")
                    return False
                    
    except Exception as e:
        print(f"\n❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
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
        print("❌ Error: config.json not found in any of these paths:")
        for path in config_paths:
            print(f"  - {path}")
        return False
    
    api_key = config['bitmex']['api_key']
    api_secret = config['bitmex']['api_secret']
    product = config['bitmex']['product']
    testnet = config['bitmex'].get('testnet', False)
    
    print("=" * 60)
    print("BitMEX Hedging Test Script")
    print("=" * 60)
    print(f"Product: {product}")
    print(f"API Key: {api_key[:10]}...")
    print(f"Testnet: {testnet}")
    print(f"Order Quantity: 100 contracts")
    print("=" * 60)
    print()
    
    # Check for environment variable or command line arg to skip confirmation
    skip_confirmation = os.environ.get('SKIP_CONFIRMATION', '').lower() == 'true' or '--yes' in sys.argv
    
    if not testnet:
        if not skip_confirmation:
            print("⚠️  WARNING: You are about to place a REAL order on BitMEX!")
            print("This will open a 100 contract position with real money.")
            print()
            try:
                response = input("Type 'YES' to continue: ")
                if response != 'YES':
                    print("Cancelled.")
                    return False
            except EOFError:
                print("⚠️  No input available. Use --yes flag or SKIP_CONFIRMATION=true to skip confirmation.")
                print("Cancelled for safety.")
                return False
        else:
            print("⚠️  WARNING: Placing REAL order on BitMEX (confirmation skipped with --yes flag)")
            print("This will open a 100 contract position with real money.")
            print()
    
    # Place order for 100 contracts (long position)
    success = await place_bitmex_order(api_key, api_secret, product, 100, testnet)
    
    if success:
        print("\n" + "=" * 60)
        print("Next Steps:")
        print("1. Check your BitMEX position in the web interface")
        print("2. The hedger should detect the position imbalance")
        print("3. The hedger will place orders on Leverex to hedge")
        print("4. Monitor the dealer logs for hedging activity")
        print("=" * 60)
    
    return success

if __name__ == '__main__':
    result = asyncio.run(main())
    sys.exit(0 if result else 1)

