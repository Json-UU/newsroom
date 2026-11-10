"""Workflow/API regressions with token authentication and mocked HTTP."""
from unittest.mock import Mock, patch

import requests
from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import (
    ApprovalDelivery, ApprovalLog, Article, Newsletter, Publisher, User,
)
from .services import approve_article, dispatch_approval, send_newsletter


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    APPROVAL_API_KEY="unit-test-integration-key",
)
class NewsTests(TestCase):
    """API, workflow and role tests sharing one fixture set."""

    @classmethod
    def setUpTestData(cls):
        """Create users for each role, a publisher and content."""
        cls.reader = User.objects.create_user(
            "reader", "reader@example.com", "Strong-pass-123")
        cls.other_reader = User.objects.create_user(
            "other-reader", "other@example.com", "Strong-pass-123")
        cls.journalist = User.objects.create_user(
            "writer", "writer@example.com", "Strong-pass-123",
            role="journalist")
        cls.other_writer = User.objects.create_user(
            "other-writer", "writer2@example.com", "Strong-pass-123",
            role="journalist")
        cls.editor = User.objects.create_user(
            "editor", "editor@example.com", "Strong-pass-123", role="editor")
        cls.publisher = Publisher.objects.create(name="Daily Cape")
        cls.publisher.journalists.add(cls.journalist)
        cls.publisher.editors.add(cls.editor)
        cls.article = Article.objects.create(
            title="Published story", content="Full approved content",
            author=cls.journalist, publisher=cls.publisher, approved=True)
        cls.independent = Article.objects.create(
            title="Independent story", content="Independent content",
            author=cls.other_writer, approved=True)
        cls.draft = Article.objects.create(
            title="Secret draft", content="Not public", author=cls.journalist,
            publisher=cls.publisher)
        cls.issue = Newsletter.objects.create(
            title="Weekend", description="A selection", author=cls.journalist)
        cls.issue.articles.add(cls.article)

    def setUp(self):
        """Give each test a fresh, unauthenticated API client."""
        self.api = APIClient()

    def authenticate(self, user):
        """Send requests as ``user`` using token auth."""
        token, _ = Token.objects.get_or_create(user=user)
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def ids(self, response):
        """Assert a 200 list response and return the article IDs."""
        self.assertEqual(response.status_code, 200, response.data)
        return {item["id"] for item in response.data["results"]}

    def test_anonymous_api_requires_authentication(self):
        """Fail: requests without a token are rejected."""
        self.assertEqual(self.api.get("/api/articles/").status_code, 401)

    def test_token_endpoint_valid_and_invalid_credentials(self):
        """Token login succeeds with good and fails with bad credentials."""
        response = self.api.post("/api/token/", {
            "username": "reader", "password": "Strong-pass-123"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.data)
        self.assertEqual(self.api.post("/api/token/", {
            "username": "reader", "password": "wrong"}).status_code, 400)

    def test_all_role_lists_exclude_drafts(self):
        """Every role's article list contains approved stories only."""
        for user in [self.reader, self.journalist, self.editor]:
            self.authenticate(user)
            self.assertEqual(self.ids(self.api.get("/api/articles/")),
                             {self.article.pk, self.independent.pk})

    def test_publisher_subscription_filters_and_hides_draft(self):
        """Publisher subscribers get its approved stories, not drafts."""
        self.reader.publisher_subscriptions.add(self.publisher)
        self.authenticate(self.reader)
        self.assertEqual(self.ids(self.api.get("/api/articles/subscribed/")),
                         {self.article.pk})

    def test_journalist_subscription_filters(self):
        """Journalist subscribers get only that journalist's stories."""
        self.reader.journalist_subscriptions.add(self.other_writer)
        self.authenticate(self.reader)
        self.assertEqual(self.ids(self.api.get("/api/articles/subscribed/")),
                         {self.independent.pk})

    def test_overlapping_subscriptions_do_not_duplicate(self):
        """A story matched by two subscriptions appears once."""
        self.reader.publisher_subscriptions.add(self.publisher)
        self.reader.journalist_subscriptions.add(self.journalist)
        self.authenticate(self.reader)
        response = self.api.get("/api/articles/subscribed/")
        self.assertEqual(response.data["count"], 1)

    def test_no_subscriptions_returns_empty_feed(self):
        """A reader with no subscriptions gets an empty feed."""
        self.authenticate(self.reader)
        self.assertEqual(
            self.ids(
                self.api.get("/api/articles/subscribed/")),
            set())

    def test_non_reader_cannot_use_subscription_feed(self):
        """Fail: journalists and editors cannot use the reader feed."""
        self.authenticate(self.journalist)
        self.assertEqual(self.api.get(
            "/api/articles/subscribed/").status_code, 403)

    def test_reader_cannot_retrieve_draft_or_write(self):
        """Fail: readers cannot see drafts or create/edit/delete."""
        self.authenticate(self.reader)
        self.assertEqual(self.api.get(
            f"/api/articles/{self.draft.pk}/").status_code, 404)
        self.assertEqual(self.api.post("/api/articles/", {
            "title": "Attempt", "content": "No"}).status_code, 403)
        self.assertEqual(self.api.patch(f"/api/articles/{self.article.pk}/", {
            "title": "Attempt"}).status_code, 403)
        self.assertEqual(self.api.delete(
            f"/api/articles/{self.article.pk}/").status_code, 403)

    def test_journalist_creates_valid_article_and_reads_own_draft(self):
        """A journalist creates a draft and can read it back."""
        self.authenticate(self.journalist)
        response = self.api.post("/api/articles/", {
            "title": "New", "content": "New content",
            "publisher": self.publisher.pk})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["approved"])
        self.assertEqual(response.data["author"], self.journalist.pk)
        self.assertEqual(self.api.get(
            f"/api/articles/{response.data['id']}/").status_code, 200)

    def test_editor_cannot_create_article(self):
        """Fail: editors cannot create articles through the API."""
        self.authenticate(self.editor)
        self.assertEqual(self.api.post("/api/articles/", {
            "title": "No", "content": "No"}).status_code, 403)

    def test_article_validation_and_approval_spoofing(self):
        """Fail: blank title, spoofed approval/author, foreign publisher."""
        self.authenticate(self.journalist)
        for data in [{"title": "", "content": "x"},
                     {"title": "x", "content": "x", "approved": True},
                     {"title": "x", "content": "x", "author": self.editor.pk}]:
            self.assertEqual(self.api.post(
                "/api/articles/", data, format="json").status_code, 400)
        foreign = Publisher.objects.create(name="Other paper")
        self.assertEqual(self.api.post("/api/articles/", {
            "title": "x", "content": "x", "publisher": foreign.pk
        }).status_code, 400)

    def test_journalist_cannot_edit_or_delete_another_authors_article(self):
        """Fail: journalists cannot change another author's work."""
        self.authenticate(self.journalist)
        url = f"/api/articles/{self.independent.pk}/"
        self.assertEqual(self.api.patch(url, {"title": "x"}).status_code, 403)
        self.assertEqual(self.api.delete(url).status_code, 403)

    def test_put_resets_approval_and_hides_story(self):
        """Editing a published story sends it back for review."""
        self.authenticate(self.journalist)
        response = self.api.put(f"/api/articles/{self.article.pk}/", {
            "title": "Updated", "content": "Changed",
            "publisher": self.publisher.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["approved"])
        self.assertEqual(response.data["revision"], 2)
        self.authenticate(self.reader)
        self.assertEqual(self.api.get(
            f"/api/articles/{self.article.pk}/").status_code, 404)

    def test_editor_cannot_manage_other_publishers(self):
        """Fail: editors cannot manage another publisher's content."""
        foreign = Publisher.objects.create(name="Foreign paper")
        article = Article.objects.create(title="Foreign", content="x",
                                         author=self.other_writer,
                                         publisher=foreign, approved=True)
        self.authenticate(self.editor)
        self.assertEqual(self.api.delete(
            f"/api/articles/{article.pk}/").status_code, 403)
        with self.assertRaises(PermissionDenied):
            approve_article(article.pk, self.editor)

    def test_only_editor_can_approve(self):
        """Fail: readers and journalists cannot approve articles."""
        for user in [self.reader, self.journalist]:
            self.authenticate(user)
            self.assertIn(self.api.post(
                f"/api/articles/{self.draft.pk}/approve/").status_code,
                [403, 404])

    @patch("news.services.requests.post")
    def test_editor_approval_email_deduplication_http_and_repeat(self, post):
        """Approval emails once, POSTs the log; a repeat sends nothing."""
        post.return_value = Mock(status_code=201)
        self.reader.publisher_subscriptions.add(self.publisher)
        self.reader.journalist_subscriptions.add(self.journalist)
        self.authenticate(self.editor)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.api.post(
                f"/api/articles/{self.draft.pk}/approve/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.reader.email])
        self.assertIn(self.draft.content, mail.outbox[0].body)
        self.assertEqual(post.call_args.kwargs["json"], {
            "article": self.draft.pk, "revision": 1})
        self.assertEqual(post.call_args.kwargs["timeout"], 5)
        with self.captureOnCommitCallbacks(execute=True):
            self.api.post(f"/api/articles/{self.draft.pk}/approve/")
        self.assertEqual(len(mail.outbox), 1)
        post.assert_called_once()

    @patch("news.services.requests.post", return_value=Mock(status_code=201))
    def test_independent_article_only_emails_its_subscribers(self, post):
        """Independent stories email only the journalist's followers."""
        draft = Article.objects.create(title="Independent", content="x",
                                       author=self.journalist)
        self.reader.journalist_subscriptions.add(self.journalist)
        with self.captureOnCommitCallbacks(execute=True):
            approve_article(draft.pk, self.editor)
        self.assertEqual([email.to for email in mail.outbox],
                         [[self.reader.email]])

    @patch("news.services.requests.post")
    def test_http_failure_can_retry_without_duplicate_email(self, post):
        """A failed API POST can be retried without re-sending email."""
        self.reader.publisher_subscriptions.add(self.publisher)
        post.side_effect = requests.Timeout()
        with self.assertLogs("news.services", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                approve_article(self.draft.pk, self.editor)
        delivery = ApprovalDelivery.objects.get(article=self.draft)
        self.assertTrue(delivery.email_sent)
        self.assertFalse(delivery.api_logged)
        self.assertIn("API log failed", delivery.last_error)
        post.side_effect = None
        post.return_value = Mock(status_code=201)
        with self.captureOnCommitCallbacks(execute=True):
            approve_article(self.draft.pk, self.editor)
        delivery.refresh_from_db()
        self.assertTrue(delivery.api_logged)
        self.assertEqual(delivery.last_error, "")
        self.assertEqual(len(mail.outbox), 1)

    def test_api_receipt_requires_key_approved_revision_and_is_idempotent(
            self):
        """/api/approved/ needs the key and logs each revision once."""
        url = "/api/approved/"
        payload = {"article": self.article.pk, "revision": 1}
        self.assertEqual(self.api.post(url, payload).status_code, 403)
        self.api.credentials(HTTP_X_APPROVAL_KEY="unit-test-integration-key")
        self.assertEqual(
            self.api.post(
                url,
                payload,
                format="json").status_code,
            201)
        self.assertEqual(
            self.api.post(
                url,
                payload,
                format="json").status_code,
            200)
        self.assertEqual(ApprovalLog.objects.count(), 1)
        self.assertEqual(self.api.post(url, {"article": self.draft.pk,
                         "revision": 1}, format="json").status_code, 404)
        self.assertEqual(self.api.post(url, {"article": "bad",
                         "revision": 1}, format="json").status_code, 400)

    def test_editor_deletes_article(self):
        """An editor can delete an article in their scope."""
        self.authenticate(self.editor)
        self.assertEqual(self.api.delete(
            f"/api/articles/{self.article.pk}/").status_code, 204)

    def test_newsletter_reader_can_view_but_not_write(self):
        """Readers can read newsletters but cannot create or delete them."""
        self.authenticate(self.reader)
        self.assertEqual(self.api.get("/api/newsletters/").status_code, 200)
        self.assertEqual(self.api.post("/api/newsletters/", {
            "title": "No", "description": "No", "articles": [self.article.pk]
        }, format="json").status_code, 403)
        self.assertEqual(self.api.delete(
            f"/api/newsletters/{self.issue.pk}/").status_code, 403)

    def test_newsletter_creation_rejects_drafts_and_allows_editor(self):
        """Newsletters accept approved stories only; editors can create."""
        self.authenticate(self.journalist)
        data = {"title": "Issue", "description": "Curated",
                "articles": [self.draft.pk]}
        self.assertEqual(self.api.post(
            "/api/newsletters/", data, format="json").status_code, 400)
        data["articles"] = [self.article.pk]
        self.assertEqual(self.api.post(
            "/api/newsletters/", data, format="json").status_code, 201)
        self.authenticate(self.editor)
        self.assertEqual(self.api.post(
            "/api/newsletters/", data, format="json").status_code, 201)

    def test_newsletter_hides_story_returned_to_draft(self):
        """A story sent back to draft drops out of its newsletter."""
        self.article.approved = False
        self.article.save()
        self.authenticate(self.reader)
        response = self.api.get(f"/api/newsletters/{self.issue.pk}/")
        self.assertEqual(response.data["articles"], [])
        response = self.client.get(f"/newsletters/{self.issue.pk}/")
        self.assertNotContains(response, self.article.title)

    def test_newsletter_owner_and_editor_can_update_delete(self):
        """Owner/editor can update and delete issues; others cannot."""
        url = f"/api/newsletters/{self.issue.pk}/"
        self.authenticate(self.other_writer)
        self.assertEqual(self.api.patch(url, {
            "title": "No"}).status_code, 403)
        self.authenticate(self.journalist)
        self.assertEqual(self.api.patch(url, {
            "title": "Updated"}).status_code, 200)
        self.authenticate(self.editor)
        self.assertEqual(self.api.delete(url).status_code, 204)

    def test_roles_groups_and_role_specific_fields(self):
        """Roles map to groups; other-role fields return None."""
        self.assertTrue(self.reader.groups.filter(name="Reader").exists())
        self.assertTrue(self.journalist.has_perm("news.add_article"))
        self.assertFalse(self.reader.has_perm("news.add_article"))
        self.assertTrue(self.editor.has_perm("news.delete_article"))
        self.assertIsNone(self.journalist.reader_publishers)
        self.assertIsNone(self.reader.independent_articles)
        self.reader.publisher_subscriptions.add(self.publisher)
        self.reader.role = "journalist"
        self.reader.save()
        self.assertFalse(self.reader.publisher_subscriptions.exists())
        self.assertFalse(self.reader.groups.filter(name="Reader").exists())

    def test_subscription_model_rejects_inapplicable_relations(self):
        """Fail: non-readers cannot subscribe, or follow non-journalists."""
        with self.assertRaises(ValidationError):
            with transaction.atomic():
                self.journalist.publisher_subscriptions.add(self.publisher)
        with self.assertRaises(ValidationError):
            with transaction.atomic():
                self.reader.journalist_subscriptions.add(self.editor)

    def test_editor_group_also_grants_editor_access(self):
        """Membership of the Editor group grants editor rights."""
        self.other_reader.groups.add(Group.objects.get(name="Editor"))
        self.assertTrue(self.other_reader.is_editor)
        self.client.force_login(self.other_reader)
        self.assertEqual(self.client.get("/workspace/").status_code, 200)

    def test_public_registration_cannot_escalate_role(self):
        """Fail: sign-up cannot create an editor or journalist."""
        response = self.client.post("/accounts/register/",
                                    {"username": "newreader",
                                     "email": "newreader@example.com",
                                     "password1": "New-strong-pass-123",
                                     "password2": "New-strong-pass-123",
                                     "role": "editor"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.get(username="newreader").role, "reader")

    def test_html_draft_access_and_post_only_approval(self):
        """Readers can't see drafts or the workspace; approval is POST-only."""
        self.assertEqual(self.client.get(
            f"/articles/{self.draft.pk}/").status_code, 404)
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get("/workspace/").status_code, 403)
        self.assertEqual(self.client.get("/articles/new/").status_code, 403)
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(
            f"/articles/{self.draft.pk}/approve/").status_code, 405)

    def test_html_edit_returns_article_to_review(self):
        """Editing through the website also resets approval."""
        self.client.force_login(self.journalist)
        response = self.client.post(f"/articles/{self.article.pk}/edit/", {
            "title": "Edited via form", "content": "Changed content",
            "publisher": self.publisher.pk})
        self.assertEqual(response.status_code, 302)
        self.article.refresh_from_db()
        self.assertFalse(self.article.approved)
        self.assertEqual(self.article.revision, 2)

    @patch("news.services.requests.post")
    def test_rollback_discards_notification_callback(self, post):
        """No notifications are sent if the approval rolls back."""
        from django.db import transaction

        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    approve_article(self.draft.pk, self.editor)
                    raise RuntimeError("Rollback")
        post.assert_not_called()
        self.draft.refresh_from_db()
        self.assertFalse(self.draft.approved)

    def test_newsletter_email_deduplicates_and_omits_drafts(self):
        """Newsletter email goes once per reader, without drafts."""
        self.issue.publisher = self.publisher
        self.issue.save()
        self.issue.articles.add(self.draft)
        self.reader.publisher_subscriptions.add(self.publisher)
        self.reader.journalist_subscriptions.add(self.journalist)
        self.assertEqual(send_newsletter(self.issue, self.journalist), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.article.content, mail.outbox[0].body)
        self.assertNotIn(self.draft.content, mail.outbox[0].body)

    def test_reader_cannot_send_newsletter(self):
        """Fail: readers cannot send a newsletter."""
        self.client.force_login(self.reader)
        self.assertEqual(self.client.post(
            f"/newsletters/{self.issue.pk}/send/").status_code, 403)

    def test_newsletter_without_approved_stories_cannot_be_sent(self):
        """Fail: an issue with no approved stories cannot be sent."""
        self.issue.articles.clear()
        with self.assertRaises(ValueError):
            send_newsletter(self.issue, self.journalist)

    @patch("news.services.requests.post")
    def test_active_delivery_lease_skips_concurrent_retry(self, post):
        """A delivery already in progress is not run a second time."""
        from datetime import timedelta
        from django.utils import timezone

        delivery = ApprovalDelivery.objects.create(
            article=self.article, revision=1,
            processing_until=timezone.now() + timedelta(minutes=1))
        dispatch_approval(delivery.pk)
        post.assert_not_called()

    def test_token_exchange_ignores_existing_browser_session(self):
        """Token login uses the credentials, not an existing session user."""
        browser = APIClient(enforce_csrf_checks=True)
        browser.force_login(self.editor)
        response = browser.post("/api/token/", {
            "username": "reader", "password": "Strong-pass-123"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Token.objects.get(key=response.data["token"]).user,
                         self.reader)
