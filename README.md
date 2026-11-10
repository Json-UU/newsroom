# The Newsroom

A Django news platform with independent and publisher journalism, editorial
approval, reader subscriptions, curated newsletters and a token-authenticated
REST API.

- **Run it with a virtual environment** or **with Docker** (below).
- **Documentation:** open [`docs/_build/html/index.html`](docs/_build/html/index.html)
  in a browser for the Sphinx user guide and code reference.

## Configuration and secrets

Settings are read from environment variables, or from a `.env` file in this
folder. `.env` is listed in `.gitignore`, so **no passwords or keys are stored in
this repository**. Create your own copy from the template:

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Then fill in the values you need:

| Variable | What it is | How to get it |
| --- | --- | --- |
| `MARIADB_PASSWORD` (and `MARIADB_USER`, `MARIADB_HOST`) | Login for your MariaDB server | The password you chose when installing MariaDB ([download](https://mariadb.org/download/)) |
| `DJANGO_USE_SQLITE=1` | Use SQLite instead of MariaDB | Nothing to obtain; useful if you do not have MariaDB |
| `DJANGO_SECRET_KEY` | Django signing key; required when `DJANGO_DEBUG=0` | Generate one: `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"` |
| `APPROVAL_API_KEY` | Shared key for the internal approval API; required when `DJANGO_DEBUG=0` | Any long random string, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP login for real email (optional) | From your email provider, e.g. a Gmail app password |
| `DJANGO_ADMIN_PASSWORD`, `NEWSROOM_DEMO_PASSWORD` | Override the demo passwords (optional) | Choose your own |

In development (`DJANGO_DEBUG=1`, the default) the secret key and approval key
fall back to local-only values, so only the database settings are needed.

## Run with a virtual environment

You need **Python 3.11+** and either a running **MariaDB** server or
`DJANGO_USE_SQLITE=1` in `.env`.

```bash
git clone REPO_URL
cd newsroom
python -m venv .venv
.venv\Scriptsctivate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # Windows: copy .env.example .env
```

Edit `.env` (see [Configuration and secrets](#configuration-and-secrets)), then:

```bash
python run.py
```

`run.py` creates the `newsroom` database if needed, applies migrations, loads
demo content and starts the server at <http://127.0.0.1:8000/>. Press Ctrl+C to
stop. The plain Django equivalent is:

```bash
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

On Windows you can instead double-click **`start.bat`**: the first run creates
`.env` and opens it in Notepad; the second run installs the requirements and
starts the server.

### Troubleshooting (venv)

- **"Could not connect to the database":** check MariaDB is running and the
  user and password in `.env` are right. A non-root user needs permission to
  create databases, or create the `newsroom` database for it yourself.
- **No MariaDB available:** add `DJANGO_USE_SQLITE=1` to `.env` to run on SQLite
  instead. This is a fallback only; the submission targets MariaDB.
- **Portable MariaDB:** set `MARIADB_SERVER` and `MARIADB_CONFIG` in `.env` and
  `run.py` starts it automatically.

## Run with Docker

You need [Docker](https://docs.docker.com/get-docker/). The image runs on
SQLite in development mode by default, so it works without MariaDB or a `.env`
file.

```bash
git clone REPO_URL
cd newsroom
docker build -t newsroom .
docker run --rm -p 8000:8000 newsroom
```

Open <http://localhost:8000/> and sign in with the [demo logins](#logins).
Approval emails are printed in the container's output. Press Ctrl+C to stop;
the SQLite data is discarded with the container.

**Play with Docker:** sign in at <https://labs.play-with-docker.com>, click
**Add new instance**, run the four commands above, then click the **8000**
badge at the top of the page to open the app.

**Using MariaDB instead:** pass your settings at run time (never bake them into
the image). `host.docker.internal` reaches a MariaDB server on your own machine
from Docker Desktop:

```bash
docker run --rm -p 8000:8000 -e DJANGO_USE_SQLITE=0   -e MARIADB_HOST=host.docker.internal -e MARIADB_PASSWORD=your-password   newsroom
```

The `newsroom` database must already exist on that server
(`CREATE DATABASE newsroom CHARACTER SET utf8mb4;`).

## Rebuild the documentation

```bash
pip install -r requirements-dev.txt
cd docs
make clean
make html                         # Windows PowerShell: .\make.bat html
```

The output goes to `docs/_build/html/` and is committed so readers of the
repository can open it directly.

## Logins

| Username | Password | Use it to |
| --- | --- | --- |
| `admin` | `Admin-pass-123` | Manage users, roles and publishers at `/admin/` |
| `editor` | `Demo-pass-123` | Review and approve articles |
| `journalist` | `Demo-pass-123` | Write articles and newsletters |
| `reader` | `Demo-pass-123` | Read articles and the subscribed feed |

The admin account is created by a migration (`news/migrations/0003_default_admin.py`)
and the demo accounts by `seed_demo`. Both only use these default passwords in
development (`DJANGO_DEBUG=1`), and never change an existing account's password.
Change them for any real use, or set `DJANGO_ADMIN_PASSWORD` and
`NEWSROOM_DEMO_PASSWORD` in `.env` before the first run.

Demo stories are loaded as already published, so creating them sends no email.
To see the approval workflow, approve the draft story as `editor`.

## Browser walkthrough

1. Register a reader or sign in as the demo `reader`. Choose publisher and/or
   journalist subscriptions. Open **My feed** to see matching approved content.
2. Sign in as `journalist`. Open **Workspace**, write an article and save for
   review. Choose a publisher you belong to or leave it blank for independent
   journalism. Other readers cannot retrieve the draft.
3. Sign in as `editor`. Open the draft through **Workspace**, review it and click
   **Approve and publish**. This emails subscribers and makes a real HTTP POST to
   `/api/approved/`. If an integration fails, the article remains published and
   the page offers **Retry notifications**. Successful channels are not resent.
4. As a journalist/editor, curate a newsletter from approved stories. Readers
   browse it through **Newsletters**. Its owner/scoped editor can email an issue
   to subscribers. Each explicit send click sends a new copy.
5. Edit a published story: it returns to review and disappears from public
   pages, feeds and newsletter contents until an editor approves it again.

Use `/admin/` to provision users/roles and assign publisher journalists/editors.
Registration always creates a reader. Journalists can manage their own content;
editors can manage independent content and their publishers' content. Editors
cannot approve their own stories. Role changes synchronise the Django group.
Do not directly edit workflow flags in the database. Article admin is read-only
for content changes; the application handles approval and notifications.

## Email and integration

Development email goes to the server console, so no external mail account is
required. To send real mail set `EMAIL_BACKEND` to
`django.core.mail.backends.smtp.EmailBackend`, and configure `EMAIL_HOST`,
`EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` and
`DEFAULT_FROM_EMAIL`. Never commit passwords or API keys.

Approval uses option 2 from the brief: explicit service logic from the approval
view, with post-commit delivery. Publisher and journalist subscribers are combined
and deduplicated. Each message has one recipient. The internal POST authenticates
with `X-Approval-Key`; it accepts only the canonical approved article/revision.
Receipts are unique per revision. A two-minute delivery lease prevents concurrent
retry requests and expires if a process dies. Failed channels can be retried.
Synchronous SMTP has no exactly-once guarantee after a process crash; see
[design notes](docs/design.md) for the boundary and production improvements.

## REST API

Obtain a token using `POST /api/token/` with `username` and `password`. Supply
`Authorization: Token <token>` on subsequent requests. Session authentication is
also available for the browsable API. Lists are paginated with `count`, `next`,
`previous`, `results`. All API reads require authentication.

| Method | Endpoint | Behaviour |
| --- | --- | --- |
| GET | `/api/articles/` | All approved articles |
| GET | `/api/articles/subscribed/` | Reader's subscribed approved articles |
| GET | `/api/articles/<id>/` | Approved story, or own/scoped editorial draft |
| POST | `/api/articles/` | Journalist creates a draft |
| PUT/PATCH | `/api/articles/<id>/` | Owner journalist or scoped editor; resets approval |
| DELETE | `/api/articles/<id>/` | Owner journalist or scoped editor |
| POST | `/api/articles/<id>/approve/` | Scoped editor approves/retries delivery |
| GET/POST | `/api/newsletters/` | Read issues; journalist/editor creates |
| GET/PUT/PATCH/DELETE | `/api/newsletters/<id>/` | Read; scoped author/editor writes |
| GET | `/api/publishers/` | Publisher serializer |
| GET | `/api/journalists/` | User serializer; excludes private fields |
| POST | `/api/approved/` | Shared-key integration receipt, not public publishing |

Example PowerShell requests (with the server running):

```powershell
$base = 'http://127.0.0.1:8000'
$login = Invoke-RestMethod "$base/api/token/" -Method Post -Body @{
    username='reader'; password='Demo-pass-123'
}
$headers = @{ Authorization = "Token $($login.token)" }
Invoke-RestMethod "$base/api/articles/subscribed/" -Headers $headers
# A reader write is rejected with HTTP 403:
Invoke-RestMethod "$base/api/articles/" -Method Post -Headers $headers -Body @{
    title='Not allowed'; content='Readers cannot create articles.'
}
```

Article create/update body: `title`, `content`, optional `publisher` ID/null.
Author/approval/revision are controlled by the server. Newsletter body: `title`,
`description`, `publisher` ID/null, and `articles` (array of approved article IDs).
The public list intentionally includes all approved stories; subscription
filtering applies to the `/subscribed/` endpoint, as specified in the brief.

## Validation

For VS Code, open this `newsroom` folder (or the repository workspace) and
install the optional development tools once:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Select the `.venv` interpreter in VS Code (**Python: Select Interpreter**).
`.pylintrc` enables `pylint-django`. This lets Pylint recognise Django's generated
model members such as `Article.objects`. After configuration changes, use
**Developer: Reload Window** in VS Code. Runtime dependencies remain in
`requirements.txt`; editor tools are in `requirements-dev.txt`.

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity 2
python -m flake8
```

Tests exercise token authentication, all roles, subscriptions, overlapping
subscriptions, ownership/publisher scope, create/update/delete, draft privacy,
group synchronisation, approval, mocked email/HTTP failures, retry, transaction
rollback, newsletter CRUD/email and validation. No external mail is sent by tests.

For a pre-existing SQLite dataset, stop writes, back it up, export domain data
with `dumpdata news --natural-foreign --natural-primary --indent 2`, switch to
MariaDB, migrate, then `loaddata` the export. Do this before creating conflicting
users or demo fixtures on the target. Reconcile record counts and subscriptions.
This new project has no legacy dataset requiring transfer.

## Design and references

See the [PDF requirement checklist](docs/requirements.md),
[normalisation and UI plan](docs/design.md) and
[verification record](docs/verification.md).

- [Django transactions and on_commit](https://docs.djangoproject.com/en/5.2/topics/db/transactions/)
- [DRF token authentication](https://www.django-rest-framework.org/api-guide/authentication/#tokenauthentication)
- [DRF testing](https://www.django-rest-framework.org/api-guide/testing/)
- [MariaDB Windows ZIP installation](https://mariadb.com/docs/server/server-management/install-and-upgrade-mariadb/installing-mariadb/binary-packages/installing-mariadb-windows-zip-packages)

Development settings are intended for a local capstone demonstration. Deployment
requires a private secret, `DJANGO_DEBUG=0`, host configuration, HTTPS and an
appropriate application/static server.
