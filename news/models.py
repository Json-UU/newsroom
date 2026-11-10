"""Normalised news, subscription and integration models.

The schema is in third normal form: each fact (an author, a publisher, a
subscription, a delivery receipt) is stored once and referenced by key.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class User(AbstractUser):
    """Custom user with a newsroom role and reader subscriptions.

    The ``role`` decides which Django group the user belongs to (kept in
    sync by ``news.signals``). Reader-only fields are the two subscription
    relations; journalist-only fields are the reverse ``articles`` and
    ``newsletters`` relations. The properties below expose each set of
    fields and return ``None`` when the user has a different role, as the
    brief requires.
    """

    class Role(models.TextChoices):
        """The three roles defined by the brief."""

        READER = "reader", "Reader"
        EDITOR = "editor", "Editor"
        JOURNALIST = "journalist", "Journalist"

    # Unique email so subscribers can be notified without duplicates.
    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=12, choices=Role.choices, default=Role.READER
    )
    # Reader field: publishers this reader follows.
    publisher_subscriptions = models.ManyToManyField(
        "Publisher", blank=True, related_name="subscribers"
    )
    # Reader field: journalists this reader follows. Not symmetrical,
    # because following a journalist does not make them follow you back.
    journalist_subscriptions = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="subscribers",
        limit_choices_to={"role": "journalist"},
    )

    @property
    def reader_publishers(self):
        """Return subscribed publishers for readers, otherwise ``None``."""
        return (self.publisher_subscriptions.all()
                if self.role == self.Role.READER else None)

    @property
    def reader_journalists(self):
        """Return subscribed journalists for readers, otherwise ``None``."""
        return (self.journalist_subscriptions.all()
                if self.role == self.Role.READER else None)

    @property
    def independent_articles(self):
        """Return a journalist's independent articles, otherwise ``None``.

        Independent articles are those with no publisher.
        """
        return (self.articles.filter(publisher__isnull=True)
                if self.role == self.Role.JOURNALIST else None)

    @property
    def independent_newsletters(self):
        """Return a journalist's independent newsletters, else ``None``."""
        return (self.newsletters.filter(publisher__isnull=True)
                if self.role == self.Role.JOURNALIST else None)

    @property
    def is_editor(self):
        """True if the user has the editor role or is in the Editor group.

        Checking the group as well means an administrator can grant editor
        rights through Django's group admin.
        """
        return self.role == self.Role.EDITOR or (
            self.is_authenticated and self.groups.filter(
                name="Editor").exists())


class Publisher(models.Model):
    """A curated publication with its own editors and journalists."""

    name = models.CharField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    # A publisher can have many editors, and an editor many publishers.
    editors = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="edited_publishers",
        limit_choices_to={"role": "editor"},
    )
    # Journalists affiliated with this publisher (they may have several).
    journalists = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True,
        related_name="journalist_publishers",
        limit_choices_to={"role": "journalist"},
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        """Show the publisher's name in forms and the admin."""
        return self.name


class Article(models.Model):
    """A news story written by a journalist.

    ``publisher`` is optional: an empty publisher means an independent
    article by the journalist, otherwise it is publisher content. Only an
    editor may set ``approved``; editing a story increments ``revision``
    and sends it back for review.
    """

    title = models.CharField(max_length=220)
    content = models.TextField()
    # PROTECT stops a journalist with published work from being deleted.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="articles", limit_choices_to={"role": "journalist"},
    )
    publisher = models.ForeignKey(
        Publisher, null=True, blank=True, on_delete=models.PROTECT,
        related_name="articles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Indexed because almost every public query filters on approval.
    approved = models.BooleanField(default=False, db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="reviewed_articles",
    )
    # Bumped on every content change so each approval is tracked separately.
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        """Show the article's title in forms and the admin."""
        return self.title

    def clean(self):
        """Check the author is a journalist who belongs to the publisher."""
        if self.author_id and self.author.role != User.Role.JOURNALIST:
            raise ValidationError("An article author must be a journalist.")
        if (self.publisher_id and self.author_id
                and not self.publisher.journalists.filter(
                    pk=self.author_id).exists()):
            raise ValidationError("The author must belong to the publisher.")


class Newsletter(models.Model):
    """A curated collection of approved articles.

    Journalists and editors create newsletters; readers can view them.
    """

    title = models.CharField(max_length=220)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="newsletters",
    )
    publisher = models.ForeignKey(
        Publisher, null=True, blank=True, on_delete=models.PROTECT,
        related_name="newsletters",
    )
    articles = models.ManyToManyField(Article, related_name="newsletters")

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        """Show the newsletter's title in forms and the admin."""
        return self.title


class ApprovalDelivery(models.Model):
    """Tracks notification progress for one approved article revision.

    Email and the API log are recorded separately so a failed channel can
    be retried without repeating the one that succeeded.
    """

    article = models.ForeignKey(
        Article, on_delete=models.CASCADE, related_name="deliveries"
    )
    revision = models.PositiveIntegerField()
    email_sent = models.BooleanField(default=False)
    api_logged = models.BooleanField(default=False)
    last_error = models.TextField(blank=True)
    # Short lease that stops two requests delivering at the same time.
    processing_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["article", "revision"], name="unique_approval_delivery"
        )]


class ApprovalLog(models.Model):
    """Receipt written by the ``/api/approved/`` endpoint.

    One row per approved revision; the unique constraint makes the
    endpoint safe to call more than once.
    """

    article = models.ForeignKey(Article, on_delete=models.CASCADE)
    revision = models.PositiveIntegerField()
    received_at = models.DateTimeField(auto_now_add=True)
    # Title copied at approval time, as shared with the "external" system.
    title = models.CharField(max_length=220)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["article", "revision"], name="unique_approval_receipt"
        )]
