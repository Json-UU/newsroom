"""Provision role groups and keep inapplicable subscription tables empty.

These signals handle user roles and groups only. Article approval does
not use signals; it follows option 2 of the brief (see ``services.py``).
"""
from django.contrib.auth.models import Group, Permission
from django.db.models.signals import (
    m2m_changed, post_migrate, post_save, pre_save,
)
from django.dispatch import receiver

from .models import User

# Maps each user role to the name of its Django group.
ROLE_NAMES = {"reader": "Reader", "editor": "Editor",
              "journalist": "Journalist"}


@receiver(post_migrate)
def provision_groups(sender, **kwargs):
    """Create the three role groups and give them their permissions.

    * Reader: view articles and newsletters.
    * Editor: view, change and delete articles and newsletters, plus add
      newsletters.
    * Journalist: add, view, change and delete articles and newsletters.
    """
    # post_migrate fires once per app; only run for this app.
    if sender.name != "news":
        return
    for role, name in ROLE_NAMES.items():
        group, _ = Group.objects.get_or_create(name=name)
        actions = {"view"}
        if role in {"editor", "journalist"}:
            actions.update({"change", "delete"})
            # The brief explicitly allows editors to create newsletters.
            codes = {"add_newsletter"}
        else:
            codes = set()
        if role == "journalist":
            codes.add("add_article")
        # Build codenames such as "view_article" and "delete_newsletter".
        codes.update(f"{action}_{model}" for action in actions
                     for model in ("article", "newsletter"))
        group.permissions.set(Permission.objects.filter(
            content_type__app_label="news", codename__in=codes
        ))


@receiver(pre_save, sender=User)
def remember_role(sender, instance, raw=False, **kwargs):
    """Store the user's role before saving, to detect role changes."""
    # raw is True while loading fixtures; skip database lookups then.
    if not raw:
        instance._previous_role = User.objects.filter(
            pk=instance.pk).values_list(
            "role", flat=True).first()


@receiver(post_save, sender=User)
def synchronise_role(sender, instance, raw=False, created=False, **kwargs):
    """Put the user in the group for their role and clear other fields.

    Fields that belong to another role are emptied, which is how the
    "assign the other role's fields None" requirement is enforced in the
    database (a many-to-many field cannot store None itself).
    """
    if raw:
        return
    name = ROLE_NAMES[instance.role]
    # Remove other role groups only when the role is new or has changed.
    if created or getattr(instance, "_previous_role", None) != instance.role:
        instance.groups.remove(*Group.objects.filter(
            name__in=set(ROLE_NAMES.values()) - {name}
        ))
    group, _ = Group.objects.get_or_create(name=name)
    instance.groups.add(group)
    # Only readers keep subscriptions.
    if instance.role != User.Role.READER:
        instance.publisher_subscriptions.clear()
        instance.journalist_subscriptions.clear()
    # Only journalists can have followers.
    if instance.role != User.Role.JOURNALIST:
        instance.subscribers.clear()


@receiver(m2m_changed, sender=User.publisher_subscriptions.through)
@receiver(m2m_changed, sender=User.journalist_subscriptions.through)
def validate_subscriptions(
        sender,
        instance,
        action,
        reverse,
        pk_set,
        **kwargs):
    """Reject subscriptions that break the role rules.

    Only readers may subscribe, and journalist subscriptions must point at
    journalists. Both directions of the relation are checked.
    """
    # Only validate before rows are added; removals are always allowed.
    if action != "pre_add":
        return
    from django.core.exceptions import ValidationError

    if reverse:
        # Added from the target's side, e.g. publisher.subscribers.add(...)
        readers = User.objects.filter(pk__in=pk_set)
        if readers.exclude(role=User.Role.READER).exists():
            raise ValidationError("Only readers can subscribe.")
        if isinstance(
                instance,
                User) and instance.role != User.Role.JOURNALIST:
            raise ValidationError("Subscriptions must target journalists.")
    else:
        # Added from the reader's side, e.g. reader.*_subscriptions.add(...)
        if instance.role != User.Role.READER:
            raise ValidationError("Only readers can subscribe.")
        if sender == User.journalist_subscriptions.through:
            if User.objects.filter(pk__in=pk_set).exclude(
                    role=User.Role.JOURNALIST).exists():
                raise ValidationError("Subscriptions must target journalists.")
