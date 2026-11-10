"""Prepare and run the local development server: python run.py."""
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


def start_local_database():
    """Start an optional portable MariaDB instance configured in .env."""
    server = os.environ.get("MARIADB_SERVER")
    config = os.environ.get("MARIADB_CONFIG")
    if not server or not config or os.environ.get("DJANGO_USE_SQLITE") == "1":
        return
    host = os.environ.get("MARIADB_HOST", "127.0.0.1")
    port = int(os.environ.get("MARIADB_PORT", "3306"))
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Portable MariaDB must use a local host address.")
    try:
        with socket.create_connection((host, port), timeout=1):
            return
    except OSError:
        pass
    print("Starting local MariaDB...")
    process = subprocess.Popen(
        [server, f"--defaults-file={config}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )
    for _ in range(80):
        if process.poll() is not None:
            break
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.25)
    raise OSError("MariaDB did not start. Check its log and MARIADB_CONFIG.")


def create_database_if_missing():
    """Create the MariaDB database named in .env if it does not exist.

    This removes the manual CREATE DATABASE step. The configured MariaDB
    user needs permission to create databases (the root user has it).
    """
    if os.environ.get("DJANGO_USE_SQLITE") == "1":
        return
    import MySQLdb

    name = os.environ.get("MARIADB_DATABASE", "newsroom")
    # The name is placed in SQL, so allow only letters, digits and "_".
    if not re.fullmatch(r"\w{1,64}", name, flags=re.ASCII):
        raise ValueError("MARIADB_DATABASE may contain only letters, digits "
                         "and underscores.")
    connection = MySQLdb.connect(
        host=os.environ.get("MARIADB_HOST", "127.0.0.1"),
        port=int(os.environ.get("MARIADB_PORT", "3306")),
        user=os.environ.get("MARIADB_USER", "root"),
        password=os.environ.get("MARIADB_PASSWORD", ""),
        connect_timeout=5,
    )
    try:
        connection.cursor().execute(
            f"CREATE DATABASE IF NOT EXISTS `{name}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    finally:
        connection.close()


def main():
    """Load local settings, migrate the database, and serve the app."""
    project_dir = Path(__file__).resolve().parent
    os.chdir(project_dir)
    load_dotenv(project_dir / ".env")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    # Both HTTP requests run in this process, so a fresh local integration
    # key works without requiring a user to create one on every launch.
    if os.environ.get("DJANGO_DEBUG", "1") == "1":
        os.environ.setdefault("DJANGO_SECRET_KEY", secrets.token_urlsafe(48))
        os.environ.setdefault("APPROVAL_API_KEY", secrets.token_urlsafe(32))
        os.environ.setdefault(
            "APPROVAL_API_URL", "http://127.0.0.1:8000/api/approved/")

    import django
    import MySQLdb
    from django.core.management import call_command
    from django.db import OperationalError

    try:
        start_local_database()
        create_database_if_missing()
        django.setup()
        # Creates the tables, role groups and the default admin account.
        call_command("migrate", interactive=False)
        # Load demo users and stories the first time only, so content a
        # user later deletes is not recreated on the next launch.
        from news.models import Article
        if not Article.objects.exists():
            call_command("seed_demo")
    except (OperationalError, MySQLdb.Error, OSError, ValueError) as exc:
        print(
            "\nCould not connect to the database. Check MariaDB is running "
            "and that MARIADB_USER and MARIADB_PASSWORD in .env are "
            "correct.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print("\nDefault logins (unless overridden in .env):")
    print("  admin / Admin-pass-123  (site admin at /admin/)")
    print("  reader, journalist, editor / Demo-pass-123")
    print("\nOpen http://127.0.0.1:8000/ in your browser.")
    print("Press Ctrl+C to stop.\n")
    # Threading is needed for the approval POST back to our own API.
    call_command("runserver", "127.0.0.1:8000", use_reloader=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
