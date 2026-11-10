# Newsroom design

This document records the planning done before implementation: the
requirements taken from the brief, the normalised data model, how roles map to
groups, the user-interface plan and the approval flow.

## Functional requirements

| # | The system must… | Implemented in |
| --- | --- | --- |
| F1 | Let anyone browse and search approved articles | `views.home`, `templates/news/home.html` |
| F2 | Let a visitor register; new accounts are always readers | `views.register`, `forms.RegistrationForm` |
| F3 | Let readers subscribe to publishers and to journalists | `views.subscriptions`, `User.*_subscriptions` |
| F4 | Show readers a feed of approved articles from their subscriptions | `views.feed`, `access.subscribed_articles` |
| F5 | Let journalists write articles, independently or for a publisher they belong to | `views.article_edit`, `forms.ArticleForm` |
| F6 | Keep new and edited articles hidden until an editor approves them | `Article.approved`, `services.save_article_changes` |
| F7 | Let editors review and approve articles in their scope, but not their own | `views.article_approve`, `services.approve_article` |
| F8 | On approval, email the journalist's and publisher's subscribers | `services.dispatch_approval` |
| F9 | On approval, POST the article to our own `/api/approved/` endpoint with `requests` | `services.dispatch_approval`, `api.ApprovalLogView` |
| F10 | Let journalists and editors create, edit and delete newsletters of approved articles | `views.newsletter_edit`, `forms.NewsletterForm` |
| F11 | Let readers view newsletters; let the owner email an issue to subscribers | `views.newsletter_detail`, `services.send_newsletter` |
| F12 | Provide a token-authenticated REST API for articles (list, subscribed, detail, create, update, delete) | `api.ArticleViewSet` |
| F13 | Provide a token endpoint at `/api/token/` | `config/urls.py` |
| F14 | Provide serializers for Article, User, Newsletter and Publisher | `serializers.py` |
| F15 | Let an administrator manage users, roles and publisher staff | `admin.py`, `/admin/` |

## Non-functional requirements

| # | Requirement | How it is met |
| --- | --- | --- |
| N1 | **Security / access control:** each role can do only what the brief allows | Group permissions plus object-level checks in `access.py`, shared by views and API; drafts return 404 to people who may not see them |
| N2 | **Authentication:** API uses tokens; website uses sessions | DRF `TokenAuthentication` and `SessionAuthentication`; every API endpoint requires login |
| N3 | **Data integrity:** a normalised schema with constraints | Third normal form (below), unique constraints on delivery and receipt rows, `PROTECT` on authors and publishers |
| N4 | **Reliability:** a failed email or API call must not lose the approval | Notifications run after commit; each channel is tracked and can be retried without repeating the other |
| N5 | **Database:** MariaDB, as the brief requires | MariaDB is the default `DATABASES` entry; SQLite is an opt-in fallback |
| N6 | **Usability:** clear, responsive pages that work on a phone | Three story columns on desktop, two under 1000px, one under 600px; readable type; visible status badges and messages |
| N7 | **Maintainability:** PEP 8, comments and modular code | flake8 passes; docstrings on every class and function; logic split into `access`, `services`, `forms`, `serializers` |
| N8 | **Testability:** automated tests for the API and workflow | 43 Django tests, with email and HTTP mocked |
| N9 | **Ease of setup:** a marker can run it quickly | `start.bat` plus one password in `.env`; default admin and demo accounts |
| N10 | **Secrets:** no real passwords or keys in the repository | Values come from `.env`, which `.gitignore` excludes; built-in defaults apply only in development |

## Data model (third normal form)

```
User ──< Article >── Publisher          (author, optional publisher)
User ──< Newsletter >── Publisher       (author, optional publisher)
Newsletter >──< Article                 (curated articles)
Publisher >──< User                     (editors)
Publisher >──< User                     (journalists)
User(reader) >──< Publisher             (publisher subscriptions)
User(reader) >──< User(journalist)      (journalist subscriptions)
Article ──< ApprovalDelivery            (one per approved revision)
Article ──< ApprovalLog                 (receipt written by /api/approved/)
```

| Table | Key fields | Notes |
| --- | --- | --- |
| `User` | `id`, `username`, unique `email`, `role` | Extends Django's `AbstractUser`. Subscriptions are many-to-many join tables, not columns |
| `Publisher` | `id`, unique `name`, `description` | Editors and journalists are two separate join tables |
| `Article` | `id`, `title`, `content`, `author_id`, `publisher_id` (nullable), `created_at`, `approved`, `approved_by_id`, `revision` | A null publisher means an independent article |
| `Newsletter` | `id`, `title`, `description`, `created_at`, `author_id`, `publisher_id` (nullable) | Articles are a join table |
| `ApprovalDelivery` | `article_id`, `revision` (unique together), `email_sent`, `api_logged`, `last_error`, `processing_until` | Notification state per approved revision |
| `ApprovalLog` | `article_id`, `revision` (unique together), `title`, `received_at` | The "external" receipt |

**Why this is in third normal form:**

- **1NF:** every column holds one value. Lists such as subscriptions, publisher
  staff and newsletter articles live in join tables, not in comma-separated
  columns.
- **2NF:** every table has a single-column surrogate key (`id`), so no column
  depends on part of a composite key. In the two tables with a composite
  uniqueness rule (`article`, `revision`), the other columns describe that
  whole pair.
- **3NF:** no column depends on another non-key column. Author and publisher
  names are not copied into `Article`; they are reached through foreign keys.
  The one deliberate copy is `ApprovalLog.title`, which records the title as it
  was shared at approval time. It is a historical fact, not derived data.

**Role-specific fields.** The brief asks that reader fields be `None` for
journalists and the reverse. A many-to-many relation cannot store `None`, so:

- the subscription relations are emptied whenever a user is not a reader
  (`signals.synchronise_role`), and subscriptions are validated so only
  readers can have them (`signals.validate_subscriptions`);
- the properties `reader_publishers`, `reader_journalists`,
  `independent_articles` and `independent_newsletters` return `None` when the
  user has a different role.

## Roles versus groups

A **role** is a field on the user; a **group** is the Django permission
container. Saving a user puts them in the group that matches their role and
removes the other role groups. The groups and permissions are created
automatically after `migrate`.

| Group | Article permissions | Newsletter permissions |
| --- | --- | --- |
| Reader | view | view |
| Editor | view, change, delete | add, view, change, delete |
| Journalist | add, view, change, delete | add, view, change, delete |

Editors get `add_newsletter` because the brief says newsletters are "edited or
created by journalists and editors", even though its permission list for
editors omits "create". Editors cannot create articles.

Group permissions say *what kind* of action a role may take. Object-level rules
in `access.py` then say *which* items: journalists manage only their own
content, and editors manage independent content plus content from publishers
they edit for. Only editors approve, and never their own articles.

## UI/UX plan

The site uses a calm newspaper style: a serif masthead and headings (Libre
Caslon Display, falling back to Georgia), generous white space and cards for
stories. The story grid has three columns on desktop, two on tablets and one on
phones.

| Page | URL | Who | Purpose |
| --- | --- | --- | --- |
| Latest | `/` | Everyone | Approved stories with search, lead story first |
| Article | `/articles/<id>/` | Everyone (drafts: author and scoped editors) | Full story; edit/delete for managers; **Approve and publish** for editors |
| Register | `/accounts/register/` | Visitors | Create a reader account |
| Sign in | `/accounts/login/` | Visitors | Session login |
| Subscriptions | `/subscriptions/` | Readers | Choose publishers and journalists with checkboxes |
| My feed | `/feed/` | Readers | Stories from subscriptions |
| Workspace | `/workspace/` | Journalists, editors | Own articles, or articles awaiting review, with status badges |
| Write/Edit article | `/articles/new/`, `/articles/<id>/edit/` | Journalists (edit: also editors) | Form; saving sends the story for review |
| Newsletters | `/newsletters/` | Everyone | Browse curated issues |
| Newsletter | `/newsletters/<id>/` | Everyone | Issue with its approved stories; edit/delete/email for managers |
| Curate newsletter | `/newsletters/new/` | Journalists, editors | Pick approved stories with checkboxes |
| Admin | `/admin/` | Administrators | Users, roles, publishers |

**Navigation adapts to the role.** Readers see *My feed* and *Subscriptions*;
journalists and editors see *Workspace*; visitors see *Sign in* and *Become a
reader*. The signed-in user's name and role are always visible.

**Feedback.** Every action ends with a message ("Article saved and awaiting
editorial approval", "Article approved; subscribers notified and API logged").
If a notification fails, the article page explains what failed and shows a
**Retry notifications** button. Deleting asks for confirmation first.

## Approval flow (option 2: explicit service called by the approval view)

The brief offers signals (option 1) or logic in the approval view (option 2).
This project uses **option 2**, because the approval view is the only place an
article becomes approved, and keeping the logic there makes it easy to follow
and to test.

1. An editor clicks **Approve and publish** (`POST /articles/<id>/approve/`) or
   calls `POST /api/articles/<id>/approve/`.
2. `services.approve_article` locks the article row, checks the editor may
   approve it, marks it approved and creates an `ApprovalDelivery` for this
   revision.
3. `transaction.on_commit` schedules `dispatch_approval`, so nothing is sent if
   the database change rolls back.
4. `dispatch_approval` claims a two-minute lease (so two requests cannot deliver
   at once) and then:
   - emails each subscriber of the journalist or the publisher once;
   - POSTs `{"article": id, "revision": n}` to `/api/approved/` with the
     `requests` module and an `X-Approval-Key` header.
5. `/api/approved/` checks the key and that the article and revision are
   approved, then stores one `ApprovalLog` receipt (a repeat call returns 200
   and stores nothing new).
6. Each channel's success is saved. If one failed, the editor can approve
   again to retry only the failed channel.

Editing an approved article increments its `revision` and clears `approved`, so
it leaves public pages until an editor approves the new version.

**Limits and production improvements.** Email is sent synchronously, so a
process crash between sending and saving could resend email on retry. In
production, delivery would move to a task queue (for example Celery) with an
outbox table, and SMTP would be replaced by a transactional email service.
