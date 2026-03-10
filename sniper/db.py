import os
import time
from typing import Iterable, Optional

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row


DEFAULT_SIGNAL_TYPES = [
    "FILL_LONG_ENTRY1",
    "FILL_SHORT_ENTRY1",
    "FILL_LONG_ENTRY2",
    "FILL_SHORT_ENTRY2",
    "PARTIAL_TP1",
    "PARTIAL_TP2",
    "CLOSE_TP3",
    "CLOSE_SL",
    "CLOSE_RECON",
]


def _build_dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("POSTGRES_DB", "marketintel")
    user = os.getenv("POSTGRES_USER", "marketintel")
    password = os.getenv("POSTGRES_PASSWORD", "marketintel")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def _log(msg: str) -> None:
    print(f"[sniper-db] {msg}", flush=True)


class SniperRepo:
    def __init__(self) -> None:
        self.dsn = _build_dsn()
        self.pool = self._init_pool()

    def _init_pool(self) -> ConnectionPool:
        while True:
            try:
                pool = ConnectionPool(
                    conninfo=self.dsn,
                    min_size=1,
                    max_size=10,
                    kwargs={"row_factory": dict_row},
                )
                with pool.connection() as conn:
                    conn.execute("SELECT 1;")
                _log("PostgreSQL connected (pool ready)")
                return pool
            except Exception as e:
                _log(f"Waiting DB... {e}")
                time.sleep(2)

    def fetch_new_action_signals(
        self,
        timeframe: str,
        last_id: int = 0,
        signal_types: Optional[Iterable[str]] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Ambil sinyal baru untuk timeframe tertentu yang BELUM pernah tercatat
        di executed_signals.

        last_id hanya optimisasi scan.
        Sumber kebenaran anti-double tetap executed_signals.
        """
        signal_types = list(signal_types or DEFAULT_SIGNAL_TYPES)

        sql = """
        SELECT s.*
        FROM signals s
        LEFT JOIN executed_signals e
          ON e.signal_id = s.id
        WHERE s.id > %s
          AND s.timeframe = %s
          AND s.signal_type = ANY(%s)
          AND e.signal_id IS NULL
        ORDER BY s.id ASC
        LIMIT %s;
        """
        with self.pool.connection() as conn:
            rows = conn.execute(sql, (int(last_id), timeframe, signal_types, int(limit))).fetchall()
            return [dict(r) for r in rows]

    def claim_signal(self, signal: dict, sniper_name: str, action: str) -> bool:
        """
        Klaim sinyal secara atomik.
        Kalau signal_id sudah ada, berarti sudah pernah diambil/ditangani.
        """
        sql = """
        INSERT INTO executed_signals (
            signal_id,
            sniper_name,
            exchange,
            symbol,
            timeframe,
            signal_type,
            action,
            status,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING', now(), now())
        ON CONFLICT (signal_id) DO NOTHING
        RETURNING signal_id;
        """
        with self.pool.connection() as conn:
            row = conn.execute(
                sql,
                (
                    int(signal["id"]),
                    sniper_name,
                    signal["exchange"],
                    signal["symbol"],
                    signal["timeframe"],
                    signal["signal_type"],
                    action,
                ),
            ).fetchone()
            return bool(row)

    def mark_success(self, signal_id: int, exchange_order_id: Optional[str] = None) -> bool:
        sql = """
        UPDATE executed_signals
        SET status = 'SUCCESS',
            exchange_order_id = %s,
            executed_at = now(),
            updated_at = now(),
            error_msg = NULL
        WHERE signal_id = %s
          AND status = 'PENDING'
        RETURNING signal_id;
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (exchange_order_id, int(signal_id))).fetchone()
            return bool(row)

    def mark_failed(self, signal_id: int, error_msg: str) -> bool:
        """
        FAILED dibuat terminal secara sengaja.
        Lebih aman butuh replay manual daripada order live nyelonong dua kali.
        """
        sql = """
        UPDATE executed_signals
        SET status = 'FAILED',
            error_msg = %s,
            updated_at = now()
        WHERE signal_id = %s
          AND status = 'PENDING'
        RETURNING signal_id;
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (str(error_msg)[:2000], int(signal_id))).fetchone()
            return bool(row)

    def mark_skipped(self, signal_id: int, reason: str) -> bool:
        sql = """
        UPDATE executed_signals
        SET status = 'SKIPPED',
            error_msg = %s,
            executed_at = now(),
            updated_at = now()
        WHERE signal_id = %s
          AND status = 'PENDING'
        RETURNING signal_id;
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (str(reason)[:2000], int(signal_id))).fetchone()
            return bool(row)

    def get_execution(self, signal_id: int) -> Optional[dict]:
        sql = "SELECT * FROM executed_signals WHERE signal_id = %s LIMIT 1;"
        with self.pool.connection() as conn:
            row = conn.execute(sql, (int(signal_id),)).fetchone()
            return dict(row) if row else None

    def get_last_seen_signal_id(self, timeframe: str) -> int:
        """
        Opsional: bantu bootstrap cursor per timeframe.
        Tidak dipakai untuk keamanan, hanya untuk performa.
        """
        sql = """
        SELECT COALESCE(MAX(signal_id), 0) AS last_id
        FROM executed_signals
        WHERE timeframe = %s;
        """
        with self.pool.connection() as conn:
            row = conn.execute(sql, (timeframe,)).fetchone()
            return int(row["last_id"]) if row else 0
