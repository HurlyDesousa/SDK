# Leverex API Connection Check

## Quick Status Check

### Option 1: Check via Web Interface (Easiest)
1. Open your browser and go to: `http://localhost:5000`
2. Look at the "Authentication Status" section
3. Check the "Leverex Connection" status:
   - ✅ **Connected** = API is connected
   - ❌ **Disconnected** = API connection failed

### Option 2: Check via API Endpoint
Run this command in your terminal:
```bash
curl http://localhost:5000/api/status | python -m json.tool
```

Or if you have PowerShell:
```powershell
Invoke-RestMethod -Uri http://localhost:5000/api/status | ConvertTo-Json
```

### Option 3: Check Container Logs
```bash
docker logs leverex-dealer-staging --tail 100 | grep -i "leverex\|maker\|connection\|authorized\|error"
```

## What to Look For

### ✅ Good Signs:
- **Connection Status**: "Connected"
- **Ready Status**: "Ready" (may take a moment after connection)
- **Price Data**: Leverex price showing a number (not "--")
- **Status Details**: Shows "All systems ready" or similar positive message

### ❌ Problem Signs:
- **Connection Status**: "Disconnected"
- **Ready Status**: "Not Ready" (for extended period)
- **Price Data**: Shows "--" (no price data)
- **Error Messages**: Look for errors like:
  - "Invalid EC key"
  - "Failed authentication"
  - "Connection refused"
  - "Name or service not known" (DNS error)

## Configuration Check

Verify your `dealer_config.json` has correct Leverex settings:

```json
{
  "leverex": {
    "api_endpoint": "wss://api.leverex.io",
    "login_endpoint": "wss://login.leverex.io/ws/v1/websocket",
    "public_endpoint": "wss://api.leverex.io",
    "key_file_path": "key.pem",
    "product": "xbtusd_rf"
  }
}
```

## Common Issues

### 1. "Invalid EC key" Error
- **Cause**: The `key.pem` file doesn't match your Leverex account
- **Fix**: Generate a new key using the key generation scripts

### 2. "Connection refused" or DNS Error
- **Cause**: Network connectivity issue or wrong endpoint
- **Fix**: Verify endpoints are correct and network can reach Leverex servers

### 3. "Not Ready" Status
- **Cause**: Connection established but waiting for session to open
- **Fix**: This is normal - wait a few seconds for session to initialize

### 4. No Price Data
- **Cause**: Not subscribed to product data or session not open
- **Fix**: Check that product subscription is working in logs

## Test Scripts

### Run Connection Test (Inside Container)
```bash
docker exec leverex-dealer-staging python test_leverex_connection.py
```

### Check Web Interface Status
```bash
docker exec leverex-dealer-staging python check_leverex_status.py
```

## Connection Flow

The Leverex connection follows this flow:
1. **Setup Connection** → Creates `AuthApiConnection` object
2. **Connect to WebSocket** → Connects to `api_endpoint`
3. **Login** → Authenticates using `key.pem` via `login_endpoint`
4. **Authorize** → Receives access token
5. **Subscribe** → Subscribes to product data and sessions
6. **Ready** → Provider becomes ready when session is open and healthy

## Current Configuration

Based on your `dealer_config.json`:
- **API Endpoint**: `wss://api.leverex.io` (Production)
- **Login Endpoint**: `wss://login.leverex.io/ws/v1/websocket` (Production)
- **Product**: `xbtusd_rf`
- **Key File**: `key.pem`

## Next Steps

If connection is not working:
1. Check container logs for specific error messages
2. Verify `key.pem` file is mounted correctly in container
3. Test endpoints are reachable from container
4. Verify key.pem matches your Leverex account

