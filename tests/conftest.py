"""Shared pytest fixtures for all apps."""

import pytest
from django.contrib.auth import get_user_model

from vocabulary.models import Language


@pytest.fixture(autouse=True)
def fast_password_hasher(settings):
    # Real password hashing is slow on purpose; tests do not need it
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        email="martin@example.com", password="secret-pass-123"
    )


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(
        email="other@example.com", password="secret-pass-123"
    )


@pytest.fixture
def cs(db):
    return Language.objects.get(code="cs")


@pytest.fixture
def en(db):
    return Language.objects.get(code="en")


@pytest.fixture
def es(db):
    return Language.objects.get(code="es")
