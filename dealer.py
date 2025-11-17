import logging
import asyncio
import json
import argparse
import time

from Providers.Leverex import LeverexProvider
from Providers.BitMEX import BitMEXProvider
from Factories.Dealer.Factory import DealerFactory
from Hedger.SimpleHedger import SimpleHedger
from StatusReporter.LocalReporter import LocalReporter
from StatusReporter.WebReporter import WebReporter
from WebInterface import WebInterface

#import pdb; pdb.set_trace()

################################################################################
if __name__ == '__main__':
   LOG_FORMAT = (
      "[%(asctime)s,%(msecs)d] [%(levelname)-8s] [%(filename)s:%(lineno)d] %(message)s"
   )
   logging.basicConfig(filename="dealer_debug.log", level=logging.INFO, format=LOG_FORMAT)
   root_logger = logging.getLogger()

   stream_logger = logging.StreamHandler()
   stream_logger.setFormatter(logging.Formatter(LOG_FORMAT))
   stream_logger.setLevel(logging.WARN)
   root_logger.addHandler(stream_logger)

   logging.warning("--------------------------------------")
   logging.warning("---- starting new dealer instance ----")
   logging.warning("--------------------------------------")

   parser = argparse.ArgumentParser(description='Leverex Dealer - hedging on BitMEX') 

   parser.add_argument('--config', type=str, help='Config file to use')
   parser.add_argument('--local', default=False, action='store_true',
      help='Do not push to remote status reporter')
   parser.add_argument('--web-port', type=int, default=5000,
      help='Port for web interface (default: 5000)')
   parser.add_argument('--no-web', default=False, action='store_true',
      help='Disable web interface')

   args = parser.parse_args()

   config = {}
   with open(args.config) as json_config_file:
      config = json.load(json_config_file)

   # Check for stop flag file
   import os
   stop_flag_file = '/app/.dealer_stop'
   
   # Create stop flag by default ONLY on first run (check for a marker file)
   # This ensures the dealer doesn't start automatically on first container start
   # But respects the state if the container restarts
   first_run_marker = '/app/.first_run'
   if not os.path.exists(first_run_marker):
      # First time running - create stop flag and marker
      with open(stop_flag_file, 'w') as f:
         f.write('stop')
      with open(first_run_marker, 'w') as f:
         f.write('done')
      logging.warning("Dealer starting in STOPPED state by default (first run)")
   # On subsequent runs, respect the existing stop flag state

   # Start web interface early so it's always accessible
   web_interface = None
   if not args.no_web:
      try:
         # Create a minimal dealer object for the web interface
         # We'll update it when the actual dealer starts
         from Factories.Dealer.Factory import DealerFactory
         from Providers.Leverex import LeverexProvider
         from Providers.BitMEX import BitMEXProvider
         from Hedger.SimpleHedger import SimpleHedger
         from StatusReporter.LocalReporter import LocalReporter
         
         # Create placeholder providers for web interface
         try:
            maker_placeholder = LeverexProvider(config)
            taker_placeholder = BitMEXProvider(config)
            hedger_placeholder = SimpleHedger(config)
            reporters_placeholder = [LocalReporter(config)]
            dealer_placeholder = DealerFactory(maker_placeholder, taker_placeholder, hedger_placeholder, reporters_placeholder)
         except:
            # If we can't create providers, create a minimal dealer
            dealer_placeholder = None
         
         web_interface = WebInterface(dealer_placeholder, port=args.web_port)
         web_interface.start()
         logging.info(f"Web interface available at http://localhost:{args.web_port}")
      except Exception as e:
         logging.warning(f"Failed to start web interface: {e}")

   while True:
      # Check if dealer should be stopped
      if os.path.exists(stop_flag_file):
         logging.warning("Dealer is in STOPPED state. Waiting for start signal...")
         # Wait and check periodically if stop flag is removed
         while os.path.exists(stop_flag_file):
            time.sleep(2)  # Check every 2 seconds
         logging.warning("Stop flag removed. Starting dealer...")
         continue  # Restart the loop to initialize dealer
      
      try:
         maker = LeverexProvider(config)
         taker = BitMEXProvider(config)
         hedger = SimpleHedger(config)
         reporters = [LocalReporter(config)]
         if args.local == False:
            reporters.append(WebReporter(config))

         dealer = DealerFactory(maker, taker, hedger, reporters)
         
         # Update web interface with actual dealer instance
         if web_interface:
            web_interface.dealer = dealer
            logging.info("Web interface updated with dealer instance")
         
         # Run dealer with stop flag monitoring
         async def run_with_stop_check():
            dealer_task = asyncio.create_task(dealer.run())
            # Monitor stop flag while dealer is running
            while not dealer_task.done():
               if os.path.exists(stop_flag_file):
                  logging.warning("Stop flag detected during dealer execution. Stopping dealer...")
                  # Cancel dealer task
                  dealer_task.cancel()
                  try:
                     await dealer_task
                  except asyncio.CancelledError:
                     pass
                  # Stop all tasks
                  for task in asyncio.all_tasks():
                     if task != asyncio.current_task():
                        task.cancel()
                  break
               await asyncio.sleep(1)  # Check every second
            if not dealer_task.done():
               await dealer_task
         
         asyncio.run(run_with_stop_check())

      except Exception as e:
         logging.error(f"!! Main loop broke with error: {str(e)} !!")
         logging.warning("!! Restarting in 10 seconds !!")
         time.sleep(10)
