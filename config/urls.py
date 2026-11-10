"""URL routes for the website, the REST API and authentication."""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.routers import DefaultRouter

from news import api, views

# The router generates the list/detail routes for each API viewset,
# e.g. /api/articles/ and /api/articles/<id>/.
router = DefaultRouter()
router.register("articles", api.ArticleViewSet, basename="api-article")
router.register(
    "newsletters",
    api.NewsletterViewSet,
    basename="api-newsletter")
router.register("publishers", api.PublisherViewSet, basename="api-publisher")
router.register(
    "journalists",
    api.JournalistViewSet,
    basename="api-journalist")

urlpatterns = [
    path("admin/", admin.site.urls),
    # Browser sign-in, sign-out and reader registration.
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/register/", views.register, name="register"),
    # Reader pages, journalist/editor workspace and article actions.
    path("", views.home, name="home"),
    path("subscriptions/", views.subscriptions, name="subscriptions"),
    path("feed/", views.feed, name="feed"),
    path("workspace/", views.workspace, name="workspace"),
    path("articles/new/", views.article_edit, name="article-create"),
    path("articles/<int:pk>/", views.article_detail, name="article"),
    path("articles/<int:pk>/edit/", views.article_edit, name="article-edit"),
    path("articles/<int:pk>/approve/", views.article_approve,
         name="article-approve"),
    path("articles/<int:pk>/delete/", views.delete_content,
         {"kind": "article"}, name="article-delete"),
    # Newsletter browsing, curation and sending.
    path("newsletters/", views.newsletters, name="newsletters"),
    path("newsletters/new/", views.newsletter_edit, name="newsletter-create"),
    path("newsletters/<int:pk>/", views.newsletter_detail, name="newsletter"),
    path("newsletters/<int:pk>/send/", views.newsletter_send,
         name="newsletter-send"),
    path("newsletters/<int:pk>/edit/", views.newsletter_edit,
         name="newsletter-edit"),
    path("newsletters/<int:pk>/delete/", views.delete_content,
         {"kind": "newsletter"}, name="newsletter-delete"),
    # API: token login (no session needed), the approval receipt
    # endpoint, then the router's resource endpoints.
    path("api/token/", ObtainAuthToken.as_view(authentication_classes=[]),
         name="api-token"),
    path("api/approved/", api.ApprovalLogView.as_view(), name="api-approved"),
    path("api/", include(router.urls)),
]
