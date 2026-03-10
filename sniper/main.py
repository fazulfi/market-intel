import os
import time
import json
from sniper.db import SniperRepo
from sniper.bybit import SniperBybit

def _log(msg: str) -> None:
    print(f"[sniper-main] {msg}", flush=True)

def main():
    timeframe = os.getenv("SNIPER_TIMEFRAME", "1m")
    sniper_name = os.getenv("SNIPER_NAME", f"sniper-{timeframe}")
    
    # PERUBAHAN NAMA: Lebih akurat secara trading
    max_notional_usd = float(os.getenv("MAX_NOTIONAL_USD", "2.0"))  
    
    _log(f"🔥 {sniper_name} STARTING! Memantau sinyal {timeframe}. Max Notional: ${max_notional_usd}")

    repo = SniperRepo()
    bybit = SniperBybit()
    
    # Pre-load market rules saat start
    bybit.load_markets()
    last_id = repo.get_last_seen_signal_id(timeframe)

    while True:
        try:
            rows = repo.fetch_new_action_signals(timeframe=timeframe, last_id=last_id, limit=50)

            for sig in rows:
                last_id = max(last_id, sig["id"])
                action = sig["signal_type"]
                symbol = sig["symbol"]
                
                payload = sig.get("payload", {})
                if isinstance(payload, str):
                    try: payload = json.loads(payload)
                    except: payload = {}

                # 1. KLAIM SINYAL (Idempotency Check / Anti Dobel)
                if not repo.claim_signal(sig, sniper_name=sniper_name, action=action):
                    continue 

                _log(f"🎯 Menangkap Sinyal: {action} untuk {symbol}")

                try:
                    order_id = None
                    
                    # --- LOGIKA ENTRY ---
                    if "ENTRY1" in action or "ENTRY2" in action:
                        trade_side = "LONG" if "LONG" in action else "SHORT"
                        ccxt_side = "buy" if trade_side == "LONG" else "sell"
                        
                        current_px = bybit.get_current_price(symbol)
                        raw_qty = max_notional_usd / current_px
                        
                        order_id = bybit.place_market_order(symbol, ccxt_side, raw_qty, reduce_only=False)

                    # --- LOGIKA PARTIAL TP ---
                    elif "PARTIAL_TP" in action:
                        trade_side = payload.get("side", "LONG")
                        ccxt_side = "sell" if trade_side == "LONG" else "buy"
                        
                        close_pct = float(payload.get("closed_pct", 0.3)) 
                        current_pos_size = bybit.get_position_size(symbol, trade_side)
                        
                        if current_pos_size > 0:
                            qty_to_close = current_pos_size * close_pct
                            min_amount, _ = bybit.get_market_limits(symbol)
                            formatted_qty = bybit.format_qty(symbol, qty_to_close)
                            
                            # 🛡️ THE DUST FILTER
                            if formatted_qty < min_amount:
                                _log(f"⚠️ Dust Detected: {formatted_qty} < {min_amount}. Diubah menjadi FULL CLOSE agar posisi tidak nyangkut.")
                                qty_to_close = current_pos_size # Paksa jual semua
                                
                            order_id = bybit.place_market_order(symbol, ccxt_side, qty_to_close, reduce_only=True)
                        else:
                            repo.mark_skipped(sig["id"], "Tidak ada posisi aktif di Bybit untuk di-TP")
                            continue

                    # --- LOGIKA CLOSE (SL / TP3) ---
                    elif "CLOSE" in action:
                        trade_side = payload.get("side", "LONG")
                        ccxt_side = "sell" if trade_side == "LONG" else "buy"
                        
                        current_pos_size = bybit.get_position_size(symbol, trade_side)
                        
                        if current_pos_size > 0:
                            order_id = bybit.place_market_order(symbol, ccxt_side, current_pos_size, reduce_only=True)
                        else:
                            repo.mark_skipped(sig["id"], "Tidak ada posisi aktif di Bybit untuk di-Close")
                            continue

                    # 3. CATAT SUKSES
                    if order_id:
                        repo.mark_success(sig["id"], exchange_order_id=order_id)

                except ValueError as ve:
                    # Gagal karena aturan bursa (Lot terlalu kecil, dll)
                    _log(f"Terminal Error: {ve}")
                    repo.mark_failed(sig["id"], str(ve))
                except Exception as e:
                    # Gagal karena API/Network
                    _log(f"API Error: {e}")
                    repo.mark_failed(sig["id"], str(e))

        except Exception as e:
            _log(f"Error di loop utama: {e}")

        # Polling santai setiap 1.5 detik
        time.sleep(1.5)

if __name__ == "__main__":
    main()
