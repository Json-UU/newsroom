"""Create a default administrator so a fresh install can sign in at once.

The account is created only if it does not already exist, so running
migrations again never changes an existing password. Outside development
(``DJANGO_DEBUG=0``) the built-in password is never used: an account is
created only when ``DJANGO_ADMIN_PASSWORD`` is set.
"""
import os

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations

# Development login, documented in README.md. Change it after signing in.
DEFAULT_USERNAME = "admin"
DEFAULT_EMAIL = "admin@example.com"
DEFAULT_PASSWORD = "Admin-pass-123"


def create_default_admin(apps, schema_editor):
    """Create the superuser described by the environment or the defaults."""
    User = apps.get_model("news", "User")
    Group = apps.get_model("auth", "Group")
    username = os.environ.get("DJANGO_ADMIN_USERNAME", DEFAULT_USERNAME)
    email = os.environ.get("DJANGO_ADMIN_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("DJANGO_ADMIN_PASSWORD")
    if not password:
        if not settings.DEBUG:
            # Never create a known password on a non-development install.
            return
        password = DEFAULT_PASSWORD
    # Leave any existing account (same username or email) untouched.
    if User.objects.filter(username=username).exists() or \
            User.objects.filter(email=email).exists():
        return
    # Historical models have no set_password(), so hash it directly.
    admin = User.objects.create(
        username=username, email=email, password=make_password(password),
        is_staff=True, is_superuser=True, role="reader",
    )
    # Signals do not run for historical models, so add the role group here.
    # Its permissions are assigned by the post_migrate signal afterwards.
    group, _ = Group.objects.get_or_create(name="Reader")
    admin.groups.add(group)


class Migration(migrations.Migration):
    """Data migration that adds the default administrator account."""

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("news", "0002_approvaldelivery_processing_until"),
    ]

    operations = [
        # Reversing is a no-op so rolling back never deletes a real account.
        migrations.RunPython(create_default_admin, migrations.RunPython.noop),
    ]
