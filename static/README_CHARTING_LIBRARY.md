# TradingView Advanced Charts Library Setup

This directory should contain the TradingView Advanced Charts library files.

## How to Obtain the Library

1. Visit https://www.tradingview.com/advanced-charts/
2. Complete the request form to get access
3. Download the library files
4. Extract and place the `charting_library` folder contents in this `static/` directory

## Directory Structure

After setup, your directory should look like:
```
static/
  charting_library/
    charting_library.min.js
    (other library files)
```

## Alternative: Using a CDN

If you have access to a CDN hosting the library, you can modify the script tag in `templates/dealer_interface.html` to point to the CDN URL instead.

## Note

The TradingView Advanced Charts library is a private library that requires approval from TradingView. The web interface will display a helpful message if the library is not found.

