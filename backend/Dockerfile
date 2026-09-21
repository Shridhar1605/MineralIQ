# Build context is the repository root (see docker-compose.yml: context: .).
# The image mirrors the repo layout under /srv so that the path helpers in
# main.py (parents[2]) and search/store.py (parents[3]) resolve to /srv,
# exactly as they resolve to the repo root when running locally.
FROM python:3.11-slim

WORKDIR /srv
COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

COPY backend/app /srv/backend/app
COPY fixtures    /srv/fixtures
COPY taxonomy    /srv/taxonomy
RUN mkdir -p /srv/data

# Modules import each other as top level (from alerts.store import ...), the
# same way tests/conftest.py puts backend/app on sys.path.
ENV PYTHONPATH=/srv/backend/app
ENV PYTHONUNBUFFERED=1
WORKDIR /srv/backend/app

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
