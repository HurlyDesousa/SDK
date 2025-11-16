import logging
import threading
import json
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

class WebInterface:
    def __init__(self, dealer, port=5000):
        self.dealer = dealer
        self.port = port
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        CORS(self.app)
        self.server_thread = None
        self.dealer_running = True  # Track dealer running state
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
                
                # Taker (Bitfinex) uses different connection type
                taker_auth = "Connected"
                if taker and taker.connection:
                    # Bitfinex connection has ws attribute
                    if hasattr(taker.connection, 'ws') and taker.connection.ws:
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
                
                # Get price data separately for Leverex (maker) and Bitfinex (taker)
                leverex_price = None
                bitfinex_price = None
                
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
                
                # Get Bitfinex (taker) price - try indexPrice first, then order book
                try:
                    if taker and hasattr(taker, 'indexPrice'):
                        if taker.indexPrice is not None and taker.indexPrice != 0:
                            bitfinex_price = float(taker.indexPrice)
                            logging.debug(f"Got index price from Bitfinex: {bitfinex_price}")
                    
                    # Fallback: try to get mid price from Bitfinex order book
                    if bitfinex_price is None and taker and hasattr(taker, 'order_book') and taker.order_book:
                        try:
                            # Try to get best bid and ask from order book
                            bid_price = None
                            ask_price = None
                            if hasattr(taker.order_book, 'get_aggregated_bid_price'):
                                bid_obj = taker.order_book.get_aggregated_bid_price(0.001)  # Small volume
                                if bid_obj and hasattr(bid_obj, 'price'):
                                    bid_price = bid_obj.price
                                elif bid_obj:
                                    bid_price = float(bid_obj)
                            if hasattr(taker.order_book, 'get_aggregated_ask_price'):
                                ask_obj = taker.order_book.get_aggregated_ask_price(0.001)  # Small volume
                                if ask_obj and hasattr(ask_obj, 'price'):
                                    ask_price = ask_obj.price
                                elif ask_obj:
                                    ask_price = float(ask_obj)
                            if bid_price and ask_price:
                                bitfinex_price = (float(bid_price) + float(ask_price)) / 2.0
                                logging.debug(f"Got mid price from Bitfinex order book: {bitfinex_price}")
                        except (ValueError, TypeError, AttributeError) as e:
                            logging.debug(f"Error getting price from Bitfinex order book: {e}")
                except (ValueError, TypeError, AttributeError) as e:
                    logging.debug(f"Error getting Bitfinex price: {e}")
                
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
                
                # Get status strings
                maker_status = maker.getStatusStr() if maker else "N/A"
                taker_status = taker.getStatusStr() if taker else "N/A"
                dealer_status = self.dealer.getStatusStr() if hasattr(self.dealer, 'getStatusStr') else "N/A"
                
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
                        'bitfinex': bitfinex_price,
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
                    # Create stop flag file
                    import os
                    stop_flag_file = '/app/.dealer_stop'
                    try:
                        with open(stop_flag_file, 'w') as f:
                            f.write('stop')
                        logging.info("Stop flag file created")
                    except Exception as e:
                        logging.error(f"Error creating stop flag: {e}")
                    
                    # Try to stop the dealer gracefully
                    try:
                        if hasattr(self.dealer, 'stop'):
                            self.dealer.stop()
                        # Try to stop the event loop
                        import asyncio
                        try:
                            loop = asyncio.get_running_loop()
                            if loop:
                                loop.stop()
                        except RuntimeError:
                            # No running loop, that's okay
                            pass
                    except Exception as e:
                        logging.error(f"Error stopping dealer: {e}")
                    return jsonify({'status': 'stopped', 'message': 'Dealer stop requested. It will stop after current operations complete.'})
                
                elif action == 'start':
                    self.dealer_running = True
                    # Remove stop flag file
                    import os
                    stop_flag_file = '/app/.dealer_stop'
                    try:
                        if os.path.exists(stop_flag_file):
                            os.remove(stop_flag_file)
                            logging.info("Stop flag file removed")
                    except Exception as e:
                        logging.error(f"Error removing stop flag: {e}")
                    return jsonify({'status': 'started', 'message': 'Dealer start requested. Restart container to apply.'})
                
                else:
                    return jsonify({'error': 'Invalid action'}), 400
                    
            except Exception as e:
                logging.error(f"Error in control endpoint: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/control/status', methods=['GET'])
        def get_control_status():
            return jsonify({'running': self.dealer_running})
    
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

