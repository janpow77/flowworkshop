"""Privilegierte Rollen nie allein über die E-Mail-Adresse (Befund 24.09.2026)."""

import pytest

from routers.auth import PRIVILEGED_ROLES, privileged_without_password


@pytest.mark.parametrize("role", sorted(PRIVILEGED_ROLES))
def test_admin_and_moderator_without_password_are_rejected(role):
    assert privileged_without_password(role, None) is True
    assert privileged_without_password(role, "") is True


@pytest.mark.parametrize("role", sorted(PRIVILEGED_ROLES))
def test_admin_and_moderator_with_password_hash_pass_this_gate(role):
    assert privileged_without_password(role, "pbkdf2_sha256$1$salt$hash") is False


def test_participants_keep_email_only_login():
    assert privileged_without_password("participant", None) is False
