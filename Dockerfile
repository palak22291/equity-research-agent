FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libcurl4-openssl-dev libssl-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc g++ make \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
COPY . .
EXPOSE 7860
CMD ["sh", "-c", "python3 -m uvicorn app.api:app --host 0.0.0.0 --port ${PORT:-7860}"]

