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

    :param user: The editor whose scope is being built.
    :type user: news.models.User
    :returns: A filter matching independent content and content from the
        editor's publishers.
    :rtype: django.db.models.Q
    """
    return Q(publisher__isnull=True) | Q(publisher__editors=user)


def visible_articles(user):
    """Return the articles ``user`` may open.

    Everyone sees approved articles. Authors also see their own drafts,
    and editors see drafts within their editorial scope.

    :param user: The current user, who may be anonymous.
    :type user: news.models.User or django.contrib.auth.models.AnonymousUser
    :returns: The articles the user is allowed to view.
    :rtype: django.db.models.QuerySet[news.models.Article]
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

    :param user: The current user, who may be anonymous.
    :type user: news.models.User or django.contrib.auth.models.AnonymousUser
    :param item: The article or newsletter being checked.
    :type item: news.models.Article or news.models.Newsletter
    :returns: ``True`` if the user may edit or delete the item.
    :rtype: bool
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

    :param user: The reader whose subscriptions are used.
    :type user: news.models.User
    :returns: Approved articles from followed publishers and journalists.
    :rtype: django.db.models.QuerySet[news.models.Article]
    """
    return Article.objects.filter(approved=True).filter(
        Q(publisher__in=user.publisher_subscriptions.all())
        | Q(author__in=user.journalist_subscriptions.all())
    ).select_related("author", "publisher").distinct()
