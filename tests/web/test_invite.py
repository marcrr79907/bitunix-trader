"""R1 contract: invite creation — unique token, dup/expiry rejection, staff gate."""

from __future__ import annotations

from datetime import timedelta

import pytest
from accounts.forms import InviteForm
from accounts.models import Invite
from django.contrib.auth import get_user_model
from django.utils import timezone

INVITE_URL = "/accounts/invites/new/"


@pytest.mark.django_db
def test_token_is_unique_and_generated():
    first = Invite.objects.create(email="one@example.com")
    second = Invite.objects.create(email="two@example.com")
    assert first.token and second.token
    assert first.token != second.token
    assert len(first.token) >= 32
    assert first.used_at is None


@pytest.mark.django_db
def test_default_expiry_is_in_the_future():
    invite = Invite.objects.create(email="exp@example.com")
    assert invite.expires_at > timezone.now()
    assert invite.is_valid() is True


@pytest.mark.django_db
def test_duplicate_active_invite_rejected():
    Invite.objects.create(email="dup@example.com")
    form = InviteForm(data={"email": "dup@example.com", "role": "member"})
    assert not form.is_valid()
    assert "email" in form.errors
    assert Invite.objects.count() == 1


@pytest.mark.django_db
def test_used_invite_does_not_block_new_invite():
    Invite.objects.create(email="re@example.com", used_at=timezone.now())
    form = InviteForm(data={"email": "re@example.com", "role": "member"})
    assert form.is_valid()
    assert Invite.objects.count() == 1


@pytest.mark.django_db
def test_duplicate_active_invite_case_insensitive():
    """W2: case-variant emails must not coexist as two active invites."""
    Invite.objects.create(email="case@example.com")
    form = InviteForm(data={"email": "CASE@example.com", "role": "member"})
    assert not form.is_valid()
    assert "email" in form.errors


@pytest.mark.django_db
def test_past_expiry_rejected_at_creation():
    past = timezone.now() - timedelta(days=1)
    form = InviteForm(
        data={
            "email": "past@example.com",
            "role": "member",
            "expires_at": past.isoformat(),
        }
    )
    assert not form.is_valid()
    assert "expires_at" in form.errors


@pytest.mark.django_db
def test_member_forbidden_from_creating_invite(client):
    member = get_user_model().objects.create_user(
        email="member@example.com", password="s3cret-passw0rd"
    )
    client.force_login(member)
    response = client.post(INVITE_URL, {"email": "new@example.com", "role": "member"})
    assert response.status_code in (302, 403)
    assert not Invite.objects.exists()


@pytest.mark.django_db
def test_staff_can_create_invite(client):
    staff = get_user_model().objects.create_user(
        email="staff@example.com", password="s3cret-passw0rd", is_staff=True
    )
    client.force_login(staff)
    response = client.post(
        INVITE_URL, {"email": "invitee@example.com", "role": "member"}
    )
    # The view re-renders (200) with the shareable link instead of redirecting.
    assert response.status_code == 200
    invite = Invite.objects.get(email="invitee@example.com")
    assert invite.created_by == staff
    assert invite.used_at is None
    assert invite.expires_at > timezone.now()
