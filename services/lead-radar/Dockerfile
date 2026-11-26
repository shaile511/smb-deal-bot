FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY lead_radar ./lead_radar

# Run as a non-root user, as most Kubernetes clusters expect.
RUN useradd --create-home appuser
USER appuser

ENV PYTHONPATH=/app
EXPOSE 8501
CMD ["streamlit", "run", "lead_radar/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
