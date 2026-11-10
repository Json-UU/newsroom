Using The Newsroom
==================

Roles
-----

Reader
   Browses approved articles and newsletters, subscribes to publishers and
   journalists, and sees matching stories under **My feed**.

Journalist
   Writes articles and newsletters in the **Workspace**. An article is
   independent when no publisher is chosen.

Editor
   Reviews drafts in their scope (independent content and content from
   their publishers) and clicks **Approve and publish**.

Administrator
   Manages users, roles and publishers at ``/admin/``.

Publishing workflow
-------------------

1. A journalist saves an article for review. Only its author and the
   responsible editors can open the draft.
2. An editor approves it. The article becomes public, subscribers are
   emailed, and the approval is logged to ``/api/approved/``
   (see :func:`news.services.approve_article`).
3. If an email or API call fails, the article stays published and the
   article page offers **Retry notifications**.
4. Editing a published article sends it back for review
   (see :func:`news.services.save_article_changes`).

REST API
--------

All API endpoints require authentication with a token
(``Authorization: Token <key>``) or a browser session. List responses are
paginated, 20 items per page. See :mod:`news.api` for the endpoints and
:mod:`news.serializers` for the fields returned.

Running the project
-------------------

Setup steps for a virtual environment and for Docker are in the
``README.md`` file at the root of the repository.
