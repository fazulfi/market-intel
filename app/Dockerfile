FROM python:3.12-slim

# Kita ubah workdir-nya agar tidak bentrok dengan nama package 'app'
WORKDIR /workspace

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kita masukkan ke dalam sub-folder /app
COPY . ./app

CMD ["python", "-u", "-m", "app.main"]
