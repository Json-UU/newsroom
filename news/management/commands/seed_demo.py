"""Create a repeatable, explicitly local demonstration dataset."""
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from news.models import Article, Newsletter, Publisher, User

# Development password for the demo users, documented in README.md.
DEFAULT_DEMO_PASSWORD = "Demo-pass-123"


class Command(BaseCommand):
    """``python manage.py seed_demo``: create demo users and content."""

    help = "Seed local demo content (password: NEWSROOM_DEMO_PASSWORD)."

    def handle(self, *args, **options):
        """Create one user per role, a publisher, articles and a newsletter.

        get_or_create makes the command safe to run more than once.
        """
        # NEWSROOM_DEMO_PASSWORD overrides the default. Outside development
        # a password must be supplied, so no known password is deployed.
        password = os.environ.get("NEWSROOM_DEMO_PASSWORD")
        if not password:
            if not settings.DEBUG:
                raise CommandError(
                    "Set NEWSROOM_DEMO_PASSWORD before seeding.")
            password = DEFAULT_DEMO_PASSWORD
        users = {}
        # Existing users keep their current password.
        for role in ("reader", "journalist", "editor"):
            user, created = User.objects.get_or_create(
                username=role, defaults={"email": f"{role}@example.com",
                                         "role": role})
            if created:
                user.set_password(password)
                user.save()
            users[role] = user
        publisher, _ = Publisher.objects.get_or_create(
            name="The Cape Observer", defaults={
                "description": "Local perspective. A wider world."})
        publisher.journalists.add(users["journalist"])
        publisher.editors.add(users["editor"])
        headlines = [
            ("A greener future starts on our doorstep",
             "Across the Cape, community gardens are turning unused "
             "spaces "
             "into places of possibility. Volunteers are growing fresh food, "
             "sharing practical skills and creating "
             "stronger neighbourhoods.\n\n"
             "The people behind these gardens say the harvest is only part "
             "of the story. Working together is building connections that "
             "last well beyond a single growing season."),
            ("The small businesses bringing new life to the high street",
             "Independent shops are finding new ways to connect with their "
             "communities. From repair workshops to neighbourhood markets, "
             "local entrepreneurs are making the everyday feel personal.\n\n"
             "Their stories offer a thoughtful reminder that a thriving "
             "high street begins with the people who call it home."),
            ("Why our libraries still matter",
             "A library is much more than a collection of books. It is a "
             "quiet place to study, a doorway to new ideas and a meeting "
             "point for people of every generation.\n\n"
             "As digital services expand, librarians are helping readers "
             "navigate information with confidence and curiosity."),
        ]
        articles = []
        # Two publisher stories and one independent story, created as
        # already approved fixtures (no notifications are sent).
        for index, (title, content) in enumerate(headlines):
            article, _ = Article.objects.get_or_create(
                title=title, author=users["journalist"], defaults={
                    "content": content, "approved": True,
                    "approved_by": users["editor"],
                    "publisher": publisher if index < 2 else None,
                })
            articles.append(article)
        # A draft left for the editor to approve during the demo.
        Article.objects.get_or_create(
            title="Tomorrow's transport: a city in motion",
            author=users["journalist"], defaults={
                "publisher": publisher,
                "content": "A draft report exploring better public transport. "
                           "This story is awaiting editorial review.",
            })
        issue, _ = Newsletter.objects.get_or_create(
            title="The weekend perspective", author=users["journalist"],
            defaults={"description": "Three stories to slow down with this "
                      "weekend. Community, creativity and a changing Cape.",
                      "publisher": publisher})
        issue.articles.set(articles)
        users["reader"].publisher_subscriptions.add(publisher)
        self.stdout.write(self.style.SUCCESS(
            "Demo ready: reader, journalist, editor. "
            "Existing passwords unchanged."
        ))
