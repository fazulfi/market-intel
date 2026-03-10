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

        # 🚀 MAPPING LONG/SHORT TO BUY/SELL
        ccxt_side = "buy" if side.upper() == "LONG" else "sell"
        # Kalau ini order Take Profit / Stop Loss (reduce_only), arahnya dibalik!
        if reduce_only: ccxt_side = "sell" if side.upper() == "LONG" else "buy"

        # Log format eksekusi
        mode_str = "DRY_RUN" if DRY_RUN else "LIVE_API"
        px_str = formatted_price if formatted_price else "MARKET"
        log(f"[{mode_str}] Executing: {order_type} {ccxt_side.upper()} (Trade: {side}) {formatted_qty} {symbol} @ {px_str} (Reduce: {reduce_only})")

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
                side=ccxt_side,
                amount=formatted_qty,
                price=formatted_price,
                params=params
            )
            log(f"✅ Order Success: {order.get('id')} - {symbol}")
            return order
        except Exception as e:
            log_error(f"❌ Order Failed: {symbol}", e)
            return None

    def fetch_open_positions(self, symbols: list) -> dict:
        """Tahap 3: Recon Engine - Menyedot posisi aktif di Bybit"""
        if DRY_RUN:
            return None  # Bypass Recon saat mode Dry Run / Simulasi
            
        try:
            if not symbols: return {}
            positions = self.exchange.fetch_positions(symbols)
            pos_map = {}
            for p in positions:
                sym = p.get('symbol')
                # CCXT menyimpan ukuran kontrak di 'contracts' atau 'positionAmt'
                size = float(p.get('contracts', 0) or p.get('positionAmt', 0) or 0)
                side = p.get('side', '').upper()
                
                # Hanya simpan posisi yang ukurannya lebih dari 0
                if size > 0:
                    pos_map[f"{sym}_{side}"] = size
            return pos_map
        except Exception as e:
            log_error("Recon Fetch Positions Error", e)
            return None

    def get_available_balance(self, coin: str = "USDT") -> float:
        """Menyedot saldo riil dari dompet Bybit-mu"""
        if DRY_RUN:
            return 1000.0  # Berpura-pura punya modal $1000 USDT saat simulasi!
        try:
            bal = self.exchange.fetch_balance()
            # Ambil saldo 'free' (yang belum terpakai untuk posisi lain)
            free_bal = float(bal.get(coin, {}).get('free', 0.0))
            return free_bal
        except Exception as e:
            log_error("Fetch Balance Error", e)
            return 0.0

    def calculate_qty_from_balance(self, symbol: str, entry_price: float, size_pct: float, coin: str = "USDT") -> float:
        """The True Translator: Mengubah % Saldo menjadi Quantity Koin eksak"""
        if entry_price <= 0: return 0.0
        
        balance = self.get_available_balance(coin)
        if balance <= 1.0: # Saldo terlalu tipis
            log(f"⚠️ Insufficient balance to calculate QTY for {symbol}")
            return 0.0
            
        # Hitung Notional Value (Berapa Dolar yang mau dipertaruhkan)
        # Asumsi size_pct adalah proporsi dari total modal (misal 0.1 = 10% modal)
        notional_value = balance * size_pct 
        
        # Berapa koin yang didapat dari Dolar tersebut?
        raw_qty = notional_value / entry_price
        
        # Format ke presisi Bybit agar tidak kena error invalid_qty!
        return self.format_qty(symbol, raw_qty)

    def cancel_all_active_orders(self, symbol: str = None) -> bool:
        """The True Kill Switch Action: Membatalkan semua pending order di Bybit"""
        target = symbol or "ALL MARKETS"
        if DRY_RUN:
            log(f"🛡️ DRY_RUN: Simulated cancellation of all open orders for {target}")
            return True
            
        try:
            log(f"🚨 EXECUTING MASS CANCEL for {target}...")
            # CCXT mendukung cancel_all_orders untuk Bybit API V5
            self.exchange.cancel_all_orders(symbol)
            log(f"✅ Mass Cancel Successful for {target}!")
            return True
        except Exception as e:
            log_error(f"❌ Mass Cancel Error for {target}", e)
            return False


    def fetch_balance(self, coin: str = "USDT") -> float:
        """Menyedot saldo asli dari dompet Bybit"""
        if DRY_RUN: return 1000.0 # Saldo bohong-bohongan untuk simulasi
        try:
            bal = self.exchange.fetch_balance()
            return float(bal.get('free', {}).get(coin, 0.0))
        except Exception as e:
            log_error(f"Fetch Balance Error ({coin})", e)
            return 0.0

    def calc_order_qty(self, symbol: str, price: float, risk_pct: float = 0.02) -> float:
        """Menghitung Kuantitas (Lot) berdasarkan 2% (default) dari Saldo USDT"""
        bal = self.fetch_balance("USDT")
        notional = bal * risk_pct  # Berapa USDT yang mau dirisikokan
        if price <= 0: return 0.0
        raw_qty = notional / price
        return self.format_qty(symbol, raw_qty)

    def cancel_all_orders(self, symbol: str = None):
        """Senjata Kill Switch: Membatalkan semua antrean limit/stop di Bybit"""
        if DRY_RUN:
            log(f"🛡️ DRY_RUN: Simulated cancel_all_orders for {symbol or 'ALL'}")
            return
        try:
            self.exchange.cancel_all_orders(symbol)
            log(f"🛑 KILLED ALL PENDING ORDERS for {symbol or 'ALL'} on Bybit!")
        except Exception as e:
            log_error("Cancel Orders Error", e)

    def calc_qty_from_usd(self, symbol: str, price: float, usd_amount: float) -> float:
        """Menghitung Lot Size murni berdasarkan nominal USD tetap ($1 / $2)"""
        if price <= 0: return 0.0
        raw_qty = usd_amount / price
        return self.format_qty(symbol, raw_qty)
