"""Tests for the default admin migration and the demo seeding command."""
import importlib
import os
from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from .models import User

# Migration modules start with a digit, so import them by name.
default_admin = importlib.import_module("news.migrations.0003_default_admin")

# Environment variables that would change the defaults under test.
OVERRIDES = ("DJANGO_ADMIN_USERNAME", "DJANGO_ADMIN_EMAIL",
             "DJANGO_ADMIN_PASSWORD", "NEWSROOM_DEMO_PASSWORD")


def clean_environment(**values):
    """Patch os.environ without the override variables, plus ``values``."""
    environment = {key: value for key, value in os.environ.items()
                   if key not in OVERRIDES}
    environment.update(values)
    return patch.dict(os.environ, environment, clear=True)


class DefaultAdminTests(TestCase):
    """The migration creates one safe, reusable administrator account."""

    def setUp(self):
        """Start without any admin account from the test database."""
        User.objects.filter(username="admin").delete()

    def run_migration(self):
        """Run the migration's function against the current models."""
        default_admin.create_default_admin(apps, None)

    @override_settings(DEBUG=True)
    def test_development_creates_default_superuser(self):
        """In development the documented admin login is created."""
        with clean_environment():
            self.run_migration()
        admin = User.objects.get(username="admin")
        self.assertTrue(admin.is_superuser and admin.is_staff)
        self.assertTrue(admin.check_password("Admin-pass-123"))
        self.assertTrue(admin.groups.filter(name="Reader").exists())

    @override_settings(DEBUG=True)
    def test_rerunning_never_changes_an_existing_password(self):
        """Running migrations again leaves a changed password alone."""
        with clean_environment():
            self.run_migration()
            admin = User.objects.get(username="admin")
            admin.set_password("Changed-pass-456")
            admin.save()
            self.run_migration()
        self.assertEqual(User.objects.filter(username="admin").count(), 1)
        admin.refresh_from_db()
        self.assertTrue(admin.check_password("Changed-pass-456"))

    @override_settings(DEBUG=False)
    def test_production_without_password_creates_nothing(self):
        """Fail-safe: no known password is ever created outside DEBUG."""
        with clean_environment():
            self.run_migration()
        self.assertFalse(User.objects.filter(username="admin").exists())

    @override_settings(DEBUG=False)
    def test_environment_password_is_used_when_supplied(self):
        """DJANGO_ADMIN_* variables override the default login."""
        with clean_environment(DJANGO_ADMIN_USERNAME="chief",
                               DJANGO_ADMIN_EMAIL="chief@example.com",
                               DJANGO_ADMIN_PASSWORD="Own-pass-789"):
            self.run_migration()
        chief = User.objects.get(username="chief")
        self.assertTrue(chief.check_password("Own-pass-789"))


class SeedDemoTests(TestCase):
    """The demo command works without configuration in development."""

    @override_settings(DEBUG=True)
    def test_development_uses_default_demo_password(self):
        """Demo users get the documented password when none is set."""
        with clean_environment():
            call_command("seed_demo", stdout=StringIO())
        for username in ("reader", "journalist", "editor"):
            user = User.objects.get(username=username)
            self.assertTrue(user.check_password("Demo-pass-123"))

    @override_settings(DEBUG=False)
    def test_production_requires_a_demo_password(self):
        """Fail: outside DEBUG the command refuses to use a default."""
        with clean_environment():
            with self.assertRaises(CommandError):
                call_command("seed_demo", stdout=StringIO())
