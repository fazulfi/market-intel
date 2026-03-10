FROM python:3.12-slim

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir \
    ccxt==4.4.93 \
    psycopg[binary]==3.2.1 \
    psycopg-pool==3.2.1

COPY . /workspace/sniper

CMD ["python", "-u", "-m", "sniper.main"]
