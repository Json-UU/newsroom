"""Django admin configuration for provisioning users and publishers."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    ApprovalDelivery, ApprovalLog, Article, Newsletter, Publisher, User,
)


@admin.register(User)
class NewsUserAdmin(UserAdmin):
    """User admin with the newsroom role and subscription fields added."""

    fieldsets = UserAdmin.fieldsets + (
        ("Newsroom", {"fields": ("role", "publisher_subscriptions",
                                 "journalist_subscriptions")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Newsroom", {"fields": ("email", "role")}),
    )
    list_display = ["username", "email", "role", "is_staff"]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Read-only article list; editing happens in the application."""

    list_display = ["title", "author", "publisher", "approved", "revision"]

    def has_add_permission(self, request):
        """Articles are created by journalists in the application."""
        return False

    def has_change_permission(self, request, obj=None):
        """Block admin edits so approval cannot skip notifications."""
        # All content edits/approval go through the tested workflow.
        return False


admin.site.register(Publisher)
admin.site.register(Newsletter)


@admin.register(ApprovalDelivery, ApprovalLog)
class IntegrationAdmin(admin.ModelAdmin):
    """Read-only view of delivery records and API receipts."""

    def has_add_permission(self, request):
        """Records are written only by the approval workflow."""
        return False

    def has_change_permission(self, request, obj=None):
        """Records are an audit trail and cannot be edited."""
        return False
