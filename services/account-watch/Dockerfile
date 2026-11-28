FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY account_watch ./account_watch

RUN useradd --create-home appuser && mkdir /app/data && chown appuser /app/data
USER appuser

ENV PYTHONPATH=/app
# SQLite in /app/data by default; the Helm chart sets POSTGRES_HOST to use the cluster's Postgres.
ENV ACCOUNT_WATCH_DATA=/app/data
EXPOSE 8501
CMD ["streamlit", "run", "account_watch/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
