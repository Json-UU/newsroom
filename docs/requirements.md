# Requirement checklist

Each requirement from the brief (*Capstone Project – News Application*,
HyperionDev) with where it is implemented and how it is verified. Test names
refer to `news/tests.py` unless another file is given.

## Steps 1–2: project and app

| Requirement | Where |
| --- | --- |
| Django project created with `startproject` | `config/` (settings, URLs, WSGI) |
| Django app created with `startapp` | `news/` |

## Step 3: models

| Requirement | Where | Verified by |
| --- | --- | --- |
| Article has `title`, `content`, `author`, `created_at`, `approved`, `publisher` | `news/models.py` `Article` | `test_journalist_creates_valid_article_and_reads_own_draft` |
| `approved` is a Boolean set by an editor | `Article.approved`; read-only in the API | `test_article_validation_and_approval_spoofing` |
| Article is independent (journalist) or publisher content | Nullable `Article.publisher`; `Article.clean` checks membership | `test_independent_article_only_emails_its_subscribers` |
| Publisher has multiple editors and journalists | `Publisher.editors`, `Publisher.journalists` (many-to-many) | `test_editor_cannot_manage_other_publishers` |
| Newsletter has `title`, `description`, `created_at`, `author` and many-to-many `Article` | `news/models.py` `Newsletter` | `test_newsletter_creation_rejects_drafts_and_allows_editor` |
| Newsletters viewed by readers, created/edited by journalists and editors | `NewsletterViewSet`, `views.newsletter_edit` | `test_newsletter_reader_can_view_but_not_write`, `test_newsletter_owner_and_editor_can_update_delete` |
| Custom user with a role and a matching group | `User.role`; `signals.synchronise_role` | `test_roles_groups_and_role_specific_fields` |
| Reader group: view articles and newsletters | `signals.provision_groups` | `test_roles_groups_and_role_specific_fields` |
| Editor group: view, update, delete articles and newsletters | `signals.provision_groups` | `test_roles_groups_and_role_specific_fields` |
| Journalist group: create, view, update, delete articles and newsletters | `signals.provision_groups` | `test_roles_groups_and_role_specific_fields` |
| Reader fields: publisher and journalist subscriptions (ManyToManyField) | `User.publisher_subscriptions`, `User.journalist_subscriptions` | `test_publisher_subscription_filters_and_hides_draft` |
| Journalist fields: independent articles and newsletters (reverse relation) | `User.independent_articles`, `User.independent_newsletters` | `test_roles_groups_and_role_specific_fields` |
| Other role's fields are `None` | Properties return `None`; subscriptions cleared on role change | `test_roles_groups_and_role_specific_fields`, `test_subscription_model_rejects_inapplicable_relations` |

Editors are also allowed to *create* newsletters. The brief's newsletter
section says they may, though its permission list does not; see
[design notes](design.md#roles-versus-groups).

## Step 4: editor review and approval

| Requirement | Where | Verified by |
| --- | --- | --- |
| Templates, views and URLs for editors to review and approve | `/workspace/`, `/articles/<id>/`, `POST /articles/<id>/approve/` | `test_html_draft_access_and_post_only_approval` |
| Access control | `login_required`, `access.py`, 403/404 responses | `test_reader_cannot_retrieve_draft_or_write`, `test_editor_group_also_grants_editor_access` |
| **Option 2 chosen:** logic runs from the approval view | `views.article_approve` → `services.approve_article` | `test_editor_approval_email_deduplication_http_and_repeat` |
| Email the approved article to the journalist's or publisher's subscribers | `services.dispatch_approval` | `test_editor_approval_email_deduplication_http_and_repeat`, `test_independent_article_only_emails_its_subscribers` |
| POST to our own `/api/approved/` with `requests` | `services.dispatch_approval`, `api.ApprovalLogView` | `test_editor_approval_email_deduplication_http_and_repeat`, `test_api_receipt_requires_key_approved_revision_and_is_idempotent` |

## Step 5: REST API

| Requirement | Where | Verified by |
| --- | --- | --- |
| `GET /api/articles/`: all approved articles | `ArticleViewSet.get_queryset` | `test_all_role_lists_exclude_drafts` |
| `GET /api/articles/subscribed/`: reader's subscriptions only | `ArticleViewSet.subscribed` | `test_publisher_subscription_filters_and_hides_draft`, `test_journalist_subscription_filters`, `test_overlapping_subscriptions_do_not_duplicate`, `test_no_subscriptions_returns_empty_feed` |
| `GET /api/articles/<id>/`: one article | `ArticleViewSet` (retrieve) | `test_reader_cannot_retrieve_draft_or_write` |
| `POST /api/articles/`: journalists only | `ArticleViewSet.perform_create` | `test_journalist_creates_valid_article_and_reads_own_draft`, `test_editor_cannot_create_article` |
| `PUT /api/articles/<id>/`: editors and journalists | `ArticleViewSet.perform_update` | `test_put_resets_approval_and_hides_story`, `test_journalist_cannot_edit_or_delete_another_authors_article` |
| `DELETE /api/articles/<id>/`: editors and journalists | `ArticleViewSet.perform_destroy` | `test_editor_deletes_article` |
| Token authentication | DRF `TokenAuthentication` | `test_token_endpoint_valid_and_invalid_credentials` |
| Authentication endpoint `/api/token/` | `config/urls.py` | `test_token_endpoint_valid_and_invalid_credentials`, `test_token_exchange_ignores_existing_browser_session` |
| Only journalists POST | `perform_create` | `test_editor_cannot_create_article`, `test_reader_cannot_retrieve_draft_or_write` |
| Only editors approve | `ArticleViewSet.approve`, `services.approve_article` | `test_only_editor_can_approve` |
| Readers can only view | Object checks in `perform_*` | `test_reader_cannot_retrieve_draft_or_write` |
| Serializers for Article, User, Newsletter, Publisher | `news/serializers.py` | Used by every API test |

## Step 6: automated tests

| Required coverage | Tests |
| --- | --- |
| Authenticated access per role | `test_anonymous_api_requires_authentication`, `test_all_role_lists_exclude_drafts`, `test_non_reader_cannot_use_subscription_feed` |
| Reader retrieves only subscribed content | the four `subscribed` tests listed above |
| Journalist can create articles | `test_journalist_creates_valid_article_and_reads_own_draft` |
| Editor can approve and delete | `test_editor_approval_email_deduplication_http_and_repeat`, `test_editor_deletes_article` |
| Newsletters behave correctly | `test_newsletter_*` (six tests) |
| Approval logic works, with email and `/api/approved/` mocked | `test_editor_approval_email_deduplication_http_and_repeat`, `test_http_failure_can_retry_without_duplicate_email`, `test_rollback_discards_notification_callback`, `test_active_delivery_lease_skips_concurrent_retry` |
| Successful and failed requests | Tests whose docstrings start with "Fail:" check refused requests (401, 403, 404, 400) |

Total: 43 tests (37 in `news/tests.py`, 6 in `news/test_defaults.py` for the
default admin and demo accounts).

## Remaining items

| Requirement | Where |
| --- | --- |
| Design before implementation: functional and non-functional requirements | [design.md](design.md) |
| UI/UX planning | [design.md](design.md#uiux-plan) |
| Normalised tables | [design.md](design.md#data-model-third-normal-form) |
| PEP 8, comments, modular code, defensive coding | flake8 passes; docstrings on every class and function; `try/except` around email and HTTP; validation in forms and serializers |
| Migrate the database to MariaDB | MariaDB is the default database in `config/settings.py`; see [verification.md](verification.md) |
