"""Token-authenticated article and newsletter REST API.

Every endpoint requires authentication (see ``REST_FRAMEWORK`` in
settings). Role checks happen in the ``perform_*`` hooks so the rules
match the HTML views through the shared ``news.access`` helpers.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.crypto import constant_time_compare
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import can_manage, subscribed_articles, visible_articles
from .models import ApprovalLog, Article, Newsletter, Publisher, User
from .serializers import (
    ArticleSerializer,
    NewsletterSerializer,
    PublisherSerializer,
    UserSerializer,
)
from .services import approve_article


class ArticleViewSet(viewsets.ModelViewSet):
    """CRUD for articles at ``/api/articles/``.

    * GET list: all approved articles.
    * GET detail: approved articles, own drafts, or drafts an editor
      oversees.
    * POST: journalists only.
    * PUT/PATCH/DELETE: the author journalist or a scoped editor.
    """

    serializer_class = ArticleSerializer

    def get_queryset(self):
        """Use the public list for listing, wider visibility for detail."""
        if self.action == "list":
            return Article.objects.filter(approved=True).select_related(
                "author", "publisher")
        return visible_articles(self.request.user)

    def perform_create(self, serializer):
        """Create a draft owned by the requesting journalist."""
        if self.request.user.role != User.Role.JOURNALIST:
            raise PermissionDenied("Only journalists can create articles.")
        serializer.save(author=self.request.user)

    def perform_update(self, serializer):
        """Allow updates only by the author or a scoped editor."""
        if not can_manage(self.request.user, serializer.instance):
            raise PermissionDenied("You cannot edit this article.")
        serializer.save()

    def perform_destroy(self, instance):
        """Allow deletion only by the author or a scoped editor."""
        if not can_manage(self.request.user, instance):
            raise PermissionDenied("You cannot delete this article.")
        instance.delete()

    @action(detail=False, methods=["get"])
    def subscribed(self, request):
        """GET ``/api/articles/subscribed/``: the reader's own feed."""
        if request.user.role != User.Role.READER:
            raise PermissionDenied("Subscriptions are available to readers.")
        page = self.paginate_queryset(subscribed_articles(request.user))
        return self.get_paginated_response(
            self.get_serializer(page, many=True).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):  # pylint: disable=unused-argument
        """POST ``/api/articles/<id>/approve/``: editor approval.

        DRF always passes ``pk`` to detail actions, so the parameter must
        stay even though ``get_object()`` reads it from ``self.kwargs``.
        """
        article = self.get_object()
        try:
            article = approve_article(article.pk, request.user)
        except DjangoPermissionDenied as exc:
            # Convert Django's exception into DRF's so the client gets 403.
            raise PermissionDenied(str(exc)) from exc
        return Response(self.get_serializer(article).data)


class NewsletterViewSet(viewsets.ModelViewSet):
    """CRUD for newsletters at ``/api/newsletters/``.

    Any authenticated user can read. Journalists and editors can create;
    only the author or a scoped editor can change or delete.
    """

    queryset = Newsletter.objects.select_related("author", "publisher").all()
    serializer_class = NewsletterSerializer

    def perform_create(self, serializer):
        """Create an issue owned by the requesting journalist/editor."""
        user = self.request.user
        if user.role != User.Role.JOURNALIST and not user.is_editor:
            raise PermissionDenied(
                "Only journalists and editors can curate issues.")
        serializer.save(author=user)

    def perform_update(self, serializer):
        """Allow updates only by the author or a scoped editor."""
        if not can_manage(self.request.user, serializer.instance):
            raise PermissionDenied("You cannot edit this newsletter.")
        serializer.save()

    def perform_destroy(self, instance):
        """Allow deletion only by the author or a scoped editor."""
        if not can_manage(self.request.user, instance):
            raise PermissionDenied("You cannot delete this newsletter.")
        instance.delete()


class PublisherViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only list of publishers, so clients can pick subscriptions."""

    queryset = Publisher.objects.prefetch_related(
        "editors", "journalists").all()
    serializer_class = PublisherSerializer


class JournalistViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only list of active journalists (public profile fields only)."""

    queryset = User.objects.filter(role=User.Role.JOURNALIST, is_active=True)
    serializer_class = UserSerializer


class ApprovalKeyPermission(permissions.BasePermission):
    """Allow a request only if it carries the shared integration key."""

    def has_permission(self, request, view):
        """Compare the ``X-Approval-Key`` header in constant time."""
        key = request.headers.get("X-Approval-Key", "")
        return bool(settings.APPROVAL_API_KEY) and constant_time_compare(
            key, settings.APPROVAL_API_KEY)


class ApprovalLogView(APIView):
    """POST ``/api/approved/``: log an approved article.

    This stands in for an external system. The approval service calls it
    with ``requests``, and it records a receipt for that revision.
    """

    # The shared key replaces user authentication for this endpoint.
    authentication_classes = []
    permission_classes = [ApprovalKeyPermission]

    def post(self, request):
        """Validate the payload and store one receipt per revision."""
        article_id = request.data.get("article")
        revision = request.data.get("revision")
        # Defensive check: both values must be positive integers (bool and
        # numeric strings are rejected because type() must be exactly int).
        if (type(article_id) is not int or article_id < 1
                or type(revision) is not int or revision < 1):
            return Response({
                "detail": "Positive article/revision integers required."},
                status=status.HTTP_400_BAD_REQUEST)
        # Only the current approved revision can be logged.
        article = get_object_or_404(
            Article, Q(pk=article_id), approved=True,
            revision=revision)
        # get_or_create makes a repeated call harmless (200 instead of 201).
        receipt, created = ApprovalLog.objects.get_or_create(
            article=article, revision=revision,
            defaults={"title": article.title}
        )
        return Response({"id": receipt.pk, "article": article.pk,
                         "revision": revision}, status=201 if created else 200)
