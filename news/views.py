"""Server-rendered browsing, subscriptions and editorial workspace.

Access control uses ``login_required`` for signed-in pages and the
shared ``news.access`` rules for per-object checks. A failed check raises
``PermissionDenied`` (HTTP 403) or returns 404 for hidden drafts.
"""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .access import (
    can_manage, editorial_scope, subscribed_articles, visible_articles,
)
from .forms import (
    ArticleForm, NewsletterForm, RegistrationForm, SubscriptionForm,
)
from .models import Article, Newsletter, User
from .services import approve_article, save_article_changes, send_newsletter


def home(request):
    """List approved articles, with an optional title/content search."""
    articles = Article.objects.filter(approved=True).select_related(
        "author", "publisher")
    query = request.GET.get("q", "").strip()
    if query:
        articles = articles.filter(Q(title__icontains=query)
                                   | Q(content__icontains=query))
    return render(request, "news/home.html", {
        # get_page() falls back to a valid page for bad page numbers.
        "page_obj": Paginator(articles, 9).get_page(request.GET.get("page")),
        "query": query, "heading": "Independent voices. Informed readers.",
    })


def register(request):
    """Sign up a new reader, log them in and send them to subscriptions.

    Public registration always creates a reader; other roles are assigned
    by an administrator.
    """
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(
            request,
            "Welcome. Choose your subscriptions to get started.")
        return redirect("subscriptions")
    return render(request,
                  "news/form.html",
                  {"form": form,
                   "heading": "Create your reader account",
                   "button": "Register",
                   })


@login_required
def subscriptions(request):
    """Let a reader choose the publishers and journalists they follow."""
    if request.user.role != User.Role.READER:
        raise PermissionDenied("Only readers can subscribe.")
    form = SubscriptionForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your subscriptions have been saved.")
        return redirect("feed")
    return render(request, "news/form.html", {
        "form": form, "heading": "Follow the voices you trust",
        "button": "Save subscriptions",
    })


@login_required
def feed(request):
    """Show a reader the approved articles from their subscriptions."""
    if request.user.role != User.Role.READER:
        raise PermissionDenied
    return render(request, "news/home.html", {
        "page_obj": Paginator(subscribed_articles(request.user), 9).get_page(
            request.GET.get("page")), "heading": "Your reading list",
        "personal_feed": True,
    })


def article_detail(request, pk):
    """Show one article, with edit/approve controls for staff.

    Drafts the user may not see return 404, so their existence is not
    revealed.
    """
    article = get_object_or_404(visible_articles(request.user), pk=pk)
    user = request.user
    manageable = can_manage(user, article)
    return render(request, "news/article.html", {
        "article": article, "manageable": manageable,
        # Editors cannot approve articles they wrote themselves.
        "can_approve": (
            user.is_authenticated and user.is_editor and manageable
            and article.author_id != user.pk),
        # Delivery status for the current revision (for retry messages).
        "delivery": article.deliveries.filter(
            revision=article.revision).first(),
    })


@login_required
def workspace(request):
    """List the articles a journalist wrote or an editor oversees."""
    user = request.user
    if user.is_editor:
        articles = Article.objects.filter(editorial_scope(user)).distinct()
    elif user.role == User.Role.JOURNALIST:
        articles = Article.objects.filter(author=user)
    else:
        # Readers have no workspace.
        raise PermissionDenied
    return render(
        request, "news/workspace.html", {
            "page_obj": Paginator(
                articles.select_related(
                    "author", "publisher"), 20) .get_page(
                request.GET.get("page")), })


@login_required
def article_edit(request, pk=None):
    """Create an article (journalists) or edit one (author/editor).

    Saving always sends the article for editorial review.
    """
    article = get_object_or_404(Article, pk=pk) if pk else Article(
        author=request.user)
    if pk:
        if not can_manage(request.user, article):
            raise PermissionDenied
    elif request.user.role != User.Role.JOURNALIST:
        raise PermissionDenied("Only journalists may submit articles.")
    form = ArticleForm(
        request.POST or None,
        instance=article,
        user=request.user)
    if request.method == "POST" and form.is_valid():
        if pk:
            # Edits go through the service so approval is reset safely.
            article = save_article_changes(article, {
                key: form.cleaned_data[key] for key in form.Meta.fields
            })
        else:
            article = form.save()
        messages.success(
            request,
            "Article saved and awaiting editorial approval.")
        return redirect("article", pk=article.pk)
    return render(request, "news/form.html", {
        "form": form, "heading": "Edit article" if pk else "Write an article",
        "button": "Save for review",
    })


@login_required
@require_POST
def article_approve(request, pk):
    """Approve an article (editors only) and report notification status.

    This is the brief's option 2: the approval view triggers the email and
    the ``/api/approved/`` POST through ``approve_article``. POST-only so a
    link or prefetch cannot approve an article by accident.
    """
    # 404 for a missing article before the permission check runs.
    get_object_or_404(Article, pk=pk)
    article = approve_article(pk, request.user)
    delivery = article.deliveries.get(revision=article.revision)
    if delivery.last_error:
        # Approved, but a channel failed; the page offers a retry.
        messages.warning(request, "Published. " + delivery.last_error)
    else:
        messages.success(
            request,
            "Article approved; subscribers notified and API logged.")
    return redirect("article", pk=pk)


@login_required
def delete_content(request, kind, pk):
    """Confirm (GET) and delete (POST) an article or newsletter.

    ``kind`` comes from the URL configuration, not from user input.
    """
    model = Article if kind == "article" else Newsletter
    item = get_object_or_404(model, pk=pk)
    if not can_manage(request.user, item):
        raise PermissionDenied
    if request.method == "POST":
        item.delete()
        messages.success(request, "Deleted successfully.")
        return redirect("workspace")
    return render(request, "news/delete.html", {"item": item})


def newsletters(request):
    """List all newsletters for anyone to browse."""
    issues = Newsletter.objects.select_related("author", "publisher")
    return render(request, "news/newsletters.html", {
        "page_obj": Paginator(issues, 12).get_page(request.GET.get("page")),
    })


def newsletter_detail(request, pk):
    """Show a newsletter and only its currently approved articles."""
    issue = get_object_or_404(Newsletter, pk=pk)
    return render(request, "news/newsletter.html", {
        "issue": issue, "articles": issue.articles.filter(approved=True),
        "manageable": can_manage(request.user, issue),
    })


@login_required
def newsletter_edit(request, pk=None):
    """Create a newsletter (journalist/editor) or edit one (owner/editor)."""
    issue = get_object_or_404(Newsletter, pk=pk) if pk else Newsletter(
        author=request.user)
    user = request.user
    if pk and not can_manage(user, issue):
        raise PermissionDenied
    if not pk and user.role != User.Role.JOURNALIST and not user.is_editor:
        raise PermissionDenied
    form = NewsletterForm(request.POST or None, instance=issue, user=user)
    if request.method == "POST" and form.is_valid():
        issue = form.save()
        messages.success(request, "Newsletter saved.")
        return redirect("newsletter", pk=issue.pk)
    return render(request,
                  "news/form.html",
                  {"form": form,
                   "heading": "Curate a newsletter",
                   "button": "Save newsletter",
                   })


@login_required
@require_POST
def newsletter_send(request, pk):
    """Email a newsletter to subscribers, reporting any failure."""
    issue = get_object_or_404(Newsletter, pk=pk)
    if not can_manage(request.user, issue):
        raise PermissionDenied
    try:
        count = send_newsletter(issue, request.user)
    except ValueError as exc:
        # The issue has no approved stories; show the reason.
        messages.warning(request, str(exc))
    except Exception:
        # Mail backend errors are shown as a friendly message.
        messages.error(request, "Email delivery failed. Check email settings.")
    else:
        messages.success(
            request,
            f"Newsletter emailed to {count} subscribers.")
    return redirect("newsletter", pk=pk)
