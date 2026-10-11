"""Home landing, invite creation (staff-only) and token-gated signup."""

from __future__ import annotations

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.forms import InviteForm, SignupForm
from accounts.models import Invite

User = get_user_model()


@require_http_methods(["GET"])
def home(request: HttpRequest) -> HttpResponse:
    """Landing: anonymous goes to login, authenticated sees the home page.

    Also the target of LOGIN_REDIRECT_URL, so it must never 404 (it did before
    this view existed).
    """
    if not request.user.is_authenticated:
        return redirect("login")
    return render(request, "accounts/home.html", {"user": request.user})


@login_required
@require_http_methods(["GET", "POST"])
def invite_create(request: HttpRequest) -> HttpResponse:
    if not request.user.is_staff:
        raise PermissionDenied
    signup_url = None
    if request.method == "POST":
        form = InviteForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.created_by = request.user
            invite.save()
            # Show the shareable link instead of redirecting away, so the
            # inviter can copy it without opening the Django admin.
            signup_url = request.build_absolute_uri(
                reverse("signup", args=[invite.token])
            )
            form = InviteForm()
    else:
        form = InviteForm()
    return render(
        request,
        "accounts/invite_create.html",
        {"form": form, "signup_url": signup_url},
    )


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


@require_http_methods(["GET"])
def theme_css(request: HttpRequest) -> HttpResponse:
    """Serve the design-system stylesheet same-origin as text/css (public).

    A stylesheet protects nothing; gating it would 302 the login page's CSS.
    Mirrors ``market.views.chart_js`` (no staticfiles in prod, zero build).
    """
    return HttpResponse(
        render(request, "registration/theme.css").content,
        content_type="text/css",
    )


@require_http_methods(["GET"])
def invite_js(request: HttpRequest) -> HttpResponse:
    """Same-origin JS for the invite page (replaces the inline onclick)."""
    return HttpResponse(
        render(request, "accounts/invite.js").content,
        content_type="text/javascript",
    )
