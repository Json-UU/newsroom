# The Newsroom: Django news platform.
FROM python:3.12-slim

# Print logs immediately and skip writing .pyc files.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# mysqlclient (the MariaDB driver) is compiled from source, so it needs a
# compiler and the MariaDB client headers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so this layer is cached between code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as an unprivileged user that owns /app (it holds the SQLite file).
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# Demo defaults: SQLite inside the container and development mode, so a
# single "docker run" works with the demo logins. Override these with -e
# (for example MARIADB_* settings without DJANGO_USE_SQLITE) for real use.
ENV DJANGO_USE_SQLITE=1 \
    DJANGO_DEBUG=1 \
    DJANGO_ALLOWED_HOSTS=*

EXPOSE 8000

# Create the tables, load demo content (safe to repeat), then serve.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_demo && python manage.py runserver 0.0.0.0:8000"]
