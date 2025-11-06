# Simple Trading Bot (using Binance Futures Testnet)

A **Simplified Crypto Trading Bot** built in **Python** for **Binance Futures (USDT-M)** on the **Testnet environment**.  
It supports **Market**, **Limit**, and **Stop/Stop-Market** orders, complete with logging, error handling, and a command-line interface.

---

## Features

- **Market & Limit Orders**
- **BUY / SELL** support  
- **Stop-Limit** and **Stop-Market** (bonus)
- **Futures Testnet REST API** integration  
- **CLI-based user input & validation**
- **Full logging of requests/responses/errors**
- **Order querying and cancellation**
- **Error handling for invalid price/quantity inputs**

---

## Requirements

- Python 3.9 or higher  
- Binance Futures Testnet account (from [Binance Login](https://accounts.binance.com/en/login))
- Then create API Key & Secret (from [https://testnet.binancefuture.com](https://testnet.binancefuture.com))
- Store them in .env file:
```bash
BINANCE_API_KEY=
BINANCE_API_SECRET=
```
---

## Installation

1. **Clone the repository**

```bash
   git clone https://github.com/Euphoric-Coder/Simple-Trading-Bot--using-Binance-Futures-Testnet-.git
```
2. **Change Directory**

```bash
   cd Simple-Trading-Bot--using-Binance-Futures-Testnet-
```
3. **Create Python Virtual Environment**

```bash
python -m venv VENV
```

4. **Activate the Virtual Environment**
```bash
source VENV/bin/activate 
```
```bash
VENV\Scripts\activate
```

5. **Install Required Dependencies**

```bash
pip install requests python-dotenv
```

## Command Line Interface (CLI)

The bot uses a command-line interface for all interactions.  
You can view available commands using:

```bash
python bot.py --help
```

## Basic Commands

---

### 1. Check Server Connection
```bash
python bot.py ping
```
**Example Output:**
```bash
{
  "status": "ok",
  "serverTime": 1730972702143
}
```

### 2. View Tradable Symbols
```bash
python bot.py symbols
```

Displays all available Futures symbols and their trading status.

---

### 3. Place Orders

| **Order Type** | **Required Params** | **Example Command** |
|----------------|---------------------|----------------------|
| **Market** | `--symbol`, `--side`, `--type`, `--quantity` | `python bot.py order --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001` |
| **Limit** | `--symbol`, `--side`, `--type`, `--quantity`, `--price`, `--timeInForce` | `python bot.py order --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.001 --price 85000 --timeInForce GTC` |
| **Stop-Limit** | `--symbol`, `--side`, `--type STOP`, `--quantity`, `--price`, `--stopPrice`, `--timeInForce` | `python bot.py order --symbol BTCUSDT --side SELL --type STOP --quantity 0.001 --price 84000 --stopPrice 84500 --timeInForce GTC` |
| **Stop-Market** | `--symbol`, `--side`, `--type STOP_MARKET`, `--quantity`, `--stopPrice` | `python bot.py order --symbol BTCUSDT --side SELL --type STOP_MARKET --quantity 0.001 --stopPrice 84500` |

---

**Example Output (Market Order):**
```json
{
  "status": "submitted",
  "order": {
    "symbol": "BTCUSDT",
    "orderId": 123456789,
    "side": "BUY",
    "type": "MARKET",
    "status": "FILLED",
    "executedQty": "0.001",
    "avgPrice": "85200.00"
  }
}
```

### 4. Query Order Status
```bash
python bot.py status --symbol BTCUSDT --orderId 123456789
```

### 5. Cancel an Order
```bash
python bot.py cancel --symbol BTCUSDT --orderId 123456789
```

## Logging & Debugging

All logs (requests, responses, and errors) are stored in:
`logs/bot.log`

#### To monitor live logs (run in another terminal):
```bash
tail -f logs/bot.log
```

**Example log entries:**
```log
2025-11-07 14:12:35 | INFO | POST https://testnet.binancefuture.com/fapi/v1/order | params={'symbol': 'BTCUSDT', 'side': 'BUY', 'type': 'MARKET', ...}
2025-11-07 14:12:35 | INFO | API response OK: {"symbol":"BTCUSDT","orderId":123456789,...}
```

---

## Example Workflow

1. **Check connection**
```bash
python bot.py ping
```

2. **List symbols**
```bash
python bot.py symbols
```

3. **Place a market order**
```bash
python bot.py order --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
```

4. **Query its Status**
```bash
python bot.py status --symbol BTCUSDT --orderId 123456789
```

5. **Cancel (if pending)**
```bash
python bot.py cancel --symbol BTCUSDT --orderId 123456789
```



