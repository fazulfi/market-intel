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

    def get_market_limits(self, symbol: str) -> Tuple[float, float]:
        """Mengambil (min_amount, amount_step) dari aturan Bybit"""
        if not self.markets_loaded: self.load_markets()
        market = self.markets_info.get(symbol)
        if not market: return 0.0, 0.0
        
        min_amount = float(market.get('limits', {}).get('amount', {}).get('min', 0.0))
        step = float(market.get('precision', {}).get('amount', 0.0))
        return min_amount, step

    def format_qty(self, symbol: str, qty: float) -> float:
        """Memotong angka desimal sesuai presisi bursa"""
        if not self.markets_loaded: self.load_markets()
        if symbol not in self.markets_info: return qty
        return float(self.exchange.amount_to_precision(symbol, qty))

    def get_current_price(self, symbol: str) -> float:
        ticker = self.exchange.fetch_ticker(symbol)
        return float(ticker['last'])

    def place_market_order(self, symbol: str, side: str, qty: float, reduce_only: bool = False) -> Optional[str]:
        formatted_qty = self.format_qty(symbol, qty)
        min_amount, _ = self.get_market_limits(symbol)
        
        # 🛡️ THE MINIMUM LOT SHIELD
        if formatted_qty < min_amount:
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
        """Cek posisi aktif saat ini untuk keperluan Partial TP / Close"""
        try:
            # Normalisasi side ke bentuk standar ccxt
            target_side = "long" if side.upper() == "LONG" else "short"
            
            positions = self.exchange.fetch_positions([symbol])
            for p in positions:
                pos_side = str(p.get('side', '')).lower()
                # Tarik size dari berbagai kemungkinan response
                pos_size = float(p.get('contracts', 0) or p.get('info', {}).get('size', 0))
                
                if p['symbol'] == symbol and pos_side == target_side:
                    return pos_size
            return 0.0
        except Exception as e:
            _log(f"Gagal fetch position {symbol}: {e}")
            return 0.0
