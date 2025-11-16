import json
import traceback
from Providers.Bitfinex import BitfinexProvider

with open('/app/config.json') as f:
    c = json.load(f)

print('Config loaded successfully')
print('Bitfinex section:', 'bitfinex' in c)
print('exposure_cooldown in bitfinex:', 'exposure_cooldown' in c.get('bitfinex', {}))

try:
    print('Creating BitfinexProvider...')
    provider = BitfinexProvider(c)
    print('Success!')
except Exception as e:
    print('Error:', str(e))
    print('Error type:', type(e).__name__)
    traceback.print_exc()

