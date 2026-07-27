FROM python:3.12-slim

# tzdata so the OS-level TZ env resolves (slim images omit it → TZ is ignored
# and log timestamps stay UTC). App scheduling uses pytz and is unaffected, but
# container/log clock alignment needs this.
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
