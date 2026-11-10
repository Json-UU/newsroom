"""DRF serializers for the User, Publisher, Article and Newsletter models."""
from rest_framework import serializers

from .forms import publisher_choices
from .models import Article, Newsletter, Publisher, User
from .services import save_article_changes


class UserSerializer(serializers.ModelSerializer):
    """Public user profile; email and subscriptions are not exposed."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "role"]


class PublisherSerializer(serializers.ModelSerializer):
    """Publisher with the IDs of its editors and journalists."""

    class Meta:
        model = Publisher
        fields = ["id", "name", "description", "editors", "journalists"]


class ArticleSerializer(serializers.ModelSerializer):
    """Article with readable author/publisher names.

    ``author``, ``approved`` and ``revision`` are controlled by the
    server, so clients cannot approve their own work.
    """

    author_name = serializers.CharField(
        source="author.username", read_only=True)
    # Independent articles have no publisher, so show "Independent".
    publisher_name = serializers.CharField(
        source="publisher.name", read_only=True, default="Independent"
    )

    class Meta:
        model = Article
        fields = ["id", "title", "content", "author", "author_name",
                  "publisher", "publisher_name", "created_at", "approved",
                  "revision"]
        read_only_fields = ["author", "created_at", "approved", "revision"]

    def validate(self, attrs):
        """Reject attempts to set protected fields or a foreign publisher."""
        # Read-only fields are silently ignored by DRF; refuse them
        # explicitly so a client knows approval cannot be spoofed.
        if "approved" in self.initial_data or "author" in self.initial_data:
            raise serializers.ValidationError(
                "Author is assigned automatically; use editor approval."
            )
        publisher = attrs.get("publisher")
        if self.instance and "publisher" in attrs:
            # Updates may not move an article to another publisher.
            if publisher != self.instance.publisher:
                raise serializers.ValidationError(
                    "Publisher cannot be reassigned after submission."
                )
        elif publisher and not publisher_choices(
                self.context["request"].user).filter(pk=publisher.pk).exists():
            # New articles may only use publishers the author belongs to.
            raise serializers.ValidationError(
                "You do not belong to this publisher.")
        return attrs

    def update(self, instance, validated_data):
        """Save through the service so the article returns to review."""
        return save_article_changes(instance, validated_data)


class NewsletterSerializer(serializers.ModelSerializer):
    """Newsletter whose ``articles`` must all be approved."""

    articles = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Article.objects.filter(approved=True)
    )

    class Meta:
        model = Newsletter
        fields = ["id", "title", "description", "created_at", "author",
                  "publisher", "articles"]
        read_only_fields = ["author", "created_at"]

    def validate_publisher(self, publisher):
        """Keep the publisher fixed and limited to the user's own."""
        if self.instance and publisher != self.instance.publisher:
            raise serializers.ValidationError(
                "Publisher cannot be reassigned.")
        choices = publisher_choices(self.context["request"].user)
        if (not self.instance and publisher
                and not choices.filter(pk=publisher.pk).exists()):
            raise serializers.ValidationError(
                "You do not belong to this publisher.")
        return publisher

    def to_representation(self, instance):
        """List only the articles that are still approved."""
        data = super().to_representation(instance)
        # A previously selected story can later return to draft.
        data["articles"] = list(instance.articles.filter(
            approved=True).values_list("pk", flat=True))
        return data
