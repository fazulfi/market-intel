import json
import os
import time

import ccxt

from sniper.bybit import SniperBybit
from sniper.db import SniperRepo


def _log(msg: str) -> None:
    print(f"[sniper-main] {msg}", flush=True)


def parse_float_env(name: str, default: str) -> float:
    raw = os.getenv(name, default)
    try:
        return float(raw)
    except Exception:
        raise ValueError(f"Environment variable {name} tidak valid: {raw}")


def get_entry_margin_usd(action: str) -> float:
    entry1_margin = parse_float_env("ENTRY1_MARGIN_USD", "1.0")
    entry2_margin = parse_float_env("ENTRY2_MARGIN_USD", "2.0")

    if "ENTRY2" in action:
        return entry2_margin
    return entry1_margin


def main() -> None:
    timeframe = os.getenv("SNIPER_TIMEFRAME", "1m")
    sniper_name = os.getenv("SNIPER_NAME", f"sniper-{timeframe}")
    max_position_notional_usd = parse_float_env("MAX_POSITION_NOTIONAL_USD", "0")

    _log(
        f"STARTING {sniper_name} | timeframe={timeframe} | max_position_notional_usd={max_position_notional_usd}"
    )

    repo = SniperRepo()
    bybit = SniperBybit()

    bybit.load_markets()
    last_id = repo.get_last_seen_signal_id(timeframe)

    while True:
        try:
            rows = repo.fetch_new_action_signals(
                timeframe=timeframe,
                last_id=last_id,
                limit=50,
            )

            for sig in rows:
                last_id = max(last_id, int(sig["id"]))
                action = str(sig["signal_type"])
                symbol = str(sig["symbol"])

                payload = sig.get("payload", {})
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        payload = {}

                if not repo.claim_signal(sig, sniper_name=sniper_name, action=action):
                    continue

                _log(f"Menangkap sinyal: {action} | {symbol}")

                try:
                    order_id = None

                    # ENTRY
                    if "ENTRY1" in action or "ENTRY2" in action:
                        trade_side = "LONG" if "LONG" in action else "SHORT"
                        ccxt_side = "buy" if trade_side == "LONG" else "sell"

                        entry_margin_usd = get_entry_margin_usd(action)
                        leverage = bybit.resolve_entry_leverage(symbol)
                        current_px = bybit.get_current_price(symbol)

                        raw_qty = bybit.calc_order_amount_from_margin(
                            symbol=symbol,
                            margin_usd=entry_margin_usd,
                            price=current_px,
                            leverage=leverage,
                            max_position_notional_usd=max_position_notional_usd,
                        )

                        _log(
                            f"ENTRY action={action} symbol={symbol} side={trade_side} "
                            f"margin={entry_margin_usd} leverage={leverage} price={current_px} raw_qty={raw_qty}"
                        )

                        order_id = bybit.place_market_order(
                            symbol=symbol,
                            side=ccxt_side,
                            qty=raw_qty,
                            reduce_only=False,
                        )

                    # PARTIAL TP
                    elif "PARTIAL_TP" in action:
                        trade_side = str(payload.get("side", "LONG")).upper()
                        ccxt_side = "sell" if trade_side == "LONG" else "buy"

                        close_pct = float(payload.get("closed_pct", 0.3))
                        close_pct = max(0.0, min(close_pct, 1.0))

                        current_pos_size = bybit.get_position_size(symbol, trade_side)

                        if current_pos_size <= 0:
                            repo.mark_skipped(sig["id"], "Tidak ada posisi aktif di Bybit untuk di-TP")
                            continue

                        qty_to_close = current_pos_size * close_pct
                        formatted_qty = bybit.format_qty(symbol, qty_to_close)
                        min_amount = bybit.get_market_min_amount(symbol)

                        if formatted_qty <= 0:
                            repo.mark_skipped(
                                sig["id"],
                                "Qty partial close menjadi 0 setelah precision formatting",
                            )
                            continue

                        if min_amount > 0 and formatted_qty < min_amount:
                            _log(
                                f"Dust detected {symbol}: {formatted_qty} < {min_amount}. Ubah jadi full close."
                            )
                            qty_to_close = current_pos_size

                        order_id = bybit.place_market_order(
                            symbol=symbol,
                            side=ccxt_side,
                            qty=qty_to_close,
                            reduce_only=True,
                        )

                    # CLOSE
                    elif "CLOSE" in action:
                        trade_side = str(payload.get("side", "LONG")).upper()
                        ccxt_side = "sell" if trade_side == "LONG" else "buy"

                        current_pos_size = bybit.get_position_size(symbol, trade_side)

                        if current_pos_size <= 0:
                            repo.mark_skipped(sig["id"], "Tidak ada posisi aktif di Bybit untuk di-close")
                            continue

                        order_id = bybit.place_market_order(
                            symbol=symbol,
                            side=ccxt_side,
                            qty=current_pos_size,
                            reduce_only=True,
                        )

                    else:
                        repo.mark_skipped(sig["id"], f"Signal type tidak dikenali executor: {action}")
                        continue

                    if order_id:
                        repo.mark_success(sig["id"], exchange_order_id=order_id)

                except ValueError as ve:
                    _log(f"Terminal error: {ve}")
                    repo.mark_failed(sig["id"], f"TERMINAL: {ve}")

                except (
                    ccxt.NetworkError,
                    ccxt.RequestTimeout,
                    ccxt.RateLimitExceeded,
                    ccxt.DDoSProtection,
                ) as ne:
                    _log(f"Retryable candidate: {ne}")
                    repo.mark_failed(sig["id"], f"RETRYABLE_CANDIDATE: {ne}")

                except (
                    ccxt.InvalidOrder,
                    ccxt.InsufficientFunds,
                    ccxt.BadSymbol,
                    ccxt.ExchangeError,
                ) as ee:
                    _log(f"Exchange terminal error: {ee}")
                    repo.mark_failed(sig["id"], f"TERMINAL: {ee}")

                except Exception as e:
                    _log(f"Unknown terminal error: {e}")
                    repo.mark_failed(sig["id"], f"TERMINAL: {e}")

        except Exception as e:
            _log(f"Error di loop utama: {e}")

        time.sleep(1.5)


if __name__ == "__main__":
    main()
