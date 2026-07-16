FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# config.py derives the env-file path from Path(__file__).parents[3], so the app
# must live at least four directories deep (mirroring its repo location) or that
# lookup raises IndexError. Compose still injects the real environment directly.
WORKDIR /opt/nafea/backend

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY app ./app

EXPOSE 8001

# Linux containers use an epoll event loop, so async psycopg works without the
# Windows SelectorEventLoop workaround the host would otherwise need.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
