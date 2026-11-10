"""Explicit approval and post-commit integration (brief option 2).

Instead of a signal, the approval view calls ``approve_article``. After
the database commit, ``dispatch_approval`` emails subscribers and POSTs
the approved article to our own ``/api/approved/`` endpoint.
"""
import logging
from datetime import timedelta
from functools import partial

import requests
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mass_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .access import can_manage
from .models import ApprovalDelivery, Article, User

logger = logging.getLogger(__name__)


def approve_article(article_id, editor):
    """Approve an article and schedule notifications after commit.

    Raises ``PermissionDenied`` unless ``editor`` is an editor who
    oversees the article and did not write it.
    """
    with transaction.atomic():
        # Lock the row so a simultaneous edit cannot slip in mid-approval.
        article = Article.objects.select_for_update().get(pk=article_id)
        if (not editor.is_editor or not can_manage(editor, article)
                or article.author_id == editor.pk):
            raise PermissionDenied(
                "An authorised independent editor is needed.")
        article.approved = True
        article.approved_by = editor
        article.save(update_fields=["approved", "approved_by"])
        # One delivery record per revision; approving again reuses it,
        # which turns a second click into a retry of failed channels.
        delivery, _ = ApprovalDelivery.objects.get_or_create(
            article=article, revision=article.revision
        )
        # Notify only if the transaction commits, so a rollback never
        # emails subscribers about an article that was not approved.
        transaction.on_commit(partial(dispatch_approval, delivery.pk))
    return article


def dispatch_approval(delivery_id):
    """Email subscribers and log the article to ``/api/approved/``.

    Each channel is attempted only if it has not already succeeded.
    Failures are logged and stored on the delivery so an editor can retry
    from the article page; they never undo the approval itself.
    """
    # A short atomic lease prevents concurrent retries without holding a DB
    # transaction open while the HTTP endpoint writes to this same database.
    now = timezone.now()
    claimed = ApprovalDelivery.objects.filter(pk=delivery_id).filter(
        Q(processing_until__isnull=True) | Q(processing_until__lt=now)
    ).update(processing_until=now + timedelta(minutes=2))
    if not claimed:
        # Another request is already delivering this revision.
        return
    delivery = ApprovalDelivery.objects.get(
        pk=delivery_id
    )
    article = Article.objects.select_related("author").get(
        pk=delivery.article_id
    )
    # Skip if the article was edited (new revision) or unapproved since.
    if not article.approved or article.revision != delivery.revision:
        delivery.processing_until = None
        delivery.save(update_fields=["processing_until"])
        return
    errors = []
    if not delivery.email_sent:
        # Subscribers of the journalist, plus the publisher if there is one.
        subscriptions = Q(journalist_subscriptions=article.author)
        if article.publisher_id:
            subscriptions |= Q(publisher_subscriptions=article.publisher_id)
        # distinct() ensures a reader following both gets one email.
        subscribers = User.objects.filter(
            role=User.Role.READER, is_active=True
        ).filter(subscriptions).exclude(email="").values_list(
            "email", flat=True).distinct()
        body = f"{article.title}\n\n{article.content}"
        # One message per recipient so addresses are never shared.
        emails = [(article.title, body, settings.DEFAULT_FROM_EMAIL, [email])
                  for email in subscribers]
        try:
            send_mass_mail(emails, fail_silently=False)
            delivery.email_sent = True
        except Exception:
            # Any mail backend error (SMTP, auth, network) is recoverable
            # through a retry, so record it rather than crash the request.
            logger.exception("Approval email failed: %s", article.pk)
            errors.append("Email failed; check email settings and retry.")
    if not delivery.api_logged:
        try:
            if not settings.APPROVAL_API_KEY:
                raise ValueError("APPROVAL_API_KEY is not configured")
            response = requests.post(
                settings.APPROVAL_API_URL,
                json={"article": article.pk, "revision": article.revision},
                headers={"X-Approval-Key": settings.APPROVAL_API_KEY},
                timeout=5,
                allow_redirects=False,
            )
            # Treat 4xx/5xx and any other unexpected status as failure.
            response.raise_for_status()
            if response.status_code not in {200, 201}:
                raise ValueError("Approval endpoint did not accept the log")
            delivery.api_logged = True
        except (requests.RequestException, ValueError):
            logger.exception("Approval API failed: %s", article.pk)
            errors.append("API log failed; check integration and retry.")
    # Save the outcome and release the lease.
    delivery.last_error = " ".join(errors)
    delivery.processing_until = None
    delivery.save(update_fields=["email_sent", "api_logged", "last_error",
                                 "processing_until"])


def save_article_changes(article, changes):
    """Serialise edits with approval and reset review on content changes.

    If any field actually changes, the article is unapproved and its
    revision is incremented, so it disappears from public pages until an
    editor approves it again. Returns the saved article.
    """
    with transaction.atomic():
        # Lock the row so the edit cannot race with an approval.
        locked = Article.objects.select_for_update().get(pk=article.pk)
        changed = any(getattr(locked, key) != value
                      for key, value in changes.items())
        if changed:
            for key, value in changes.items():
                setattr(locked, key, value)
            locked.approved = False
            locked.approved_by = None
            locked.revision += 1
            # Run model validation (author/publisher rules) before saving.
            locked.full_clean()
            locked.save()
    return locked


def send_newsletter(issue, user):
    """Email a curated issue, excluding stories returned to draft.

    Raises ``PermissionDenied`` if ``user`` cannot manage the issue and
    ``ValueError`` if it has no approved stories. Returns the number of
    recipients.
    """
    if not can_manage(user, issue):
        raise PermissionDenied("You cannot send this newsletter.")
    articles = list(issue.articles.filter(approved=True))
    if not articles:
        raise ValueError("Add at least one approved story before sending.")
    # Recipients follow the issue's author or its publisher.
    subscriptions = Q(journalist_subscriptions=issue.author)
    if issue.publisher_id:
        subscriptions |= Q(publisher_subscriptions=issue.publisher_id)
    recipients = list(User.objects.filter(
        role=User.Role.READER, is_active=True
    ).filter(subscriptions).exclude(email="").values_list(
        "email", flat=True).distinct())
    body = f"{issue.title}\n\n{issue.description}\n\n" + "\n\n".join(
        f"{article.title}\n{article.content}" for article in articles
    )
    send_mass_mail([
        (issue.title, body, settings.DEFAULT_FROM_EMAIL, [email])
        for email in recipients
    ], fail_silently=False)
    return len(recipients)
