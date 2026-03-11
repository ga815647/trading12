FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agents/ ./agents/
COPY config/ ./config/
COPY data/*.py ./data/
COPY engine/ ./engine/
COPY README.md .

CMD ["python", "engine/run_daily_scan.py"]
