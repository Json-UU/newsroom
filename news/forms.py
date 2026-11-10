"""Forms for registration, articles, newsletters and subscriptions."""
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q

from .models import Article, Newsletter, Publisher, User


class RegistrationForm(UserCreationForm):
    """Public sign-up form.

    ``role`` is deliberately not a field, so every new account is a
    reader and nobody can register as an editor or journalist.
    """

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]


def publisher_choices(user):
    """Return the publishers ``user`` may file content under.

    Journalists see publishers they belong to; editors also see the
    publishers they edit for.
    """
    query = Q(journalists=user)
    if user.is_editor:
        query |= Q(editors=user)
    return Publisher.objects.filter(query).distinct()


class ArticleForm(forms.ModelForm):
    """Write or edit an article; author and approval are set elsewhere."""

    class Meta:
        model = Article
        fields = ["title", "content", "publisher"]
        widgets = {"content": forms.Textarea(attrs={"rows": 14})}

    def __init__(self, *args, user, **kwargs):
        """Limit the publisher dropdown to the user's own publishers."""
        super().__init__(*args, **kwargs)
        self.fields["publisher"].queryset = publisher_choices(user)
        self.fields["publisher"].help_text = (
            "Leave blank to publish independently."
        )
        if self.instance.pk:
            # A content editor cannot reassign the author's publisher.
            self.fields["publisher"].disabled = True


class NewsletterForm(forms.ModelForm):
    """Curate a newsletter from approved articles."""

    class Meta:
        model = Newsletter
        fields = ["title", "description", "publisher", "articles"]
        widgets = {"articles": forms.CheckboxSelectMultiple}

    def __init__(self, *args, user, **kwargs):
        """Offer only the user's publishers and approved articles."""
        super().__init__(*args, **kwargs)
        self.fields["publisher"].queryset = publisher_choices(user)
        self.fields["articles"].queryset = Article.objects.filter(
            approved=True)
        if self.instance.pk:
            # The publisher is fixed once the newsletter exists.
            self.fields["publisher"].disabled = True


class SubscriptionForm(forms.ModelForm):
    """Let a reader pick the publishers and journalists they follow."""

    class Meta:
        model = User
        fields = ["publisher_subscriptions", "journalist_subscriptions"]
        widgets = {
            "publisher_subscriptions": forms.CheckboxSelectMultiple,
            "journalist_subscriptions": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        """Offer only active journalists as subscription choices."""
        super().__init__(*args, **kwargs)
        self.fields["journalist_subscriptions"].queryset = User.objects.filter(
            role=User.Role.JOURNALIST, is_active=True
        )
