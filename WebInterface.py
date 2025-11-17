import logging
import threading
import json
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

class WebInterface:
    def __init__(self, dealer, port=5000):
        self.dealer = dealer
        self.port = port
        self.app = Flask(__name__, template_folder='templates', static_folder='static', static_url_path='/static')
        CORS(self.app)
        self.server_thread = None
        # Check if dealer is stopped by default (stop flag file exists)
        import os
        stop_flag_file = '/app/.dealer_stop'
        self.dealer_running = not os.path.exists(stop_flag_file)  # Track dealer running state
        self._setup_routes()
        
    def _setup_routes(self):
        @self.app.route('/')
        def index():
            return render_template('dealer_interface.html')
        
        @self.app.route('/api/status')
        def get_status():
            try:
                maker = self.dealer.maker
                taker = self.dealer.taker
                
                # Get authentication status
                # Maker (Leverex) uses websocket connection
                maker_auth = "Connected"
                if maker and maker.connection:
                    if hasattr(maker.connection, 'websocket') and maker.connection.websocket:
                        maker_auth = "Connected"
                    else:
                        maker_auth = "Disconnected"
                else:
                    maker_auth = "Disconnected"
                
                # Taker (BitMEX) uses websocket connection
                taker_auth = "Connected"
                if taker:
                    # BitMEX connection has websocket attribute
                    if hasattr(taker, 'websocket') and taker.websocket:
                        taker_auth = "Connected"
                    elif hasattr(taker, '_connected') and taker._connected:
                        taker_auth = "Connected"
                    else:
                        taker_auth = "Disconnected"
                else:
                    taker_auth = "Disconnected"
                
                # Get ready status
                maker_ready = maker.isReady() if maker else False
                taker_ready = taker.isReady() if taker else False
                dealer_ready = self.dealer.isReady()
                
                # Get price data separately for Leverex (maker) and BitMEX (taker)
                leverex_price = None
                bitmex_price = None
                
                # Get Leverex (maker) price
                try:
                    if maker:
                        if hasattr(maker, 'indexPrice'):
                            logging.info(f"Leverex indexPrice attribute exists, value: {maker.indexPrice}, type: {type(maker.indexPrice)}")
                            if maker.indexPrice is not None and maker.indexPrice != 0:
                                leverex_price = float(maker.indexPrice)
                                logging.info(f"Got index price from Leverex: {leverex_price}")
                            else:
                                logging.info(f"Leverex indexPrice is None or 0: {maker.indexPrice}")
                        else:
                            logging.warning("Leverex provider does not have indexPrice attribute")
                    else:
                        logging.warning("Maker (Leverex) provider is None")
                except (ValueError, TypeError, AttributeError) as e:
                    logging.error(f"Error getting Leverex price: {e}", exc_info=True)
                
                # Get BitMEX (taker) price - try indexPrice first
                try:
                    if taker and hasattr(taker, 'indexPrice'):
                        if taker.indexPrice is not None and taker.indexPrice != 0:
                            bitmex_price = float(taker.indexPrice)
                            logging.debug(f"Got index price from BitMEX: {bitmex_price}")
                except (ValueError, TypeError, AttributeError) as e:
                    logging.debug(f"Error getting BitMEX price: {e}")
                
                session_open_price = None
                if maker and maker.currentSession:
                    try:
                        session_open_price = maker.currentSession.getOpenPrice()
                    except:
                        pass
                
                # Get offers
                bids = []
                asks = []
                if maker and hasattr(maker, 'offers') and maker.offers:
                    try:
                        bids = [{'price': float(bid.bid), 'volume': float(bid.volume)} 
                                for bid in maker.offers.bids[:10] if bid.isValid()]  # Top 10 bids
                        asks = [{'price': float(ask.ask), 'volume': float(ask.volume)} 
                                for ask in maker.offers.asks[:10] if ask.isValid()]  # Top 10 asks
                    except (AttributeError, TypeError, ValueError) as e:
                        logging.debug(f"Error getting offers: {e}")
                        bids = []
                        asks = []
                
                # Get status strings with more detail
                maker_status = "N/A"
                if maker:
                    try:
                        maker_status = maker.getStatusStr() if hasattr(maker, 'getStatusStr') else "Status unavailable"
                    except Exception as e:
                        maker_status = f"Error: {str(e)}"
                
                taker_status = "N/A"
                if taker:
                    try:
                        taker_status = taker.getStatusStr() if hasattr(taker, 'getStatusStr') else "Status unavailable"
                    except Exception as e:
                        taker_status = f"Error: {str(e)}"
                
                dealer_status = "N/A"
                if hasattr(self.dealer, 'getStatusStr'):
                    try:
                        dealer_status = self.dealer.getStatusStr()
                    except Exception as e:
                        dealer_status = f"Error: {str(e)}"
                elif hasattr(self.dealer, 'isReady'):
                    dealer_status = "Ready" if self.dealer.isReady() else "Not Ready"
                
                return jsonify({
                    'authentication': {
                        'maker': {
                            'status': maker_auth,
                            'ready': maker_ready,
                            'statusStr': maker_status
                        },
                        'taker': {
                            'status': taker_auth,
                            'ready': taker_ready,
                            'statusStr': taker_status
                        },
                        'dealer': {
                            'ready': dealer_ready,
                            'statusStr': dealer_status
                        }
                    },
                    'price': {
                        'leverex': leverex_price,
                        'bitmex': bitmex_price,
                        'sessionOpen': session_open_price
                    },
                    'offers': {
                        'bids': bids,
                        'asks': asks
                    },
                    'control': {
                        'running': self.dealer_running
                    }
                })
            except Exception as e:
                logging.error(f"Error getting status: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/control', methods=['POST'])
        def control_dealer():
            try:
                import json as json_lib
                data = json_lib.loads(request.data)
                action = data.get('action', '')
                
                if action == 'stop':
                    self.dealer_running = False
                    # Create stop flag file (don't exit - dealer will stop on next check)
                    import os
                    stop_flag_file = '/app/.dealer_stop'
                    try:
                        with open(stop_flag_file, 'w') as f:
                            f.write('stop')
                        logging.info("Stop flag file created - dealer will stop after current operations")
                    except Exception as e:
                        logging.error(f"Error creating stop flag: {e}")
                    
                    return jsonify({'status': 'stopped', 'message': 'Dealer stop requested. It will stop after current operations complete.'})
                
                elif action == 'start':
                    self.dealer_running = True
                    # Remove stop flag file (don't exit - let dealer start naturally)
                    import os
                    stop_flag_file = '/app/.dealer_stop'
                    try:
                        if os.path.exists(stop_flag_file):
                            os.remove(stop_flag_file)
                            logging.info("Stop flag file removed - dealer will start")
                    except Exception as e:
                        logging.error(f"Error removing stop flag: {e}")
                    
                    return jsonify({'status': 'started', 'message': 'Dealer start requested. It will start in a moment.'})
                
                else:
                    return jsonify({'error': 'Invalid action'}), 400
                    
            except Exception as e:
                logging.error(f"Error in control endpoint: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/control/status', methods=['GET'])
        def get_control_status():
            return jsonify({'running': self.dealer_running})
        
        @self.app.route('/api/positions')
        def get_positions():
            try:
                maker = self.dealer.maker
                taker = self.dealer.taker
                
                positions = {
                    'leverex': [],
                    'bitmex': [],
                    'net_exposure': {
                        'leverex': 0,
                        'bitmex': 0,
                        'total': 0
                    }
                }
                
                # Get Leverex positions
                if maker:
                    try:
                        leverex_positions = maker.getPositions()
                        if leverex_positions and hasattr(leverex_positions, 'orderData') and leverex_positions.orderData:
                            for order_id, order in leverex_positions.orderData.orders.items():
                                if hasattr(order, 'is_trade_position') and order.is_trade_position():
                                    pos_data = {
                                        'id': str(order_id),
                                        'side': 'SELL' if (hasattr(order, 'is_sell') and order.is_sell()) else 'BUY',
                                        'volume': float(order.quantity) if hasattr(order, 'quantity') else 0,
                                        'price': float(order.price) if hasattr(order, 'price') else 0,
                                        'pnl': float(order.trade_pnl) if hasattr(order, 'trade_pnl') and order.trade_pnl is not None else None,
                                        'is_taker': bool(order.is_taker) if hasattr(order, 'is_taker') else False,
                                        'type': 'TAKER' if (hasattr(order, 'is_taker') and order.is_taker) else 'MAKER'
                                    }
                                    positions['leverex'].append(pos_data)
                        
                        # Get net exposure
                        if hasattr(leverex_positions, 'netExposure'):
                            positions['net_exposure']['leverex'] = float(leverex_positions.netExposure) if leverex_positions.netExposure else 0
                    except Exception as e:
                        logging.error(f"Error getting Leverex positions: {e}", exc_info=True)
                
                # Get BitMEX positions
                if taker:
                    try:
                        bitmex_positions = taker.getPositions()
                        if bitmex_positions and hasattr(bitmex_positions, 'positions'):
                            product = taker.product
                            if product in bitmex_positions.positions:
                                for pos_id, pos in bitmex_positions.positions[product].items():
                                    pos_data = {
                                        'id': str(pos_id),
                                        'symbol': pos.symbol if hasattr(pos, 'symbol') else product,
                                        'volume': float(pos.amount) if hasattr(pos, 'amount') else 0,
                                        'side': 'LONG' if pos.amount > 0 else 'SHORT' if pos.amount < 0 else 'FLAT',
                                        'entry_price': float(pos.base_price) if hasattr(pos, 'base_price') else 0,
                                        'leverage': float(pos.leverage) if hasattr(pos, 'leverage') else 1,
                                        'liquidation_price': float(pos.liquidation_price) if hasattr(pos, 'liquidation_price') and pos.liquidation_price else None,
                                        'collateral': float(pos.collateral) if hasattr(pos, 'collateral') and pos.collateral else None,
                                        'pnl': float(pos.profit_loss) if hasattr(pos, 'profit_loss') and pos.profit_loss is not None else None
                                    }
                                    positions['bitmex'].append(pos_data)
                        
                        # Get net exposure and convert to XBT
                        # BitMEX netExposure is in contracts (USD), convert to XBT using index price
                        if hasattr(bitmex_positions, 'netExposure'):
                            net_exposure_contracts = float(bitmex_positions.netExposure) if bitmex_positions.netExposure else 0
                            # Convert contracts to XBT: contracts / index_price
                            # BitMEX uses inverse contracts where 1 contract = 1 USD of exposure
                            # To get XBT: exposure_in_USD / price_in_USD = XBT
                            index_price = taker.indexPrice if hasattr(taker, 'indexPrice') and taker.indexPrice else None
                            if index_price and index_price > 0:
                                # Convert USD exposure to XBT
                                net_exposure_xbt = net_exposure_contracts / float(index_price)
                                positions['net_exposure']['bitmex'] = net_exposure_xbt
                            else:
                                # Fallback: use contracts if no price available
                                positions['net_exposure']['bitmex'] = net_exposure_contracts
                    except Exception as e:
                        logging.error(f"Error getting BitMEX positions: {e}", exc_info=True)
                
                # Calculate total net exposure
                positions['net_exposure']['total'] = positions['net_exposure']['leverex'] + positions['net_exposure']['bitmex']
                
                return jsonify(positions)
            except Exception as e:
                logging.error(f"Error in positions endpoint: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/trade-history')
        def get_trade_history():
            try:
                maker = self.dealer.maker
                if not maker:
                    return jsonify({'trades': [], 'error': 'Leverex provider not available'})
                
                trades = []
                try:
                    # Get all trades from public feed (all users)
                    if hasattr(maker, 'all_trades') and maker.all_trades:
                        for trade in maker.all_trades:
                            # Determine side based on amount (positive = buy, negative = sell)
                            amount = trade.get('amount', 0)
                            side = 'BUY' if amount >= 0 else 'SELL'
                            
                            trade_data = {
                                'order_id': str(trade.get('id', '')),
                                'side': side,
                                'price': trade.get('price', 0),
                                'volume': abs(amount),
                                'timestamp': trade.get('timestamp', 0),
                                'session_id': '',
                                'is_taker': None,  # Not available in public feed
                                'pnl': None,  # Not available in public feed
                                'fee': None,  # Not available in public feed
                                'is_public': True,  # Mark as public trade
                            }
                            trades.append(trade_data)
                    
                    # Also include user's own trades from current session
                    if hasattr(maker, 'getSessionOrders'):
                        try:
                            orders = maker.getSessionOrders()
                            for order_id, order in orders.items():
                                if hasattr(order, 'is_trade_position') and order.is_trade_position():
                                    # Get side - check if it's a sell order
                                    side = 'SELL' if hasattr(order, 'is_sell') and order.is_sell() else 'BUY'
                                    
                                    # Get volume (quantity)
                                    volume = float(order.quantity) if hasattr(order, 'quantity') else 0
                                    if side == 'SELL':
                                        volume = -volume  # Negative for sells
                                    
                                    trade_data = {
                                        'order_id': str(order.id) if hasattr(order, 'id') else str(order_id),
                                        'side': side,
                                        'price': float(order.price) if hasattr(order, 'price') else 0,
                                        'volume': abs(volume),
                                        'timestamp': int(order.timestamp) if hasattr(order, 'timestamp') else 0,
                                        'session_id': str(order.session_id) if hasattr(order, 'session_id') else '',
                                        'is_taker': bool(order.is_taker) if hasattr(order, 'is_taker') else False,
                                        'pnl': float(order.trade_pnl) if hasattr(order, 'trade_pnl') and order.trade_pnl is not None else None,
                                        'fee': float(order.fee) if hasattr(order, 'fee') else None,
                                        'is_public': False,  # User's own trade
                                    }
                                    trades.append(trade_data)
                        except Exception as e:
                            logging.debug(f"Error getting user trades: {e}")
                    
                    # Sort by timestamp descending (most recent first)
                    trades.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
                    
                except Exception as e:
                    logging.error(f"Error getting trade history: {e}", exc_info=True)
                    return jsonify({'trades': [], 'error': str(e)})
                
                return jsonify({'trades': trades[:200]})  # Limit to last 200 trades
            except Exception as e:
                logging.error(f"Error in trade history endpoint: {e}")
                return jsonify({'trades': [], 'error': str(e)}), 500
    
    def start(self):
        """Start the web server in a separate thread"""
        def run_server():
            self.app.run(host='0.0.0.0', port=self.port, debug=False, use_reloader=False)
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        logging.info(f"Web interface started on http://localhost:{self.port}")
    
    def stop(self):
        """Stop the web server"""
        # Flask doesn't have a clean way to stop, but since it's a daemon thread,
        # it will stop when the main process exits
        pass

