"""Django admin registration for ``ExchangeCredential``.

Staff trusted surface (CP.1): the changelist intentionally lists **every user's**
credentials. This is a privileged operator zone guarded by Django's ``is_staff``
auth — analogous to the worker trusted zone (R14.4) — NOT the per-user
``for_user`` self-service rule. No ``get_queryset`` override is used; the admin
never imports ``credentials.decrypt``, so plaintext cannot leak even to staff.
Plaintext is accepted only through write-only password inputs and funnelled into
``ExchangeCredential.set_secrets``, the sole ciphertext writer.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin

from trading.models import ExchangeCredential


class ExchangeCredentialAdminForm(forms.ModelForm):
    """Write-only plaintext -> ``set_secrets`` on the existing Fernet boundary.

    ``api_key``/``api_secret`` are non-model fields with ``render_value=False``
    so they are never echoed back. The encrypted columns are excluded from
    ``Meta.fields`` — they are neither editable nor rendered.
    """

    api_key = forms.CharField(
        required=False, widget=forms.PasswordInput(render_value=False)
    )
    api_secret = forms.CharField(
        required=False, widget=forms.PasswordInput(render_value=False)
    )

    class Meta:
        model = ExchangeCredential
        fields = ("user", "label", "is_active")

    def clean(self):
        data = super().clean()
        key, secret = data.get("api_key"), data.get("api_secret")
        if bool(key) != bool(secret):
            raise forms.ValidationError(
                "Provide both api_key and api_secret, or leave both blank."
            )
        if not self.instance.pk and not key:
            raise forms.ValidationError("api_key and api_secret are required.")
        return data

    def save(self, commit: bool = True) -> ExchangeCredential:
        instance = super().save(commit=False)
        if self.cleaned_data.get("api_key"):
            instance.set_secrets(
                self.cleaned_data["api_key"], self.cleaned_data["api_secret"]
            )
        if commit:
            instance.save()
        return instance


@admin.register(ExchangeCredential)
class ExchangeCredentialAdmin(admin.ModelAdmin):
    form = ExchangeCredentialAdminForm
    list_display = ("label", "user", "is_active", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    search_fields = ("label", "user__email")
    list_filter = ("is_active",)
