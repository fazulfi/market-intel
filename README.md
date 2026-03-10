# Market Intel Bot V3.5 (Multi-Instance Edition) 🚀

Market Intel is an Enterprise-Grade, event-driven cryptocurrency trading bot architecture. Built to handle layered setups, partial take-profits, and strict multi-instance isolation using Docker.

## 🌟 Key Features
- **Multi-Instance Architecture:** Deploy `Feeder` (Data Collector) and multiple `Worker` (Strategy Executors) independently.
- **Smart Timeframe Isolation:** DB-level filtering to prevent cross-contamination between 1m, 5m, and 15m instances.
- **Layered Entry & TP:** Supports 2-step entries and 3-step Take Profits with dynamic Stop-Loss movement (Break-Even protection).
- **Hybrid Market Data:** Combines Bybit WebSocket (Klines + Ticker) with a blazing-fast Redis in-memory cache.
- **Telegram Routing:** Decentralized reporting. Route alerts to specific Timeframe Channels and weekly summaries to Private Chat.

## 🛠️ Tech Stack
- **Engine:** Python 3.12-slim
- **Database:** PostgreSQL
- **Cache:** Redis
- **Testing:** Pytest
- **Deployment:** Docker & Docker Compose

## 🚀 Quick Start
1. Clone the repository.
2. Setup your Environment Variables:
   ```
   cp .env.template.feeder .env.1m
   cp .env.template.worker .env.5m```
3. Edit the .env files with your Bybit API Keys and Telegram credentials.

4. Launch the fleet:
   ```
   docker compose up -d --build```

🛡️ Architecture
Data Feeder (WS) ➡️ Redis + Postgres ➡️ Signal Engine ➡️ Entry Manager ➡️ Trade Manager ➡️ Telegram Alerts
