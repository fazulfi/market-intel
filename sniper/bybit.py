import os
import ccxt
from typing import Optional, Tuple

def _log(msg: str) -> None:
    print(f"[sniper-bybit] {msg}", flush=True)

class SniperBybit:
    def __init__(self):
        api_key = os.getenv("BYBIT_API_KEY", "")
        secret = os.getenv("BYBIT_API_SECRET", "")
        
        if not api_key or not secret:
            _log("WARNING: API Key/Secret tidak ditemukan di environment!")

        self.exchange = ccxt.bybit({
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'} # Linear Perpetual (USDT)
        })
        self.markets_loaded = False
        self.markets_info = {}

    def load_markets(self):
        try:
            self.markets_info = self.exchange.load_markets()
            self.markets_loaded = True
            _log(f"Berhasil memuat metadata dari {len(self.markets_info)} market.")
        except Exception as e:
            _log(f"Gagal load market: {e}")

    def get_market_min_amount(self, symbol: str) -> float:
        """Mengambil batas minimum lot dari bursa dengan lebih akurat."""
        if not self.markets_loaded:
            self.load_markets()
        market = self.markets_info.get(symbol)
        if not market:
            return 0.0
        return float(market.get('limits', {}).get('amount', {}).get('min', 0.0))

    def set_max_leverage(self, symbol: str) -> int:
        """Mencari leverage maksimal yang diizinkan bursa dan mengesetnya."""
        if not self.markets_loaded:
            self.load_markets()
        market = self.markets_info.get(symbol)
        
        max_lev = 1
        if market:
            max_lev = int(market.get('limits', {}).get('leverage', {}).get('max', 1))
        
        try:
            # Mengatur leverage ke Bybit secara eksplisit
            self.exchange.set_leverage(max_lev, symbol)
            _log(f"Leverage {symbol} diset ke maksimal: {max_lev}x")
            return max_lev
        except Exception as e:
            # Pengecualian biasanya terjadi jika leverage sudah di angka tersebut
            _log(f"Info set leverage {symbol}: {e}")
            return max_lev

    def format_qty(self, symbol: str, qty: float) -> float:
        """Memotong angka desimal sesuai presisi bursa"""
        if not self.markets_loaded:
            self.load_markets()
        if symbol not in self.markets_info:
            return qty
        return float(self.exchange.amount_to_precision(symbol, qty))

    def get_current_price(self, symbol: str) -> float:
        """Mengambil harga 'last' secara aman dengan validasi."""
        ticker = self.exchange.fetch_ticker(symbol)
        last = ticker.get("last")
        if last is None or float(last) <= 0:
            raise ValueError(f"Harga live tidak valid untuk {symbol}: {ticker}")
        return float(last)

    def place_market_order(self, symbol: str, side: str, qty: float, reduce_only: bool = False) -> Optional[str]:
        formatted_qty = self.format_qty(symbol, qty)
        min_amount = self.get_market_min_amount(symbol)
        
        # 🛡️ THE MINIMUM LOT SHIELD & VALIDATION
        if formatted_qty <= 0:
            raise ValueError(f"DITOLAK: Kuantitas {formatted_qty} tidak valid setelah formatting")

        if min_amount > 0 and formatted_qty < min_amount:
            raise ValueError(f"DITOLAK: Kuantitas {formatted_qty} lebih kecil dari minimum lot bursa ({min_amount})")

        _log(f"EXECUTING: MARKET {side.upper()} | {formatted_qty} {symbol} | Reduce: {reduce_only}")
        
        try:
            params = {'reduceOnly': reduce_only}
            order = self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side.lower(),
                amount=formatted_qty,
                price=None,
                params=params
            )
            order_id = order.get('id')
            _log(f"✅ SUCCESS: Order {order_id} terkirim!")
            return order_id
        except Exception as e:
            _log(f"❌ GAGAL Eksekusi {symbol}: {e}")
            raise e

    def get_position_size(self, symbol: str, side: str) -> float:
        """Cek posisi aktif saat ini secara defensif."""
        try:
            target_side = "long" if side.upper() == "LONG" else "short"
            positions = self.exchange.fetch_positions([symbol])
            
            for p in positions:
                pos_symbol = str(p.get("symbol", ""))
                pos_side = str(p.get("side", "")).lower()
                pos_size = float(p.get("contracts", 0) or p.get("info", {}).get("size", 0))
                
                # 🛡️ Validasi ekstra defensif
                if pos_symbol == symbol and pos_side == target_side and pos_size > 0:
                    return pos_size
            return 0.0
        except Exception as e:
            _log(f"Gagal fetch position {symbol}: {e}")
            return 0.0
