"""Invite + token-signup forms."""

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Invite

User = get_user_model()


class InviteForm(forms.ModelForm):
    """Staff-facing: create an invite; reject duplicate active or past expiry.

    `expires_at` is optional — leaving it blank applies the model default (now + 7d).
    """

    expires_at = forms.DateTimeField(required=False)

    class Meta:
        model = Invite
        fields = ("email", "role", "expires_at")

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower()
        if Invite.objects.filter(
            email__iexact=email, used_at__isnull=True, expires_at__gt=timezone.now()
        ).exists():
            raise forms.ValidationError(
                "An active invite already exists for this email."
            )
        return email

    def clean_expires_at(self):
        expires_at = self.cleaned_data.get("expires_at")
        if expires_at is not None and expires_at <= timezone.now():
            raise forms.ValidationError("Expiry must be in the future.")
        return expires_at

    def save(self, commit: bool = True) -> Invite:
        invite = super().save(commit=False)
        if self.cleaned_data.get("expires_at") is None:
            invite.expires_at = Invite._meta.get_field("expires_at").get_default()
        if commit:
            invite.save()
        return invite


class SignupForm(forms.Form):
    """Visitor-facing: set a password for an invite token."""

    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            raise forms.ValidationError("Passwords do not match.")
        return data
