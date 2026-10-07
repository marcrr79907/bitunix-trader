"""Invite creation (staff-only) and token-gated signup."""

from __future__ import annotations

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.forms import InviteForm, SignupForm
from accounts.models import Invite

User = get_user_model()


@login_required
@require_http_methods(["GET", "POST"])
def invite_create(request: HttpRequest) -> HttpResponse:
    if not request.user.is_staff:
        raise PermissionDenied
    if request.method == "POST":
        form = InviteForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.created_by = request.user
            invite.save()
            return redirect("invite_create")
    else:
        form = InviteForm()
    return render(request, "accounts/invite_create.html", {"form": form})


@require_http_methods(["GET", "POST"])
def signup(request: HttpRequest, token: str) -> HttpResponse:
    invite = Invite.objects.filter(token=token).first()
    if invite is None or not invite.is_valid():
        raise Http404
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            email = invite.email.lower()
            # W1: an invite for an existing account must not crash or duplicate.
            if User.objects.filter(email=email).exists():
                raise Http404
            password = form.cleaned_data["password1"]
            # W4: enforce the project's password validators, not just length.
            try:
                password_validation.validate_password(password)
            except ValidationError as exc:
                form.add_error("password1", exc)
                return render(
                    request, "accounts/signup.html", {"form": form, "invite": invite}
                )
            # W3: consume the token and create the user in one transaction.
            with transaction.atomic():
                locked = Invite.objects.select_for_update().get(pk=invite.pk)
                if not locked.is_valid():
                    raise Http404
                User.objects.create_user(
                    email=email, password=password, role=locked.role
                )
                locked.used_at = timezone.now()
                locked.save(update_fields=["used_at"])
            return redirect("login")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form, "invite": invite})
