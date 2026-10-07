# Single image for all three services; the command is overridden per service.
#   web       -> gunicorn (default CMD below)
#   worker    -> python web/worker.py
#   scheduler -> python web/scheduler.py
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/web

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY web/ web/

EXPOSE 8000

# ${PORT} is injected by Railway; 8000 is the local/compose default.
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
