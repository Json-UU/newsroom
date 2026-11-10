# Verification record

This folder was accidentally deleted on 8 November 2026 and recreated the same
day. The 2 November results below are restored from the original record; the
8 November sections describe checks run on that date.

## 2 November 2026: full verification on MariaDB

| Check | Result |
| --- | --- |
| MariaDB server | 11.4.11-MariaDB, local loopback instance |
| `python manage.py migrate --noinput` on MariaDB | All migrations applied |
| `python manage.py test --verbosity 1` on MariaDB | 37 tests passed |
| Same suite with explicit SQLite fallback | 37 tests passed |
| `python manage.py check` | No issues |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python -m flake8` | Passed, 79-character line limit |

The MariaDB database was created for this capstone; no existing dataset
needed transfer. No SQLite result is substituted for MariaDB validation.

### Browser verification (Playwright)

19 browser assertions passed across two runs:

1. Journalist-created draft is awaiting approval.
2. Journalist has no approval button.
3. Editor approval succeeds with the real HTTP integration.
4. Approved article has no pending delivery errors.
5. Newsletter email targets the subscribed reader.
6. Token exchange works with an existing editor browser session.
7. Token-authenticated subscription feed returns the subscribed article.
8. Reader API writes receive HTTP 403.
9. Editor can create a newsletter through the form.
10. Newsletter renders its selected story.
11. Editor can delete a newsletter through confirmation.
12. Editing a published story resets approval.
13. Reader retrieval of the revised draft receives HTTP 404.
14. Reader workspace access receives HTTP 403.
15. Journalist subscription appears in the reader's browser feed.
16. Draft is absent from the reader's browser feed.
17. Search filters the article list.
18. Mobile viewport has no horizontal overflow.
19. Newsletter remains accessible for reading.

The approval check produced a real `/api/approved/` HTTP 201 response, and a
MariaDB read-back confirmed an `ApprovalLog` for the article revision with
delivery state `email_sent=True`, `api_logged=True`, `last_error=''`.

Email was checked through Django's console backend in the live run and the
in-memory outbox in automated tests. Delivery through an external SMTP provider
was not tested.

## 8 November 2026: documentation pass

Docstrings were added to every class and function (127 at the time) and
comments to the access rules, approval flow, role signals, settings and URLs.
Each edited module was compared with its previous version as a parsed syntax
tree with docstrings removed; all were identical, so behaviour was unchanged.
Tests (37), `check`, `makemigrations --check` and flake8 passed on SQLite.

## 8 November 2026: simplified setup

- Setup reduced to `start.bat` plus one password in `.env`.
- Migration `0003_default_admin` creates the `admin` account.
- `run.py` creates the MariaDB database if missing and loads demo users on the
  first launch only.
- A bug introduced by an outside edit was fixed: the `pk` parameter had been
  removed from `ArticleViewSet.approve`, which made
  `POST /api/articles/<id>/approve/` fail. Two existing tests caught it.

| Check (SQLite) | Result |
| --- | --- |
| `python manage.py test` | 43 tests passed (37 + 6 new in `news/test_defaults.py`) |
| `python manage.py check` | No issues |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python -m flake8` (including `run.py`) | Passed |

A first launch was simulated from a clean copy with no `.venv`, `.env` or
database. Migrations ran, the admin and three demo accounts were created, all
four logins succeeded, `/admin/` returned 200, token login returned 200, and a
second launch did not load the demo data again.

**Not verified on 8 November:** MariaDB was not running, so the tests were not
re-run on MariaDB and the automatic `CREATE DATABASE` step in `run.py` was not
exercised. Run `start.bat` with MariaDB running to confirm both.

## Screenshots

Retaken on 8 November 2026 from the demo data (the originals were lost with
the folder). The home page was rendered by Django and captured with headless
Chrome at 1366px wide and, for mobile, in a 390px-wide viewport. The mobile
capture shows the single-column layout with no horizontal overflow.

- [Desktop](screenshots/desktop.png)
- [Mobile](screenshots/mobile.png)
