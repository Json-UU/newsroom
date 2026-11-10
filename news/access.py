"""Shared object-level access rules for the HTML views and the API.

Keeping these rules in one module means the website and the REST API
always agree on who can see or change a piece of content.
"""
from django.db.models import Q

from .models import Article, User


def editorial_scope(user):
    """Return a filter for the content an editor is responsible for.

    Editors oversee all independent content plus the content of any
    publisher they edit for.
    """
    return Q(publisher__isnull=True) | Q(publisher__editors=user)


def visible_articles(user):
    """Return the articles ``user`` may open.

    Everyone sees approved articles. Authors also see their own drafts,
    and editors see drafts within their editorial scope.
    """
    articles = Article.objects.select_related("author", "publisher")
    if not user.is_authenticated:
        return articles.filter(approved=True)
    visibility = Q(approved=True) | Q(author=user)
    if user.is_editor:
        visibility |= editorial_scope(user)
    # distinct() removes duplicate rows from the publisher/editor join.
    return articles.filter(visibility).distinct()


def can_manage(user, item):
    """Return True if ``user`` may edit or delete an article/newsletter.

    Editors manage independent items and items from their publishers.
    Journalists manage only items they wrote. Readers manage nothing.
    """
    if not user.is_authenticated:
        return False
    if user.is_editor:
        return (item.publisher_id is None
                or item.publisher.editors.filter(pk=user.pk).exists())
    return user.role == User.Role.JOURNALIST and item.author_id == user.pk


def subscribed_articles(user):
    """Return approved articles from the reader's subscriptions.

    An article matches if its publisher or its journalist is followed;
    distinct() stops an article matching both from appearing twice.
    """
    return Article.objects.filter(approved=True).filter(
        Q(publisher__in=user.publisher_subscriptions.all())
        | Q(author__in=user.journalist_subscriptions.all())
    ).select_related("author", "publisher").distinct()
