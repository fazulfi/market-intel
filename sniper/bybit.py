import os
from typing import Optional

import ccxt


def _log(msg: str) -> None:
    print(f"[sniper-bybit] {msg}", flush=True)


class SniperBybit:
    def __init__(self) -> None:
        api_key = os.getenv("BYBIT_API_KEY", "")
        secret = os.getenv("BYBIT_API_SECRET", "")
        testnet = os.getenv("BYBIT_TESTNET", "false").lower() == "true"

        if not api_key or not secret:
            _log("WARNING: API Key/Secret tidak ditemukan di environment")

        self.exchange = ccxt.bybit(
            {
                "apiKey": api_key,
                "secret": secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "swap",
                },
            }
        )

        if testnet:
            self.exchange.set_sandbox_mode(True)
            _log("Bybit sandbox/testnet mode aktif")

        self.markets_loaded = False
        self.markets_info: dict = {}
        self._leverage_cache: dict[str, int] = {}

    def load_markets(self) -> None:
        try:
            self.markets_info = self.exchange.load_markets()
            self.markets_loaded = True
            _log(f"Berhasil memuat metadata dari {len(self.markets_info)} market")
        except Exception as e:
            _log(f"Gagal load market: {e}")
            raise

    def ensure_market(self, symbol: str) -> dict:
        if not self.markets_loaded:
            self.load_markets()

        market = self.markets_info.get(symbol)
        if not market:
            raise ValueError(f"Market tidak ditemukan untuk symbol {symbol}")
        return market

    def get_market_min_amount(self, symbol: str) -> float:
        market = self.ensure_market(symbol)
        return float(market.get("limits", {}).get("amount", {}).get("min") or 0.0)

    def format_qty(self, symbol: str, qty: float) -> float:
        self.ensure_market(symbol)
        return float(self.exchange.amount_to_precision(symbol, qty))

    def get_current_price(self, symbol: str) -> float:
        ticker = self.exchange.fetch_ticker(symbol)
        last = ticker.get("last")
        if last is None or float(last) <= 0:
            raise ValueError(f"Harga live tidak valid untuk {symbol}: {ticker}")
        return float(last)

    def get_max_leverage(self, symbol: str) -> int:
        market = self.ensure_market(symbol)
        raw = market.get("limits", {}).get("leverage", {}).get("max") or 1
        try:
            lev = int(float(raw))
        except Exception:
            lev = 1
        return max(1, lev)

    def set_leverage(self, symbol: str, leverage: int) -> int:
        self.ensure_market(symbol)

        leverage = max(1, int(leverage))

        cached = self._leverage_cache.get(symbol)
        if cached == leverage:
            return leverage

        try:
            self.exchange.set_leverage(leverage, symbol)
            self._leverage_cache[symbol] = leverage
            _log(f"Leverage {symbol} diset ke {leverage}x")
            return leverage
        except Exception as e:
            _log(f"Gagal set leverage {symbol} ke {leverage}x: {e}")
            raise

    def resolve_entry_leverage(self, symbol: str) -> int:
        use_max_leverage = os.getenv("USE_MAX_LEVERAGE", "false").lower() == "true"
        target_leverage = int(os.getenv("TARGET_LEVERAGE", "1"))

        leverage = self.get_max_leverage(symbol) if use_max_leverage else max(1, target_leverage)
        return self.set_leverage(symbol, leverage)

    def calc_order_amount_from_margin(
        self,
        symbol: str,
        margin_usd: float,
        price: float,
        leverage: int,
        max_position_notional_usd: float = 0.0,
    ) -> float:
        market = self.ensure_market(symbol)

        if margin_usd <= 0:
            raise ValueError(f"margin_usd tidak valid: {margin_usd}")
        if price <= 0:
            raise ValueError(f"price tidak valid: {price}")

        leverage = max(1, int(leverage))
        notional_usd = margin_usd * leverage

        if max_position_notional_usd > 0:
            notional_usd = min(notional_usd, max_position_notional_usd)

        base_qty = notional_usd / price

        if market.get("contract"):
            contract_size = float(market.get("contractSize") or 1.0)
            if contract_size <= 0:
                raise ValueError(f"contractSize tidak valid untuk {symbol}: {contract_size}")
            return base_qty / contract_size

        return base_qty

    def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        reduce_only: bool = False,
    ) -> Optional[str]:
        formatted_qty = self.format_qty(symbol, qty)
        min_amount = self.get_market_min_amount(symbol)

        if formatted_qty <= 0:
            raise ValueError(f"DITOLAK: Kuantitas {formatted_qty} tidak valid setelah formatting")

        if min_amount > 0 and formatted_qty < min_amount:
            raise ValueError(
                f"DITOLAK: Kuantitas {formatted_qty} lebih kecil dari minimum lot bursa ({min_amount})"
            )

        _log(
            f"EXECUTING: MARKET {side.upper()} | {formatted_qty} {symbol} | Reduce: {reduce_only}"
        )

        params = {"reduceOnly": reduce_only}
        try:
            order = self.exchange.create_order(
                symbol=symbol,
                type="market",
                side=side.lower(),
                amount=formatted_qty,
                price=None,
                params=params,
            )
            order_id = order.get("id")
            _log(f"SUCCESS: Order {order_id} terkirim")
            return order_id
        except Exception as e:
            _log(f"GAGAL Eksekusi {symbol}: {e}")
            raise

    def get_position_size(self, symbol: str, side: str) -> float:
        target_side = str(side).upper()
        if target_side not in ("LONG", "SHORT"):
            raise ValueError(f"Side posisi tidak valid: {side}")

        normalized_side = "long" if target_side == "LONG" else "short"

        try:
            positions = self.exchange.fetch_positions([symbol])
        except Exception as e:
            _log(f"Gagal fetch position {symbol}: {e}")
            raise

        for p in positions:
            pos_symbol = str(p.get("symbol", ""))
            pos_side = str(p.get("side", "")).lower()
            pos_size = float(p.get("contracts", 0) or p.get("info", {}).get("size", 0) or 0)

            if pos_symbol == symbol and pos_side == normalized_side and pos_size > 0:
                return pos_size

        return 0.0
