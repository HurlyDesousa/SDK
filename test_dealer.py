import json
import traceback
from Providers.BitMEX import BitMEXProvider

with open('/app/config.json') as f:
    c = json.load(f)

print('Config loaded successfully')
print('BitMEX section:', 'bitmex' in c)
print('Product:', c.get('bitmex', {}).get('product', 'N/A'))

try:
    print('Creating BitMEXProvider...')
    provider = BitMEXProvider(c)
    print('Success!')
except Exception as e:
    print('Error:', str(e))
    print('Error type:', type(e).__name__)
    traceback.print_exc()

