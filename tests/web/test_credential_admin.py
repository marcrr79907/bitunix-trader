"""CP.1-CP.5 contract: staff credential admin, ciphertext at rest.

The admin is the provisioning surface for `ExchangeCredential`. It accepts
plaintext ONLY through write-only password inputs, funnels it through
`set_secrets` (the sole ciphertext writer), never renders plaintext back, and
never imports `credentials.decrypt`. These tests use a staff client and probe
the raw ciphertext column directly (tests live outside the scanned request
path).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from trading.models import ExchangeCredential

User = get_user_model()

CHANGELIST_URL = "/admin/trading/exchangecredential/"
ADD_URL = "/admin/trading/exchangecredential/add/"
ADMIN_PY = (
    Path(__file__).resolve().parent.parent.parent / "web" / "trading" / "admin.py"
)

# Obviously fake so secret scanners do not flag the fixtures.
PLAIN_KEY = "test-not-a-real-key"
PLAIN_SECRET = "test-not-a-real-secret"


@pytest.fixture
def fernet_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CREDENTIALS_FERNET_KEY", key)
    return key


@pytest.fixture
def staff(db):
    # Superuser implies is_staff and clears Django admin's per-model checks.
    return User.objects.create_superuser(
        email="staff-cred@example.com", password="pw-staff-12345"
    )


@pytest.fixture
def member(db):
    return User.objects.create_user(
        email="member-cred@example.com", password="pw-member-12345"
    )


def _change_url(pk):
    return f"/admin/trading/exchangecredential/{pk}/change/"


@pytest.mark.django_db
def test_staff_can_reach_credential_changelist(client, staff):
    # CP.1: staff gate admits the operator surface.
    client.force_login(staff)
    response = client.get(CHANGELIST_URL)
    assert response.status_code == 200


@pytest.mark.django_db
def test_non_staff_denied_and_sees_no_data(client, member, fernet_key):
    # CP.1: authenticated non-staff is redirected to admin login, no data leaks.
    cred = ExchangeCredential(user=member)
    cred.set_secrets(PLAIN_KEY, PLAIN_SECRET)
    cred.save()

    client.force_login(member)
    response = client.get(CHANGELIST_URL)
    assert response.status_code == 302
    assert response.url.startswith("/admin/login/")
    assert PLAIN_KEY.encode() not in response.content


@pytest.mark.django_db
def test_create_stores_ciphertext_not_plaintext(client, staff, fernet_key):
    # CP.2: create funnels plaintext through set_secrets; column is ciphertext.
    import credentials

    client.force_login(staff)
    response = client.post(
        ADD_URL,
        {
            "user": staff.pk,
            "label": "primary",
            "is_active": "on",
            "api_key": PLAIN_KEY,
            "api_secret": PLAIN_SECRET,
        },
    )
    assert response.status_code == 302

    cred = ExchangeCredential.objects.get()
    cred.refresh_from_db()
    assert cred.api_key_encrypted != PLAIN_KEY
    assert cred.api_secret_encrypted != PLAIN_SECRET
    assert credentials.decrypt(cred.api_key_encrypted) == PLAIN_KEY
    assert credentials.decrypt(cred.api_secret_encrypted) == PLAIN_SECRET


@pytest.mark.django_db
def test_change_page_renders_neither_plaintext_nor_ciphertext(
    client, staff, fernet_key
):
    # CP.2: plaintext is write-only; ciphertext columns are not editable fields.
    cred = ExchangeCredential(user=staff)
    cred.set_secrets(PLAIN_KEY, PLAIN_SECRET)
    cred.save()
    ciphertext = cred.api_key_encrypted

    client.force_login(staff)
    response = client.get(_change_url(cred.pk))
    assert response.status_code == 200
    assert PLAIN_KEY.encode() not in response.content
    assert PLAIN_SECRET.encode() not in response.content
    assert ciphertext.encode() not in response.content
    assert b"api_key_encrypted" not in response.content
    assert b"api_secret_encrypted" not in response.content


@pytest.mark.django_db
def test_create_with_blank_secrets_fails(client, staff, fernet_key):
    # CP.3: both secrets required on create; no row created.
    client.force_login(staff)
    response = client.post(
        ADD_URL,
        {"user": staff.pk, "label": "x", "api_key": "", "api_secret": ""},
    )
    assert response.status_code == 200  # re-rendered with errors
    assert ExchangeCredential.objects.count() == 0


@pytest.mark.django_db
def test_create_with_partial_secrets_fails(client, staff, fernet_key):
    # CP.3: exactly one of the pair is rejected on create.
    client.force_login(staff)
    response = client.post(
        ADD_URL,
        {"user": staff.pk, "label": "x", "api_key": PLAIN_KEY, "api_secret": ""},
    )
    assert response.status_code == 200
    assert ExchangeCredential.objects.count() == 0


@pytest.mark.django_db
def test_blank_edit_preserves_ciphertext(client, staff, fernet_key):
    # CP.3: both blank on edit keeps existing ciphertext untouched.
    cred = ExchangeCredential(user=staff, label="old")
    cred.set_secrets(PLAIN_KEY, PLAIN_SECRET)
    cred.save()
    before_key = cred.api_key_encrypted
    before_secret = cred.api_secret_encrypted

    client.force_login(staff)
    response = client.post(
        _change_url(cred.pk),
        {
            "user": staff.pk,
            "label": "renamed",
            "is_active": "on",
            "api_key": "",
            "api_secret": "",
        },
    )
    assert response.status_code == 302

    cred.refresh_from_db()
    assert cred.label == "renamed"
    assert cred.api_key_encrypted == before_key
    assert cred.api_secret_encrypted == before_secret


@pytest.mark.django_db
def test_partial_edit_rejected_and_ciphertext_unchanged(client, staff, fernet_key):
    # CP.3: exactly one secret on edit fails; stored ciphertext is unchanged.
    cred = ExchangeCredential(user=staff)
    cred.set_secrets(PLAIN_KEY, PLAIN_SECRET)
    cred.save()
    before_key = cred.api_key_encrypted
    before_secret = cred.api_secret_encrypted

    client.force_login(staff)
    response = client.post(
        _change_url(cred.pk),
        {
            "user": staff.pk,
            "label": "x",
            "is_active": "on",
            "api_key": "another-fake-key",
            "api_secret": "",
        },
    )
    assert response.status_code == 200

    cred.refresh_from_db()
    assert cred.api_key_encrypted == before_key
    assert cred.api_secret_encrypted == before_secret


@pytest.mark.django_db
def test_form_save_commit_true_persists_ciphertext(staff, fernet_key):
    # Covers the commit=True branch of form.save() (the admin calls it with
    # commit=False and re-saves; this exercises the standalone path directly).
    import credentials
    from trading.admin import ExchangeCredentialAdminForm

    form = ExchangeCredentialAdminForm(
        data={
            "user": staff.pk,
            "label": "direct",
            "is_active": "on",
            "api_key": PLAIN_KEY,
            "api_secret": PLAIN_SECRET,
        }
    )
    assert form.is_valid(), form.errors
    cred = form.save()

    cred.refresh_from_db()
    assert credentials.decrypt(cred.api_key_encrypted) == PLAIN_KEY
    assert credentials.decrypt(cred.api_secret_encrypted) == PLAIN_SECRET


def test_admin_module_does_not_reach_decrypt():
    # CP.4: the new admin module must not import or call decrypt.
    tree = ast.parse(ADMIN_PY.read_text(), filename=str(ADMIN_PY))
    offenders = [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.Attribute) and node.attr == "decrypt")
        or (isinstance(node, ast.Name) and node.id == "decrypt")
        or (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[-1] == "credentials"
            and any(alias.name == "decrypt" for alias in node.names)
        )
    ]
    assert offenders == []


def test_admin_module_has_no_unscoped_owned_query():
    # CP.5: no hand-written ExchangeCredential.objects.<verb>() in admin source.
    source = ADMIN_PY.read_text()
    assert re.search(r"ExchangeCredential\.objects\.", source) is None
