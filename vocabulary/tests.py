import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse

from .models import Language

User = get_user_model()


@pytest.mark.django_db
def test_initial_languages_exist():
    codes = set(Language.objects.values_list("code", flat=True))

    assert {"cs", "en", "es"} <= codes
    assert Language.objects.get(code="cs").name == "Čeština"


@pytest.mark.django_db
def test_languages_are_ordered_by_name():
    names = list(Language.objects.values_list("name", flat=True))

    assert names == sorted(names)


@pytest.mark.parametrize("code", ["cs", "de"])
def test_valid_language_code(code):
    Language(code=code, name="X").full_clean(validate_unique=False)


@pytest.mark.parametrize("code", ["CZ", "cze", "c", "c1", ""])
def test_invalid_language_code(code):
    with pytest.raises(ValidationError):
        Language(code=code, name="X").full_clean(validate_unique=False)


@pytest.mark.django_db
def test_language_code_is_unique():
    with pytest.raises(IntegrityError):
        Language.objects.create(code="cs", name="Czech again")


@pytest.mark.django_db
def test_search_ignores_accents():
    # Needs the unaccent extension created by the first migration
    assert Language.objects.filter(name__unaccent__iexact="cestina").exists()
    assert Language.objects.filter(name__unaccent__icontains="spanel").exists()


@pytest.mark.django_db
def test_user_native_language_is_optional():
    user = User.objects.create_user(email="martin@example.com", password="secret-pass-123")
    assert user.native_language is None

    user.native_language = Language.objects.get(code="cs")
    user.save()
    user.refresh_from_db()
    assert user.native_language.code == "cs"


@pytest.mark.django_db
def test_admin_language_pages_work(client):
    admin = User.objects.create_superuser(email="admin@example.com", password="secret-pass-123")
    client.force_login(admin)
    czech = Language.objects.get(code="cs")

    assert client.get(reverse("admin:vocabulary_language_changelist")).status_code == 200
    assert client.get(reverse("admin:vocabulary_language_add")).status_code == 200
    change_url = reverse("admin:vocabulary_language_change", args=[czech.pk])
    assert client.get(change_url).status_code == 200
