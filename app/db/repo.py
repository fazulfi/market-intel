import time
import json
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from app.config import DB_DSN
from app.utils.logging import log

class Repo:
    def __init__(self):
        self.pool = self._init_pool()

    def _init_pool(self):
        while True:
            try:
                pool = ConnectionPool(conninfo=DB_DSN, min_size=1, max_size=10, kwargs={"row_factory": dict_row})
                with pool.connection() as conn:
                    conn.execute("SELECT 1;")
                log("PostgreSQL connected (pool ready)")
                return pool
            except Exception as e:
                log(f"Waiting DB... {e}")
                time.sleep(2)

    def init_schema(self):
        from pathlib import Path
        schema_path = Path(__file__).parent / "schema.sql"
        sql = schema_path.read_text()
        with self.pool.connection() as conn:
            conn.execute(sql)

    def upsert_candles(self, exchange, symbol, tf, candles):
        sql = """
        INSERT INTO candles (exchange,symbol,timeframe,ts_ms,open,high,low,close,volume)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING;
        """
        rows = [(exchange, symbol, tf, *c) for c in candles]
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)

    def get_recent_candles(self, exchange, symbol, tf, limit):
        sql = "SELECT ts_ms,open,high,low,close,volume FROM candles WHERE exchange=%s AND symbol=%s AND timeframe=%s ORDER BY ts_ms DESC LIMIT %s;"
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (exchange, symbol, tf, limit))
                rows = cur.fetchall()
        return list(reversed(rows))

    def insert_signal(self, exchange, symbol, tf, ts, stype, payload):
        sql = """
        INSERT INTO signals (exchange, symbol, timeframe, ts_ms, signal_type, payload)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT (exchange, symbol, timeframe, ts_ms, signal_type) DO NOTHING;
        """
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (exchange, symbol, tf, ts, stype, json.dumps(payload)))

    def fetch_new_signals(self, last_id):
        sql = "SELECT * FROM signals WHERE id > %s ORDER BY id ASC LIMIT 100;"
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (last_id,))
                return cur.fetchall()

    def mark_alert_sent(self, exchange, symbol, tf, ts, stype):
        sql = "INSERT INTO alerts (exchange,symbol,timeframe,ts_ms,signal_type) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING;"
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (exchange, symbol, tf, ts, stype))
                return cur.rowcount == 1

    # --- V1.6 TRADE METHODS ---
    def get_open_trade(self, exchange, symbol, tf):
        sql = "SELECT * FROM trades WHERE exchange=%s AND symbol=%s AND timeframe=%s AND status='OPEN' ORDER BY id DESC LIMIT 1;"
        with self.pool.connection() as conn:
            row = conn.execute(sql, (exchange, symbol, tf)).fetchone()
            return dict(row) if row else None

    def open_trade(self, exchange, symbol, tf, side, opened_ts_ms, payload: dict):
        sql = """
        INSERT INTO trades (exchange, symbol, timeframe, side, status, opened_ts_ms, entry, tp, sl, atr14, vol_mult, level)
        VALUES (%s,%s,%s,%s,'OPEN',%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id;
        """
        with self.pool.connection() as conn:
            r = conn.execute(sql, (
                exchange, symbol, tf, side, int(opened_ts_ms),
                float(payload["entry"]), float(payload["tp"]), float(payload["sl"]),
                float(payload.get("atr14")) if payload.get("atr14") is not None else None,
                float(payload.get("vol_mult")) if payload.get("vol_mult") is not None else None,
                float(payload.get("level")) if payload.get("level") is not None else None,
            )).fetchone()
            # 🚨 BUG FIX: Ambil ID dengan Dictionary Key, bukan Array Index!
            return r["id"] if r else None

    def close_trade(self, trade_id: int, closed_ts_ms: int, close_price: float, reason: str):
        sql = "UPDATE trades SET status='CLOSED', closed_ts_ms=%s, close_price=%s, close_reason=%s, closed_at=now() WHERE id=%s AND status='OPEN' RETURNING id;"
        with self.pool.connection() as conn:
            r = conn.execute(sql, (int(closed_ts_ms), float(close_price), reason, int(trade_id))).fetchone()
            return bool(r)


    # --- V2.5 PARTIAL TP METHODS ---
    def mark_partial_tp(self, trade_id: int, tp_level: int, close_pct: float, pnl_added: float, new_sl: float = None):
        tp_col = f"tp{tp_level}_hit"
        if new_sl is None:
            sql = f"UPDATE trades SET {tp_col} = true, remaining_size_pct = GREATEST(remaining_size_pct - %s, 0.0), realized_pnl_pct = realized_pnl_pct + %s, updated_at = now() WHERE id = %s AND status = 'OPEN' RETURNING id;"
            params = (float(close_pct), float(pnl_added), int(trade_id))
        else:
            sql = f"UPDATE trades SET {tp_col} = true, remaining_size_pct = GREATEST(remaining_size_pct - %s, 0.0), realized_pnl_pct = realized_pnl_pct + %s, sl = %s, updated_at = now() WHERE id = %s AND status = 'OPEN' RETURNING id;"
            params = (float(close_pct), float(pnl_added), float(new_sl), int(trade_id))
        with self.pool.connection() as conn:
            r = conn.execute(sql, params).fetchone()
            return bool(r)

    def close_trade_v25(self, trade_id: int, closed_ts_ms: int, close_price: float, close_reason: str, final_pnl: float, hit_tp3: bool = False):
        sql = "UPDATE trades SET status='CLOSED', closed_ts_ms=%s, close_price=%s, close_reason=%s, realized_pnl_pct = realized_pnl_pct + %s, remaining_size_pct = 0.0, tp3_hit = CASE WHEN %s THEN true ELSE tp3_hit END, closed_at = now(), updated_at = now() WHERE id=%s AND status='OPEN' RETURNING id;"
        with self.pool.connection() as conn:
            r = conn.execute(sql, (int(closed_ts_ms), float(close_price), str(close_reason), float(final_pnl), bool(hit_tp3), int(trade_id))).fetchone()
            return bool(r)

    def list_open_trades(self, tfs: list):
        sql = "SELECT * FROM trades WHERE status='OPEN' AND timeframe = ANY(%s) ORDER BY id ASC;"
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (tfs,)).fetchall()
            return [dict(r) for r in rows]

    # --- V1.7 SUMMARY METHODS ---
    def fetch_open_trades_count(self, tfs: list):
        sql = "SELECT COUNT(*) AS open_count FROM trades WHERE status='OPEN' AND timeframe = ANY(%s);"
        with self.pool.connection() as conn:
            row = conn.execute(sql, (tfs,)).fetchone()
            return int(row["open_count"]) if row else 0

    def fetch_trade_stats_window(self, seconds: int, tfs: list):
        sql = '''
        WITH base AS (
            SELECT
                CASE
                    WHEN (tp1_hit = true OR tp2_hit = true OR tp3_hit = true OR realized_pnl_pct != 0)
                        THEN realized_pnl_pct
                    WHEN side='LONG' THEN (close_price - entry) / entry * 100.0
                    WHEN side='SHORT' THEN (entry - close_price) / entry * 100.0
                    ELSE 0.0
                END AS pnl_pct,
                close_reason
            FROM trades
            WHERE status='CLOSED'
              AND closed_at >= now() - (%s || ' seconds')::interval
              AND timeframe = ANY(%s)
        )
        SELECT
            COUNT(*) AS closed,
            COUNT(*) FILTER (WHERE pnl_pct > 0) AS wins,
            COUNT(*) FILTER (WHERE pnl_pct <= 0) AS losses,
            COUNT(*) FILTER (WHERE close_reason = 'SL (Break-Even)') AS be_exits,
            COALESCE(AVG(pnl_pct), 0) AS avg_pnl,
            COALESCE(SUM(pnl_pct), 0) AS sum_pnl
        FROM base;
        '''
        with self.pool.connection() as conn:
            row = conn.execute(sql, (seconds, tfs)).fetchone()
            return dict(row) if row else {}

    def upsert_setup_pending(self, exchange, symbol, tf, side, created_ts_ms, expires_ts_ms, level, payload: dict):
        import json
        sql = '''
        INSERT INTO trade_setups (exchange, symbol, timeframe, side, status, created_ts_ms, expires_ts_ms, level, payload)
        VALUES (%s,%s,%s,%s,'PENDING',%s,%s,%s,%s::jsonb)
        ON CONFLICT (exchange, symbol, timeframe) WHERE status = 'PENDING'
        DO UPDATE SET
            side = EXCLUDED.side, created_ts_ms = EXCLUDED.created_ts_ms,
            expires_ts_ms = EXCLUDED.expires_ts_ms, level = EXCLUDED.level,
            payload = EXCLUDED.payload, updated_at = now()
        RETURNING id;
        '''
        with self.pool.connection() as conn:
            r = conn.execute(sql, (exchange, symbol, tf, side, int(created_ts_ms), int(expires_ts_ms), float(level), json.dumps(payload))).fetchone()
            return r["id"] if r else None

    def list_pending_setups(self, tfs: list):
        sql = "SELECT * FROM trade_setups WHERE status='PENDING' AND timeframe = ANY(%s) ORDER BY id ASC;"
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (tfs,)).fetchall()
            return [dict(r) for r in rows]

    def mark_setup_triggered(self, setup_id: int):
        sql = "UPDATE trade_setups SET status='TRIGGERED', updated_at=now() WHERE id=%s AND status='PENDING' RETURNING id;"
        with self.pool.connection() as conn:
            return bool(conn.execute(sql, (int(setup_id),)).fetchone())

    def mark_setup_expired(self, setup_id: int):
        sql = "UPDATE trade_setups SET status='EXPIRED', updated_at=now() WHERE id=%s AND status='PENDING' RETURNING id;"
        with self.pool.connection() as conn:
            return bool(conn.execute(sql, (int(setup_id),)).fetchone())


    # --- V2.3 TWO-STEP ENTRY ---
    def open_trade_two_step(self, exchange, symbol, tf, side, opened_ts_ms, payload: dict):
        sql = '''
        INSERT INTO trades (
            exchange, symbol, timeframe, side, status, opened_ts_ms,
            entry, tp, sl, atr14, vol_mult, level,
            entry1, entry2, entry1_size, entry2_size, filled_entry2, avg_entry
        )
        VALUES (%s,%s,%s,%s,'OPEN',%s,
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
        RETURNING id;
        '''
        with self.pool.connection() as conn:
            r = conn.execute(sql, (
                exchange, symbol, tf, side, int(opened_ts_ms),
                float(payload["entry"]), float(payload["tp"]), float(payload["sl"]),
                float(payload.get("atr14")) if payload.get("atr14") is not None else None,
                float(payload.get("vol_mult")) if payload.get("vol_mult") is not None else None,
                float(payload.get("level")) if payload.get("level") is not None else None,
                float(payload.get("entry1")) if payload.get("entry1") is not None else None,
                float(payload.get("entry2")) if payload.get("entry2") is not None else None,
                float(payload.get("entry1_size")) if payload.get("entry1_size") is not None else None,
                float(payload.get("entry2_size")) if payload.get("entry2_size") is not None else None,
                bool(payload.get("filled_entry2", False)),
                float(payload.get("avg_entry")) if payload.get("avg_entry") is not None else None,
            )).fetchone()
            return r["id"] if r else None

    def mark_entry2_filled(self, trade_id: int, avg_entry: float):
        sql = '''
        UPDATE trades
        SET filled_entry2 = true,
            avg_entry = %s,
            entry = %s,
            updated_at = now()
        WHERE id = %s AND status = 'OPEN' AND filled_entry2 = false
        RETURNING id;
        '''
        with self.pool.connection() as conn:
            r = conn.execute(sql, (float(avg_entry), float(avg_entry), int(trade_id))).fetchone()
            return bool(r)

    def has_recent_closed_trade(self, exchange, symbol, tf, cooldown_sec: int):
        sql = '''
        SELECT 1
        FROM trades
        WHERE exchange=%s
          AND symbol=%s
          AND timeframe=%s
          AND status='CLOSED'
          AND closed_at >= now() - (%s || ' seconds')::interval
        LIMIT 1;
        '''
        with self.pool.connection() as conn:
            row = conn.execute(sql, (exchange, symbol, tf, int(cooldown_sec))).fetchone()
            return bool(row)

    # --- V2.3.1 POST-CLOSE COOLDOWN BY BARS ---
    def has_recent_closed_trade_bars(self, exchange, symbol, tf, current_ts_ms: int, cooldown_bars: int):
        tf_sec = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
        sec = tf_sec.get(tf, 60)
        lookback_ms = int(cooldown_bars) * sec * 1000

        sql = '''
        SELECT 1
        FROM trades
        WHERE exchange=%s
          AND symbol=%s
          AND timeframe=%s
          AND status='CLOSED'
          AND closed_ts_ms >= %s
        LIMIT 1;
        '''
        with self.pool.connection() as conn:
            row = conn.execute(sql, (exchange, symbol, tf, int(current_ts_ms - lookback_ms))).fetchone()
            return bool(row)

    # --- V2.4 LAYERED SETUP ---
    def create_layered_setup(self, exchange, symbol, tf, side, created_ts_ms, expires_ts_ms, payload: dict):
        sql = '''
        INSERT INTO trade_setups (
            exchange, symbol, timeframe, side, status, created_ts_ms, expires_ts_ms, level, payload,
            entry1, entry2, sl, tp1, tp2, tp3, atr14, filled_entry1, filled_entry2, avg_entry, entry1_size, entry2_size, updated_at
        ) VALUES (
            %s,%s,%s,%s,'PENDING',%s,%s,%s,%s::jsonb,
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now()
        )
        ON CONFLICT (exchange, symbol, timeframe) WHERE status='PENDING'
        DO UPDATE SET
            side=EXCLUDED.side, expires_ts_ms=EXCLUDED.expires_ts_ms, level=EXCLUDED.level, payload=EXCLUDED.payload,
            entry1=EXCLUDED.entry1, entry2=EXCLUDED.entry2, sl=EXCLUDED.sl, tp1=EXCLUDED.tp1, tp2=EXCLUDED.tp2, tp3=EXCLUDED.tp3,
            atr14=EXCLUDED.atr14, entry1_size=EXCLUDED.entry1_size, entry2_size=EXCLUDED.entry2_size, updated_at=now()
        RETURNING id;
        '''
        import json
        with self.pool.connection() as conn:
            r = conn.execute(sql, (
                exchange, symbol, tf, side, int(created_ts_ms), int(expires_ts_ms), float(payload["level"]), json.dumps(payload),
                float(payload["entry1"]), float(payload["entry2"]), float(payload["sl"]), float(payload["tp1"]),
                float(payload["tp2"]), float(payload["tp3"]), float(payload["atr14"]), False, False, 
                float(payload["entry1"]), float(payload["entry1_size"]), float(payload["entry2_size"])
            )).fetchone()
            return r["id"] if r else None

    def open_trade_from_setup(self, setup: dict, opened_ts_ms: int):
        sql = '''
        INSERT INTO trades (
            exchange, symbol, timeframe, side, status, opened_ts_ms,
            entry, tp, sl, atr14, vol_mult, level,
            entry1, entry2, entry1_size, entry2_size, filled_entry2, avg_entry,
            tp1, tp2, tp3, remaining_size_pct, realized_pnl_pct,
            tp1_hit, tp2_hit, tp3_hit, updated_at
        ) VALUES (
            %s,%s,%s,%s,'OPEN',%s,
            %s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,
            %s,%s,%s,1.0,0.0,
            false,false,false, now()
        ) ON CONFLICT DO NOTHING RETURNING id;
        '''
        import json
        p = setup.get("payload", {})
        if isinstance(p, str):
            p = json.loads(p)
        with self.pool.connection() as conn:
            r = conn.execute(sql, (
                setup["exchange"], setup["symbol"], setup["timeframe"], setup["side"], int(opened_ts_ms),
                float(setup.get("avg_entry", setup["entry1"])),
                float(setup["tp3"]),
                float(setup["sl"]),
                float(setup["atr14"]),
                float(p.get("vol_mult")) if p.get("vol_mult") is not None else None,
                float(setup["level"]),
                float(setup["entry1"]),
                float(setup["entry2"]),
                float(setup["entry1_size"]),
                float(setup["entry2_size"]),
                False,
                float(setup.get("avg_entry", setup["entry1"])),
                float(setup.get("tp1", 0)),
                float(setup.get("tp2", 0)),
                float(setup.get("tp3", 0)),
            )).fetchone()
            return r["id"] if r else None

