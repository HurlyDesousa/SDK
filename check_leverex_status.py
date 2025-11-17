#!/usr/bin/env python3
"""
Check Leverex connection status via web interface API
"""
import json
import requests
import sys

def check_leverex_status():
    """Check Leverex status from web interface"""
    try:
        # Try to connect to web interface
        url = "http://localhost:5000/api/status"
        
        print("=" * 60)
        print("Leverex Connection Status Check")
        print("=" * 60)
        print(f"\n📡 Connecting to web interface: {url}")
        
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                
                print("✅ Web interface accessible")
                print("\n" + "=" * 60)
                print("Connection Status")
                print("=" * 60)
                
                # Leverex (Maker) status
                maker = data.get('authentication', {}).get('maker', {})
                print(f"\n🔵 Leverex (Maker):")
                print(f"  Connection: {maker.get('status', 'N/A')}")
                print(f"  Ready: {maker.get('ready', False)}")
                print(f"  Status Details: {maker.get('statusStr', 'N/A')}")
                
                # BitMEX (Taker) status
                taker = data.get('authentication', {}).get('taker', {})
                print(f"\n🟢 BitMEX (Taker):")
                print(f"  Connection: {taker.get('status', 'N/A')}")
                print(f"  Ready: {taker.get('ready', False)}")
                print(f"  Status Details: {taker.get('statusStr', 'N/A')}")
                
                # Dealer status
                dealer = data.get('authentication', {}).get('dealer', {})
                print(f"\n⚙️  Dealer:")
                print(f"  Ready: {dealer.get('ready', False)}")
                print(f"  Status: {dealer.get('statusStr', 'N/A')}")
                
                # Price data
                prices = data.get('price', {})
                print(f"\n💰 Prices:")
                leverex_price = prices.get('leverex')
                bitmex_price = prices.get('bitmex')
                print(f"  Leverex: {leverex_price if leverex_price else 'N/A'}")
                print(f"  BitMEX: {bitmex_price if bitmex_price else 'N/A'}")
                
                # Control status
                control = data.get('control', {})
                print(f"\n🎮 Dealer Control:")
                print(f"  Running: {control.get('running', False)}")
                
                print("\n" + "=" * 60)
                
                # Summary
                leverex_connected = maker.get('status') == 'Connected'
                leverex_ready = maker.get('ready', False)
                
                if leverex_connected and leverex_ready:
                    print("✅ Leverex API: CONNECTED and READY")
                    return True
                elif leverex_connected:
                    print("⚠️  Leverex API: CONNECTED but NOT READY")
                    print("   (May be waiting for session to open)")
                    return True
                else:
                    print("❌ Leverex API: NOT CONNECTED")
                    return False
                    
            else:
                print(f"❌ Web interface returned status: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to web interface")
            print("   Make sure the dealer container is running:")
            print("   docker exec leverex-dealer-staging python -c 'import requests; print(requests.get(\"http://localhost:5000/api/status\").json())'")
            return False
        except requests.exceptions.Timeout:
            print("❌ Web interface timeout")
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = check_leverex_status()
    sys.exit(0 if success else 1)

