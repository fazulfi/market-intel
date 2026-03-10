import ccxt
from app.config import BYBIT_API_KEY, BYBIT_API_SECRET, DRY_RUN
from app.utils.logging import log, log_error

class BybitExecutor:
    def __init__(self):
        # Inisialisasi API Bybit via CCXT
        self.exchange = ccxt.bybit({
            'apiKey': BYBIT_API_KEY,
            'secret': BYBIT_API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'} # Linear Perpetual
        })
        self.markets_loaded = False
        self.markets_info = {}

    def load_markets(self):
        """Menyedot aturan Tick Size dan Lot Size dari Bybit"""
        try:
            log("Loading Bybit market data (precision, lot sizes)...")
            self.markets_info = self.exchange.load_markets()
            self.markets_loaded = True
            log(f"Successfully loaded {len(self.markets_info)} markets from Bybit.")
        except Exception as e:
            log_error("Failed to load Bybit markets", e)

    def format_qty(self, symbol: str, qty: float) -> float:
        """Membulatkan Lot Size (Kuantitas Koin) agar tidak ditolak Bybit"""
        if not self.markets_loaded: self.load_markets()
        market = self.markets_info.get(symbol)
        if not market: return qty
        return float(self.exchange.amount_to_precision(symbol, qty))

    def format_price(self, symbol: str, price: float) -> float:
        """Membulatkan Tick Size (Harga) agar tidak ditolak Bybit"""
        if not self.markets_loaded: self.load_markets()
        market = self.markets_info.get(symbol)
        if not market: return price
        return float(self.exchange.price_to_precision(symbol, price))

    def place_order(self, symbol: str, side: str, order_type: str, qty: float, price: float = None, reduce_only: bool = False):
        """Fungsi utama untuk menembak order ke Exchange"""
        formatted_qty = self.format_qty(symbol, qty)
        formatted_price = self.format_price(symbol, price) if price else None

        # Log format eksekusi
        mode_str = "DRY_RUN" if DRY_RUN else "LIVE_API"
        px_str = formatted_price if formatted_price else "MARKET"
        log(f"[{mode_str}] Executing: {order_type} {side} {formatted_qty} {symbol} @ {px_str} (ReduceOnly: {reduce_only})")

        # 🛡️ THE DRY RUN SHIELD 🛡️
        if DRY_RUN:
            log(f"🛡️ DRY_RUN ACTIVE: Actual API call skipped for {symbol}.")
            return {"id": f"dry_dummy_{int(qty*1000)}", "status": "simulated"}

        # 🔥 LIVE EXECUTION 🔥
        try:
            params = {'reduceOnly': reduce_only}
            order = self.exchange.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=formatted_qty,
                price=formatted_price,
                params=params
            )
            log(f"✅ Order Success: {order.get('id')} - {symbol}")
            return order
        except Exception as e:
            log_error(f"❌ Order Failed: {symbol}", e)
            return None
