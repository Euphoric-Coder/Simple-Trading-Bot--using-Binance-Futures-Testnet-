# Deliverables:
# - Market & Limit orders (BUY/SELL)
# - Bonus: STOP (stop-limit) and STOP_MARKET
# - Input validation against exchange filters (tick size, lot size, min/max, price step)
# - CLI with argparse
# - Structured logging (requests, responses, errors) -> logs/bot.log
# - Clear I/O: prints JSON results of order placement/status/cancel
#
# Testnet Base URL used (as per instructions): https://testnet.binancefuture.com

import os
import hmac
import time
import json
import math
import argparse
import hashlib
import logging
import pathlib
import requests
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode
from dotenv import load_dotenv

TESTNET_BASE_URL = "https://testnet.binancefuture.com"
FAPI_PREFIX = "/fapi/v1"

# Logging Configuration
LOG_DIR = pathlib.Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("basicbot")

# API Configuration & Error Classes
@dataclass
class APIConfig:
    api_key: str
    api_secret: str
    base_url: str = TESTNET_BASE_URL
    recv_window: int = 5000  # ms


class APIError(Exception):
    """Raised when Binance API returns an error."""

    def __init__(self, code: int, msg: str, payload: Optional[dict] = None):
        super().__init__(f"APIError {code}: {msg}")
        self.code = code
        self.msg = msg
        self.payload = payload or {}

# HTTP Client (Handles Signing and Requests)
class HTTPClient:
    def __init__(self, config: APIConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.config.api_key})

    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = urlencode(params, doseq=True)
        signature = hmac.new(
            self.config.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    def _handle_response(self, resp: requests.Response) -> dict:
        text = resp.text
        try:
            data = resp.json()
        except Exception:
            logger.error("Non-JSON response: %s", text)
            resp.raise_for_status()
            return {}

        if (
            resp.status_code >= 400
            or isinstance(data, dict)
            and data.get("code", 0) != 0
            and "msg" in data
        ):
            # Note: Futures error payload often like {"code": -2019, "msg": "..."}
            code = data.get("code", resp.status_code)
            msg = data.get("msg", "HTTP error")
            logger.error(
                "API error | status=%s | code=%s | msg=%s | body=%s",
                resp.status_code,
                code,
                msg,
                text,
            )
            raise APIError(code, msg, data)

        logger.info("API response OK: %s", text)
        return data

    def get(
        self, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False
    ) -> dict:
        url = self.config.base_url + path
        params = params or {}
        if signed:
            params.update(
                {
                    "timestamp": int(time.time() * 1000),
                    "recvWindow": self.config.recv_window,
                }
            )
            params = self._sign(params)

        logger.info("GET %s | params=%s", url, params)
        resp = self.session.get(url, params=params, timeout=20)
        return self._handle_response(resp)

    def post(
        self, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False
    ) -> dict:
        url = self.config.base_url + path
        params = params or {}
        if signed:
            params.update(
                {
                    "timestamp": int(time.time() * 1000),
                    "recvWindow": self.config.recv_window,
                }
            )
            params = self._sign(params)

        logger.info("POST %s | params=%s", url, params)
        resp = self.session.post(url, params=params, timeout=20)
        return self._handle_response(resp)

    def delete(
        self, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False
    ) -> dict:
        url = self.config.base_url + path
        params = params or {}
        if signed:
            params.update(
                {
                    "timestamp": int(time.time() * 1000),
                    "recvWindow": self.config.recv_window,
                }
            )
            params = self._sign(params)

        logger.info("DELETE %s | params=%s", url, params)
        resp = self.session.delete(url, params=params, timeout=20)
        return self._handle_response(resp)


# Exchange Filters (Tick size, Lot size, etc.)
@dataclass
class SymbolFilters:
    price_tick: float
    qty_step: float
    min_qty: float
    max_qty: float
    min_price: float
    max_price: float

    def round_price(self, price: float) -> float:
        return math.floor(price / self.price_tick) * self.price_tick

    def round_qty(self, qty: float) -> float:
        # floor to step
        steps = math.floor(qty / self.qty_step)
        return steps * self.qty_step

    def validate_price(self, price: float) -> float:
        if price < self.min_price or price > self.max_price:
            raise ValueError(
                f"Price {price} out of bounds [{self.min_price}, {self.max_price}]"
            )
        p = self.round_price(price)
        if abs(p - price) > 1e-12:
            logger.warning("Adjusted price from %s to tick-aligned %s", price, p)
        return p

    def validate_qty(self, qty: float) -> float:
        if qty < self.min_qty or qty > self.max_qty:
            raise ValueError(
                f"Quantity {qty} out of bounds [{self.min_qty}, {self.max_qty}]"
            )
        q = self.round_qty(qty)
        if q <= 0:
            raise ValueError("Quantity rounds to zero; increase value.")
        if abs(q - qty) > 1e-12:
            logger.warning("Adjusted quantity from %s to step-aligned %s", qty, q)
        return q

# Exchange Info
class ExchangeInfoCache:
    """Fetch exchange Info to validate symbol filters."""

    def __init__(self, http: HTTPClient):
        self.http = http
        self._cache: Dict[str, SymbolFilters] = {}

    def get_filters(self, symbol: str) -> SymbolFilters:
        s = symbol.upper()
        if s in self._cache:
            return self._cache[s]

        data = self.http.get(f"{FAPI_PREFIX}/exchangeInfo")
        symbols = {item["symbol"]: item for item in data.get("symbols", [])}
        if s not in symbols:
            raise ValueError(f"Unknown symbol: {s}")

        info = symbols[s]
        if info.get("status") != "TRADING":
            logger.warning("Symbol %s status is %s", s, info.get("status"))

        price_filter = next(
            f for f in info["filters"] if f["filterType"] == "PRICE_FILTER"
        )
        lot_filter = next(f for f in info["filters"] if f["filterType"] == "LOT_SIZE")

        filters = SymbolFilters(
            price_tick=float(price_filter["tickSize"]),
            qty_step=float(lot_filter["stepSize"]),
            min_qty=float(lot_filter["minQty"]),
            max_qty=float(lot_filter["maxQty"]),
            min_price=float(price_filter["minPrice"]),
            max_price=float(price_filter["maxPrice"]),
        )
        self._cache[s] = filters
        return filters

# Simplified Trading Bot
class BasicBot:
    """
    Uses REST directly for maximum compatibility.

    Place orders: MARKET, LIMIT, STOP (stop-limit), STOP_MARKET
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        base = TESTNET_BASE_URL if testnet else "https://fapi.binance.com"
        self.config = APIConfig(api_key=api_key, api_secret=api_secret, base_url=base)
        self.http = HTTPClient(self.config)
        self.ex_info = ExchangeInfoCache(self.http)

    # Utilities
    def server_time(self) -> dict:
        return self.http.get(f"{FAPI_PREFIX}/time")

    def exchange_symbols(self) -> Dict[str, Any]:
        return self.http.get(f"{FAPI_PREFIX}/exchangeInfo")

    # Orders
    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        time_in_force: Optional[str] = None,
        stop_price: Optional[float] = None,
        reduce_only: Optional[bool] = None,
        new_client_order_id: Optional[str] = None,
    ) -> dict:
        """
        Supported order_type: MARKET, LIMIT, STOP (stop-limit), STOP_MARKET
        For LIMIT/STOP: price required; for STOP/STOP_MARKET: stop_price required.
        """

        symbol = symbol.upper()
        side = side.upper()
        order_type = order_type.upper()

        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")

        allowed_types = {"MARKET", "LIMIT", "STOP", "STOP_MARKET"}
        if order_type not in allowed_types:
            raise ValueError(f"order_type must be one of {allowed_types}")

        filters = self.ex_info.get_filters(symbol)
        qty = filters.validate_qty(float(quantity))

        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": f"{qty:.10f}".rstrip("0").rstrip("."),
        }

        # LIMIT needs price + TIF
        if order_type == "LIMIT":
            if price is None:
                raise ValueError("Limit order requires --price")
            if time_in_force is None:
                raise ValueError("Limit order requires --timeInForce (e.g., GTC)")
            px = filters.validate_price(float(price))
            params.update(
                {"price": self._fmt(px), "timeInForce": time_in_force.upper()}
            )

        # STOP (stop-limit) needs price + stopPrice + TIF
        if order_type == "STOP":
            if price is None or stop_price is None:
                raise ValueError("STOP requires --price and --stopPrice")
            if time_in_force is None:
                raise ValueError("STOP requires --timeInForce (e.g., GTC)")
            px = filters.validate_price(float(price))
            sp = filters.validate_price(float(stop_price))
            params.update(
                {
                    "price": self._fmt(px),
                    "stopPrice": self._fmt(sp),
                    "timeInForce": time_in_force.upper(),
                    "workingType": "CONTRACT_PRICE",  # or MARK_PRICE
                }
            )

        # STOP_MARKET needs stopPrice
        if order_type == "STOP_MARKET":
            if stop_price is None:
                raise ValueError("STOP_MARKET requires --stopPrice")
            sp = filters.validate_price(float(stop_price))
            params.update({"stopPrice": self._fmt(sp), "workingType": "CONTRACT_PRICE"})

        if reduce_only is not None:
            params["reduceOnly"] = "true" if reduce_only else "false"
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id

        # Futures create order endpoint
        result = self.http.post(f"{FAPI_PREFIX}/order", params=params, signed=True)
        return result

    def query_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None,
    ) -> dict:
        if not order_id and not client_order_id:
            raise ValueError("Provide either --orderId or --origClientOrderId")
        params = {"symbol": symbol.upper()}
        if order_id:
            params["orderId"] = int(order_id)
        if client_order_id:
            params["origClientOrderId"] = client_order_id
        return self.http.get(f"{FAPI_PREFIX}/order", params=params, signed=True)

    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None,
    ) -> dict:
        if not order_id and not client_order_id:
            raise ValueError("Provide either --orderId or --origClientOrderId")
        params = {"symbol": symbol.upper()}
        if order_id:
            params["orderId"] = int(order_id)
        if client_order_id:
            params["origClientOrderId"] = client_order_id
        return self.http.delete(f"{FAPI_PREFIX}/order", params=params, signed=True)

    # Helpers
    @staticmethod
    def _fmt(x: float) -> str:
        # Trim trailing zeros for Binance-friendly formatting
        s = f"{x:.10f}"
        return s.rstrip("0").rstrip(".") if "." in s else s


# CLI
def pretty_print(obj: Any):
    print(json.dumps(obj, indent=2, sort_keys=True))


def load_keys(args) -> Tuple[str, str]:
    # Priority: CLI args > .env > env vars set in OS
    load_dotenv(override=False)
    api_key = args.api_key or os.getenv("BINANCE_API_KEY", "")
    api_secret = args.api_secret or os.getenv("BINANCE_API_SECRET", "")
    if not api_key or not api_secret:
        raise SystemExit(
            "Missing API credentials. Provide via --api-key/--api-secret or .env BINANCE_API_KEY/BINANCE_API_SECRET."
        )
    return api_key, api_secret


def cli():
    parser = argparse.ArgumentParser(
        description="Simplified Binance USDT-M Futures Testnet Trading Bot (REST)."
    )
    parser.add_argument(
        "--api-key", help="API key (or set BINANCE_API_KEY in .env)", default=None
    )
    parser.add_argument(
        "--api-secret",
        help="API secret (or set BINANCE_API_SECRET in .env)",
        default=None,
    )
    parser.add_argument(
        "--live", action="store_true", help="Use live mainnet (default: testnet)"
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    # ping/server time
    sub.add_parser("ping", help="Check connectivity (server time).")

    # list symbols
    sub.add_parser("symbols", help="List exchange symbols and status.")

    # place order
    p_order = sub.add_parser("order", help="Place an order.")
    p_order.add_argument("--symbol", required=True, help="e.g., BTCUSDT")
    p_order.add_argument("--side", required=True, choices=["BUY", "SELL"])
    p_order.add_argument(
        "--type", required=True, choices=["MARKET", "LIMIT", "STOP", "STOP_MARKET"]
    )
    p_order.add_argument(
        "--quantity", required=True, type=float, help="Order qty (contracts)"
    )
    p_order.add_argument("--price", type=float, help="Required for LIMIT and STOP")
    p_order.add_argument(
        "--stopPrice", type=float, help="Required for STOP and STOP_MARKET"
    )
    p_order.add_argument(
        "--timeInForce", help="GTC/IOC/FOK; required for LIMIT and STOP"
    )
    p_order.add_argument(
        "--reduceOnly", action="store_true", help="Set reduceOnly=true"
    )
    p_order.add_argument("--clientId", help="Custom client order id")

    # status
    p_status = sub.add_parser("status", help="Query order status.")
    p_status.add_argument("--symbol", required=True)
    p_status.add_argument("--orderId", type=int)
    p_status.add_argument("--origClientOrderId")

    # cancel
    p_cancel = sub.add_parser("cancel", help="Cancel an order.")
    p_cancel.add_argument("--symbol", required=True)
    p_cancel.add_argument("--orderId", type=int)
    p_cancel.add_argument("--origClientOrderId")

    args = parser.parse_args()

    api_key, api_secret = load_keys(args)
    bot = BasicBot(api_key, api_secret, testnet=not args.live)

    try:
        if args.cmd == "ping":
            res = bot.server_time()
            pretty_print({"status": "ok", "serverTime": res.get("serverTime")})

        elif args.cmd == "symbols":
            res = bot.exchange_symbols()
            # show tradable perpetual symbols only (for brevity)
            symbols = [
                {
                    "symbol": s["symbol"],
                    "pair": s.get("pair"),
                    "status": s.get("status"),
                    "contractType": s.get("contractType"),
                    "marginAsset": s.get("marginAsset"),
                }
                for s in res.get("symbols", [])
            ]
            pretty_print({"count": len(symbols), "symbols": symbols})

        elif args.cmd == "order":
            res = bot.place_order(
                symbol=args.symbol,
                side=args.side,
                order_type=args.type,
                quantity=args.quantity,
                price=args.price,
                time_in_force=args.timeInForce,
                stop_price=args.stopPrice,
                reduce_only=args.reduceOnly,
                new_client_order_id=args.clientId,
            )
            pretty_print({"status": "submitted", "order": res})

        elif args.cmd == "status":
            res = bot.query_order(
                symbol=args.symbol,
                order_id=args.orderId,
                client_order_id=args.origClientOrderId,
            )
            pretty_print({"status": "fetched", "order": res})

        elif args.cmd == "cancel":
            res = bot.cancel_order(
                symbol=args.symbol,
                order_id=args.orderId,
                client_order_id=args.origClientOrderId,
            )
            pretty_print({"status": "canceled", "result": res})

    except APIError as e:
        pretty_print(
            {"status": "error", "code": e.code, "msg": e.msg, "payload": e.payload}
        )
    except requests.RequestException as e:
        logger.exception("HTTP error")
        pretty_print({"status": "error", "msg": f"HTTP error: {e}"})
    except Exception as e:
        logger.exception("Unexpected error")
        pretty_print({"status": "error", "msg": str(e)})


if __name__ == "__main__":
    cli()
