import logging
import asyncio
import json
import time
import hmac
import hashlib
from decimal import Decimal
from datetime import datetime
import traceback
import websockets
from urllib.parse import urlencode
import aiohttp

from Factories.Provider.Factory import Factory, INITIALIZED
from Factories.Definitions import ProviderException, \
   AggregationOrderBook, PositionsReport, BalanceReport, \
   PriceEvent, CashOperation, OpenVolume, TheTxTracker, \
   checkConfig, double_eq
from leverex_core.utils import round_down


################################################################################
##
#### utilities
##
################################################################################
class BitMEXException(Exception):
   pass


################################################################################
##
#### StatusReporter classes
##
################################################################################
class BitMEXPosition(object):
   def __init__(self, position_data):
      self.id = position_data.get('symbol', '')
      self.amount = Decimal(str(position_data.get('currentQty', 0)))
      self.base_price = Decimal(str(position_data.get('avgEntryPrice', 0)))
      self.leverage = Decimal(str(position_data.get('leverage', 1)))
      self.liquidation_price = Decimal(str(position_data.get('liquidationPrice', 0))) if position_data.get('liquidationPrice') else None
      self.collateral = Decimal(str(position_data.get('margin', 0))) if position_data.get('margin') else None
      self.collateral_min = Decimal(str(position_data.get('initMargin', 0))) if position_data.get('initMargin') else None
      self.profit_loss = Decimal(str(position_data.get('unrealisedPnl', 0))) if position_data.get('unrealisedPnl') else None
      self.symbol = position_data.get('symbol', '')

   def __str__(self):
      lev = self.leverage
      if isinstance(lev, float):
         lev = round(lev, 2)

      liq = self.liquidation_price
      if isinstance(liq, float):
         liq = round(liq, 2)

      collateral = self.collateral
      if collateral != None:
         collateral = round(collateral, 2)

      text = "<id: {} -- vol: {}, price: {} -- lev: {}, liq: {}, col: {}>"
      return text.format(self.id, self.amount,
         round(self.base_price, 2), lev, liq, collateral)


class BitMEXPositionsReport(PositionsReport):
   def __init__(self, provider):
      super().__init__(provider)
      self.product = provider.product

      #convert position to BitMEXPosition
      self.positions = {}
      for symbol in provider.positions:
         self.positions[symbol] = {}
         for id in provider.positions[symbol]:
            self.positions[symbol][id] = BitMEXPosition(provider.positions[symbol][id])

   def __str__(self):
      #header
      exp = round_down(self.netExposure, 8) if self.netExposure else "N/A"
      result = " ** {} -- exp: {} -- product: {}\n".format(
         self.name, exp, self.product)

      #positions
      if not self.product in self.positions:
         result += "    N/A\n"
         return result

      productPos = self.positions[self.product]
      for pos in productPos:
         result += " *  {}\n".format(str(productPos[pos]))

      return result

   def getPnl(self):
      if not self.product in self.positions:
         return "N/A"

      if len(self.positions[self.product]) != 1:
         return "N/A"

      id = next(iter(self.positions[self.product]))
      pnl = self.positions[self.product][id].profit_loss
      if pnl == None:
         return "N/A"
      return round(pnl, 6)


################################################################################
class BitMEXBalanceReport(BalanceReport):
   def __init__(self, provider):
      super().__init__(provider)
      self.ccy = provider.ccy
      self.balances = provider.balances

   def __str__(self):
      result = " +- {}:\n".format(self.name)
      if not self.balances:
         result += " +  <N/A>"
         return result

      for ccy in self.balances:
         total = self.balances[ccy].get('total', 0)
         free = self.balances[ccy].get('free', 0)
         result += " +    <[{}] total: {}, free: {}>\n".format(
            ccy, round(total, 2), round(free, 2))

      return result


################################################################################
##
#### Provider
##
################################################################################
class BitMEXProvider(Factory):
   required_settings = {
      'bitmex': [
         'api_key', 'api_secret',
         'product',
         'collateral_pct',
         'max_collateral_deviation'
      ],
      'hedger': [
         'max_offer_volume'
      ]
   }

   #############################################################################
   #### setup
   #############################################################################
   def __init__(self, config):
      super().__init__("BitMEX")
      self.connection = None
      self.websocket = None
      self.positions = {}
      self.balances = {}
      self.lastReadyState = False
      self.indexPrice = 0
      self._connected = False
      self.best_bid = None  # Best bid price (highest buy price)
      self.best_ask = None  # Best ask price (lowest sell price)

      #check for required config entries
      checkConfig(config, self.required_settings)

      self.config = config['bitmex']
      self.product = self.config['product']
      self.ccy = 'USD'  # BitMEX uses USD for XBTUSD
      self.ccy_base = 'XBT'  # Bitcoin
      self.collateral_pct = self.config['collateral_pct']
      self.setLeverage(100/self.collateral_pct)
      self.max_collateral_deviation = self.config['max_collateral_deviation']
      self.max_offer_volume = config['hedger']['max_offer_volume']

      # setup BitMEX connection
      self.order_book = AggregationOrderBook()
      self.api_key = self.config['api_key']
      self.api_secret = self.config['api_secret']
      self.testnet = self.config.get('testnet', False)
      self.ws_url = 'wss://testnet.bitmex.com/realtime' if self.testnet else 'wss://www.bitmex.com/realtime'

   def generate_signature(self, verb, path, expires, data=''):
      """Generate BitMEX API signature"""
      message = verb + path + str(expires) + data
      signature = hmac.new(
         self.api_secret.encode('utf-8'),
         message.encode('utf-8'),
         hashlib.sha256
      ).hexdigest()
      return signature

   async def authenticate(self):
      """Authenticate with BitMEX WebSocket"""
      expires = int(time.time()) + 5
      signature = self.generate_signature('GET', '/realtime', expires)
      
      auth_message = {
         'op': 'authKey',
         'args': [self.api_key, expires, signature]
      }
      
      await self.websocket.send(json.dumps(auth_message))
      logging.info("[BitMEX] Authentication request sent")

   async def subscribe(self, topic, symbol=None):
      """Subscribe to BitMEX WebSocket topics"""
      if symbol:
         subscribe_msg = {
            'op': 'subscribe',
            'args': [f'{topic}:{symbol}']
         }
      else:
         subscribe_msg = {
            'op': 'subscribe',
            'args': [topic]
         }
      
      await self.websocket.send(json.dumps(subscribe_msg))
      logging.info(f"[BitMEX] Subscribed to {subscribe_msg['args']}")

   async def websocket_loop(self):
      """Main WebSocket message loop"""
      try:
         async with websockets.connect(self.ws_url) as ws:
            self.websocket = ws
            logging.info(f"[BitMEX] Connected to {self.ws_url}")
            
            # Authenticate
            await self.authenticate()
            await asyncio.sleep(1)
            
            # Subscribe to required data
            await self.subscribe('position', self.product)
            await self.subscribe('margin')  # Margin table doesn't support symbol filtering
            await self.subscribe('orderBookL2', self.product)
            await self.subscribe('quote', self.product)
            await self.subscribe('instrument', self.product)  # Subscribe to instrument for indexPrice
            await asyncio.sleep(1)
            
            await super().setConnected(True)
            await super().fetchInitialData()
            
            # Message loop
            async for message in ws:
               try:
                  data = json.loads(message)
                  await self.handle_message(data)
               except json.JSONDecodeError:
                  logging.error(f"[BitMEX] Failed to parse message: {message}")
               except Exception as e:
                  logging.error(f"[BitMEX] Error handling message: {e}")
                  traceback.print_exc()
                  
      except Exception as e:
         logging.error(f"[BitMEX] WebSocket error: {e}")
         traceback.print_exc()
         self._connected = False
         loop = asyncio.get_running_loop()
         loop.stop()

   async def handle_message(self, data):
      """Handle incoming WebSocket messages"""
      if 'table' in data and 'action' in data:
         table = data['table']
         action = data['action']
         
         if table == 'position':
            if action == 'partial' or action == 'update':
               await self.on_position_update(data.get('data', []))
         elif table == 'margin':
            if action == 'partial' or action == 'update':
               await self.on_margin_update(data.get('data', []))
         elif table == 'orderBookL2':
            if action == 'partial':
               self.on_order_book_snapshot(data.get('data', []))
            elif action == 'update' or action == 'insert' or action == 'delete':
               await self.on_order_book_update(data.get('data', []))
         elif table == 'quote':
            if action == 'partial' or action == 'update':
               await self.on_quote_update(data.get('data', []))
         elif table == 'instrument':
            if action == 'partial' or action == 'update':
               await self.on_instrument_update(data.get('data', []))
      elif 'info' in data:
         logging.info(f"[BitMEX] Info: {data['info']}")
      elif 'error' in data:
         logging.error(f"[BitMEX] Error: {data['error']}")

   def setup(self, callback):
      super().setup(callback)

   async def loadAddresses(self, callback):
      # BitMEX doesn't require address loading
      await callback()

   def setWithdrawAddresses(self, addresses):
      self.chainAddresses.setWithdrawAddresses(addresses)

   async def loadWithdrawals(self, callback):
      await callback()

   #############################################################################
   #### events
   #############################################################################

   async def on_position_update(self, positions_data):
      """Handle position updates"""
      for pos_data in positions_data:
         symbol = pos_data.get('symbol', '')
         if symbol not in self.positions:
            self.positions[symbol] = {}
         
         # Use symbol as ID for BitMEX (one position per symbol)
         self.positions[symbol][symbol] = pos_data
      
      if not hasattr(self, '_positions_initialized') or self._positionsInitialized == 0:
         await super().setInitPosition()
         await self.evaluateReadyState()
      else:
         await super().onPositionUpdate()

   async def on_margin_update(self, margin_data):
      """Handle margin/balance updates"""
      for margin in margin_data:
         currency = margin.get('currency', 'XBt')  # BitMEX uses XBt (satoshis)
         if currency == 'XBt':
            # Convert XBt to BTC (1 XBt = 0.00000001 BTC)
            total = Decimal(str(margin.get('marginBalance', 0))) * Decimal('0.00000001')
            available = Decimal(str(margin.get('availableMargin', 0))) * Decimal('0.00000001')
         else:
            total = Decimal(str(margin.get('marginBalance', 0)))
            available = Decimal(str(margin.get('availableMargin', 0)))
         
         if currency not in self.balances:
            self.balances[currency] = {}
         
         self.balances[currency]['total'] = float(total)
         self.balances[currency]['free'] = float(available)
      
      if not hasattr(self, '_balance_initialized') or self._balanceInitialized == 0:
         await super().setInitBalance()
         await self.evaluateReadyState()
      else:
         await self.onBalanceUpdate()

   def on_order_book_snapshot(self, snapshot_data):
      """Handle order book snapshot"""
      # Update best bid/ask from order book
      best_bid = None
      best_ask = None
      for entry in snapshot_data:
         if entry.get('symbol') == self.product:
            side = entry.get('side')
            price = entry.get('price')
            if side == 'Buy' and price:
               if best_bid is None or price > best_bid:
                  best_bid = float(price)
            elif side == 'Sell' and price:
               if best_ask is None or price < best_ask:
                  best_ask = float(price)
      
      if best_bid:
         self.best_bid = best_bid
      if best_ask:
         self.best_ask = best_ask

   async def on_order_book_update(self, update_data):
      """Handle order book updates"""
      # Update best bid/ask from order book updates
      for entry in update_data:
         if entry.get('symbol') == self.product:
            side = entry.get('side')
            price = entry.get('price')
            size = entry.get('size', 0)
            
            if side == 'Buy' and price:
               if size > 0:
                  # New or updated bid
                  if self.best_bid is None or price > self.best_bid:
                     self.best_bid = float(price)
               else:
                  # Removed bid, need to recalculate
                  if self.best_bid and price == self.best_bid:
                     # The best bid was removed, need to find new best
                     self.best_bid = None  # Will be updated on next snapshot or quote
            elif side == 'Sell' and price:
               if size > 0:
                  # New or updated ask
                  if self.best_ask is None or price < self.best_ask:
                     self.best_ask = float(price)
               else:
                  # Removed ask, need to recalculate
                  if self.best_ask and price == self.best_ask:
                     # The best ask was removed, need to find new best
                     self.best_ask = None  # Will be updated on next snapshot or quote
      
      await super().onOrderBookUpdate()

   async def on_instrument_update(self, instrument_data):
      """Handle instrument updates (includes indexPrice)"""
      for instrument in instrument_data:
         if instrument.get('symbol') == self.product:
            # Use the official indexPrice from BitMEX
            index_price = instrument.get('indexPrice')
            if index_price:
               self.indexPrice = float(index_price)
               logging.debug(f"[BitMEX] Index price updated: {self.indexPrice}")
               await self.dealerCallback(self, PriceEvent)
            # Also update lastPrice if available (last traded price)
            last_price = instrument.get('lastPrice')
            if last_price:
               logging.debug(f"[BitMEX] Last price: {last_price}")

   async def on_quote_update(self, quote_data):
      """Handle quote updates (price updates) - used for BBO tracking"""
      for quote in quote_data:
         if quote.get('symbol') == self.product:
            bid = quote.get('bidPrice')
            ask = quote.get('askPrice')
            if bid and ask:
               self.best_bid = float(bid)
               self.best_ask = float(ask)
               # Only use mid-price as fallback if indexPrice hasn't been set yet
               if self.indexPrice == 0:
                  self.indexPrice = (self.best_bid + self.best_ask) / 2.0
                  logging.debug(f"[BitMEX] Using mid-price fallback: {self.indexPrice}")
                  await self.dealerCallback(self, PriceEvent)

   #############################################################################
   #### Provider overrides
   #############################################################################

   def getAsyncIOTask(self):
      return asyncio.create_task(self.websocket_loop())

   def isReady(self):
      return self.lastReadyState

   def getMinTargetBalance(self, target):
      if not self.isReady():
         return None

      if self.ccy not in self.balances:
         return None

      balance = self.balances[self.ccy]
      total = balance.get('total', 0)

      return min(target, Decimal(total))

   def getOpenVolume(self):
      if not self.isReady():
         return None

      if self.ccy not in self.balances:
         return None
      
      balance = self.balances[self.ccy]
      free = balance.get('free', 0)
      
      # Simplified - would need proper order book integration
      price = self.indexPrice if self.indexPrice else 0
      if price == 0:
         return None

      return OpenVolume(free, 0, price * self.getCollateralRatio(), 0, price * self.getCollateralRatio())

   def getCashMetrics(self):
      if self.ccy not in self.balances:
         return None
      
      balance = self.balances[self.ccy]
      if 'total' not in balance:
         return None

      return {
         'total': Decimal(balance['total']),
         'pending': Decimal(0),
         'ratio': self.getCollateralRatio()
      }

   def getPendingBalances(self):
      return {}

   def getExposure(self):
      if not self.isReady():
         return None

      if self.product not in self.positions:
         return Decimal(0)
      
      exposure = Decimal(0)
      for id in self.positions[self.product]:
         pos = self.positions[self.product][id]
         if isinstance(pos, dict):
            exposure += Decimal(str(pos.get('currentQty', 0)))
         else:
            exposure += pos.amount
      
      return exposure

   async def updateExposure(self, quantity):
      """Update exposure by placing limit order at BBO (Best Bid/Offer)"""
      if not self.isReady():
         logging.warning(f"[BitMEX] Cannot update exposure - provider not ready")
         return
      
      quantity = Decimal(str(quantity))
      if quantity == 0:
         logging.debug(f"[BitMEX] No exposure change needed")
         return
      
      # BitMEX requires orders in multiples of 100 for XBTUSD
      # Round to nearest 100
      quantity_rounded = int(quantity / 100) * 100
      if quantity_rounded == 0 and abs(quantity) > 0:
         # If less than 100, round to 100 in the direction of the order
         quantity_rounded = 100 if quantity > 0 else -100
      
      if quantity_rounded == 0:
         logging.debug(f"[BitMEX] Quantity {quantity} rounded to 0, skipping order")
         return
      
      side = 'Buy' if quantity_rounded > 0 else 'Sell'
      order_qty = abs(quantity_rounded)
      
      # Get BBO price: for Buy use best ask, for Sell use best bid
      if side == 'Buy':
         if self.best_ask is None or self.best_ask <= 0:
            logging.warning(f"[BitMEX] Best ask price not available, cannot place limit order")
            return
         limit_price = self.best_ask
      else:  # Sell
         if self.best_bid is None or self.best_bid <= 0:
            logging.warning(f"[BitMEX] Best bid price not available, cannot place limit order")
            return
         limit_price = self.best_bid
      
      logging.info(f"[BitMEX] Placing {side} limit order for {order_qty} contracts at {limit_price} (BBO, requested: {quantity})")
      
      try:
         # Use REST API to place limit order at BBO
         base_url = 'https://testnet.bitmex.com' if self.testnet else 'https://www.bitmex.com'
         path = '/api/v1/order'  # Full path including /api/v1 for signature
         verb = 'POST'
         expires = int(time.time()) + 60

         order_data = {
            'symbol': self.product,
            'side': side,
            'orderQty': order_qty,
            'ordType': 'Limit',
            'price': limit_price
         }

         # BitMEX requires sorted keys for signature
         data_str = json.dumps(order_data, separators=(',', ':'), sort_keys=True)
         signature = self.generate_signature(verb, path, expires, data_str)
         
         headers = {
            'api-expires': str(expires),
            'api-key': self.api_key,
            'api-signature': signature,
            'Content-Type': 'application/json'
         }
         
         async with aiohttp.ClientSession() as session:
            # Use full URL and send raw JSON string to match signature
            url = base_url + path
            async with session.post(
               url,
               data=data_str,  # Send raw JSON string to match signature
               headers=headers
            ) as response:
               if response.status == 200:
                  result = await response.json()
                  logging.info(f"[BitMEX] Order placed successfully: {result.get('orderID', 'N/A')}")
               else:
                  error_text = await response.text()
                  logging.error(f"[BitMEX] Order failed: {response.status} - {error_text}")
                  
      except Exception as e:
         logging.error(f"[BitMEX] Error placing order: {e}")
         traceback.print_exc()

   def getPositions(self):
      return BitMEXPositionsReport(self)

   def getBalance(self):
      return BitMEXBalanceReport(self)

   def getOpenPrice(self):
      if self.product not in self.positions:
         return None
      if len(self.positions[self.product]) != 1:
         return None

      id = next(iter(self.positions[self.product]))
      pos = self.positions[self.product][id]
      if isinstance(pos, dict):
         return Decimal(str(pos.get('avgEntryPrice', 0)))
      return pos.base_price

   async def withdraw(self, amount, callback):
      # BitMEX withdrawal would need REST API
      logging.warning("[BitMEX] withdraw not implemented yet")
      await callback()

   async def cancelWithdrawals(self):
      pass

   def withdrawalsLoaded(self):
      return True

   async def checkCollateral(self, openPrice):
      """Check and adjust collateral"""
      # BitMEX handles collateral differently - this is a placeholder
      logging.debug(f"[BitMEX] checkCollateral called with {openPrice}")

   async def onBalanceUpdate(self):
      await super().onBalanceUpdate()

   #############################################################################
   #### state
   #############################################################################
   def getStatusStr(self):
      """Get detailed status string for BitMEX provider"""
      if not self.isReady():
         if not self._connected:
            return "awaiting connection..."
         if self._balanceInitialized != INITIALIZED:
            return f"awaiting balance snapshot... (state: {self._balanceInitialized})"
         if self._positionsInitialized != INITIALIZED:
            return f"awaiting positions snapshot... (state: {self._positionsInitialized})"
      
      # Provider is ready, return detailed status
      status_parts = []
      
      if self._connected:
         status_parts.append("Connected")
      else:
         status_parts.append("Disconnected")
      
      if self.websocket:
         status_parts.append("WebSocket active")
      else:
         status_parts.append("WebSocket inactive")
      
      if self.indexPrice and self.indexPrice > 0:
         status_parts.append(f"Price: {self.indexPrice:.2f}")
      else:
         status_parts.append("No price data")
      
      if self.product in self.positions and len(self.positions[self.product]) > 0:
         pos_count = len(self.positions[self.product])
         status_parts.append(f"{pos_count} position(s)")
      else:
         status_parts.append("No positions")
      
      if self.balances:
         status_parts.append("Balance loaded")
      else:
         status_parts.append("No balance data")
      
      return " | ".join(status_parts) if status_parts else "Ready"

   async def evaluateReadyState(self):
      currentReadyState = super().isReady()
      if self.lastReadyState == currentReadyState:
         return

      self.lastReadyState = currentReadyState
      await super().onReady()

