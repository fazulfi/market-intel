FROM python:3.12-slim
WORKDIR /workspace
RUN pip install --no-cache-dir psycopg[binary]==3.2.1 psycopg-pool==3.2.1 ccxt==4.4.93
COPY . ./sniper
CMD ["python", "-u", "-m", "sniper.main"]
