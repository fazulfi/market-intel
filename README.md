# Market Intel Bot

Market Intel adalah bot trading crypto berbasis event-driven architecture untuk Bybit, dirancang untuk menjalankan strategi multi-instance per timeframe dengan isolasi state yang ketat, penyimpanan data di PostgreSQL, cache tick real-time di Redis, dan pengiriman alert ke Telegram.

## Fitur Utama

- Multi-instance worker per timeframe, sehingga 1m, 5m, dan 15m dapat berjalan terpisah tanpa saling mengganggu.
- Penyimpanan candle, signal, setup, trade, dan alert di PostgreSQL.
- Redis sebagai cache harga tick real-time untuk mempercepat keputusan entry dan trade management.
- Hybrid market data:
  - WebSocket ticker untuk harga live
  - WebSocket klines untuk candle confirmed
  - REST backfill opsional saat startup
- Breakout + volume spike + trend filter berbasis EMA.
- Layered setup:
  - Entry 1
  - Entry 2
  - TP1 / TP2 / TP3
  - Stop-loss dinamis
  - Break-even dan trailing logic
- Alert Telegram untuk setup, fill, partial TP, close, dan summary periodik.
- Dockerized deployment untuk VPS / server 24/7.

## Arsitektur

Market Data (Bybit WS/REST)
-> Redis + PostgreSQL
-> Signal Engine
-> Entry Manager
-> Trade Manager
-> Telegram Alerts / Summary

## Komponen Utama

- `db`
  Database PostgreSQL untuk candle, signal, setup, trade, dan alert.

- `redis`
  Cache in-memory untuk tick live.

- `app-1m`
  Instance worker untuk timeframe 1m.

- `app-5m`
  Instance worker untuk timeframe 5m.

- `app-15m`
  Instance worker untuk timeframe 15m.

## Struktur Singkat

- `app/main.py`
  Entry point aplikasi.

- `app/config.py`
  Seluruh konfigurasi environment variable.

- `app/db/schema.sql`
  Schema database.

- `app/db/repo.py`
  Abstraksi akses database.

- `app/services/signals.py`
  Engine pembuat setup signal.

- `app/services/entry_manager.py`
  Engine fill Entry 1 dan Entry 2.

- `app/services/trade_manager.py`
  Engine partial take profit, SL, BE, dan trailing.

- `app/services/alerts.py`
  Pengirim alert Telegram.

- `app/services/summary.py`
  Ringkasan performa periodik.

- `app/services/ws_ticker.py`
  WebSocket ticker live.

- `app/services/ws_klines.py`
  WebSocket klines confirmed.

- `tickers.txt`
  Daftar simbol yang dipantau.

## Requirements

- Docker
- Docker Compose
- VPS / server Linux yang stabil
- API key Bybit jika strategi / collector memerlukannya
- Telegram bot token dan chat/channel ID

## Quick Start

1. Clone repository

   git clone https://github.com/fazulfi/market-intel.git
   cd market-intel

2. Siapkan file environment untuk tiap instance

   Buat file berikut:
   - `.env.1m`
   - `.env.5m`
   - `.env.15m`

3. Siapkan daftar simbol di `tickers.txt`

   Contoh:
   BTC/USDT:USDT
   ETH/USDT:USDT
   SOL/USDT:USDT

4. Jalankan seluruh stack

   docker compose up -d --build

5. Cek log

   docker compose logs -f app-1m
   docker compose logs -f app-5m
   docker compose logs -f app-15m

## Environment Variables Utama

Berikut variabel yang paling penting untuk diisi.

### Koneksi Database

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

### Redis

- `REDIS_URL`

### Exchange

- `EXCHANGE`
- `SYMBOLS` atau gunakan `SYMBOLS_FILE`
- `TIMEFRAMES`

### Signal Engine

- `BREAKOUT_N`
- `VOL_AVG_N`
- `VOL_SPIKE_K`
- `EMA_TREND_N`
- `EMA_TREND_TF`
- `TREND_TF_MAP`
- `ATR_TF_MAP`
- `ATR_N`
- `ATR_WARMUP`
- `SIGNAL_INTERVAL_SEC`

### Setup / Entry / TP / SL

- `ENTRY1_SIZE`
- `ENTRY2_SIZE`
- `ENTRY1_ATR_OFFSET`
- `ENTRY2_ATR_OFFSET`
- `ENTRY1_CHASE_ATR_PCT`
- `TP1_ATR_MULT`
- `TP2_ATR_MULT`
- `TP3_ATR_MULT`
- `SL_ATR_MULT`
- `TP1_CLOSE_PCT`
- `TP2_CLOSE_PCT`
- `TP3_CLOSE_PCT`
- `SETUP_EXPIRY_BARS`
- `POST_CLOSE_COOLDOWN_BARS`

### WebSocket / Collector

- `ENABLE_WS_TICKER`
- `ENABLE_WS_KLINES`
- `ENABLE_REST_COLLECTOR`
- `WS_MARKET_TYPE`
- `WS_PING_SEC`
- `WS_RECONNECT_SEC`
- `BYBIT_WS_PUBLIC_URL`
- `WS_KLINE_TIMEFRAMES`

### Telegram

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_CHANNEL_ID`
- `ALERT_COOLDOWN_SEC`

### Summary

- `ENABLE_SUMMARY`
- `SUMMARY_HOURLY_MINUTE`
- `SUMMARY_DAILY_HOUR`
- `SUMMARY_DAILY_MINUTE`
- `SUMMARY_WEEKLY_DAY`
- `SUMMARY_WEEKLY_HOUR`
- `SUMMARY_WEEKLY_MINUTE`

## Contoh Workflow Operasional

### Menjalankan bot

docker compose up -d --build

### Menghentikan bot

docker compose down

### Restart semua service

docker compose restart

### Melihat log satu instance

docker compose logs -f app-1m

### Melihat status container

docker compose ps

## Catatan Penting

- Tiap instance berjalan dengan file env masing-masing agar konfigurasi timeframe tetap terisolasi.
- `tickers.txt` dibaca dari path `/workspace/tickers.txt` di dalam container.
- PostgreSQL menyimpan state trading utama. Jangan asal hapus volume kalau masih butuh histori trade.
- Redis dipakai untuk state tick live. Jika Redis mati, sebagian logic akan fallback ke candle terbaru, tetapi performa real-time bisa menurun.
- Jika kamu mengubah schema database, jangan hanya mengubah `schema.sql`. Pastikan database existing juga dimigrasikan dengan benar.
- Untuk deployment baru dari nol, pastikan schema dan container dibangun ulang dengan bersih.

## Troubleshooting

### Bot hidup tapi tidak ada signal
Periksa:
- `tickers.txt`
- mapping timeframe
- data candle sudah masuk ke PostgreSQL
- trend filter / breakout parameter terlalu ketat

### WebSocket reconnect terus
Periksa:
- koneksi internet VPS
- URL websocket
- symbol format Bybit
- rate limit / gangguan provider

### Alert Telegram tidak masuk
Periksa:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_CHANNEL_ID`
- bot sudah diundang ke channel / group
- format permission Telegram

### Fresh deploy error kolom database
Itu biasanya berarti schema file dan database existing tidak sinkron.
Solusi:
- lakukan migration yang benar
- atau reset volume database jika histori tidak diperlukan

## Rekomendasi Pengembangan Selanjutnya

- Tambahkan test otomatis untuk signal logic, entry logic, dan trade management.
- Tambahkan migration versioning agar perubahan schema tidak bergantung pada patch manual.
- Tambahkan healthcheck aplikasi yang lebih spesifik selain log heartbeat.
- Rapikan dokumentasi environment variable per instance agar onboarding lebih cepat.

## Disclaimer

Bot ini adalah sistem eksekusi strategi dan monitoring pasar. Penggunaan di market live memiliki risiko finansial. Gunakan dengan parameter, validasi, dan pengawasan yang memadai.

## License

MIT
