#!/usr/bin/env python3
"""
Test Leverex API connection and authentication
"""
import json
import asyncio
import logging
import traceback

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

async def test_leverex_connection():
    """Test Leverex provider connection"""
    try:
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
        
        print("\n" + "=" * 60)
        print("Leverex API Connection Test")
        print("=" * 60)
        
        # Check config
        leverex_config = config.get('leverex', {})
        print(f"\nConfiguration:")
        print(f"  API Endpoint: {leverex_config.get('api_endpoint', 'N/A')}")
        print(f"  Login Endpoint: {leverex_config.get('login_endpoint', 'N/A')}")
        print(f"  Public Endpoint: {leverex_config.get('public_endpoint', 'N/A')}")
        print(f"  Product: {leverex_config.get('product', 'N/A')}")
        print(f"  Key File: {leverex_config.get('key_file_path', 'N/A')}")
        
        # Import and create provider
        print(f"\n📦 Creating LeverexProvider...")
        from Providers.Leverex import LeverexProvider
        
        provider = LeverexProvider(config)
        print(f"✅ Provider created: {provider.name}")
        
        # Check connection setup
        print(f"\n🔌 Setting up connection...")
        connection_ready = False
        
        def on_ready():
            nonlocal connection_ready
            connection_ready = True
            print("✅ Connection ready callback triggered")
        
        provider.setup(on_ready)
        
        # Check if connection object exists
        if hasattr(provider, 'connection'):
            print(f"✅ Connection object exists")
            if provider.connection:
                print(f"  Connection type: {type(provider.connection).__name__}")
            else:
                print(f"  ⚠️  Connection object is None")
        else:
            print(f"❌ Connection object not found")
        
        # Check public connection
        if hasattr(provider, 'public_connection'):
            if provider.public_connection:
                print(f"✅ Public connection exists")
            else:
                print(f"  ℹ️  Public connection not configured")
        
        # Try to get connection status
        print(f"\n📊 Connection Status:")
        if hasattr(provider, 'isReady'):
            ready = provider.isReady()
            print(f"  Provider Ready: {ready}")
        else:
            print(f"  ⚠️  isReady() method not available")
        
        if hasattr(provider, 'getStatusStr'):
            try:
                status = provider.getStatusStr()
                print(f"  Status: {status}")
            except Exception as e:
                print(f"  Status: Error getting status - {e}")
        
        # Check if we can get async task
        print(f"\n🔄 Getting async task...")
        try:
            task = provider.getAsyncIOTask()
            if task:
                print(f"✅ Async task created")
                print(f"  Task type: {type(task).__name__}")
                # Don't actually run it, just check it can be created
                task.cancel()
            else:
                print(f"❌ Async task is None")
        except Exception as e:
            print(f"❌ Error creating async task: {e}")
            traceback.print_exc()
        
        print(f"\n" + "=" * 60)
        print("Test completed")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Exception during test: {e}")
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = asyncio.run(test_leverex_connection())
    exit(0 if success else 1)

