import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
def test_create_user_with_email():
    user = User.objects.create_user(email="martin@example.com", password="secret-pass-123")

    assert user.email == "martin@example.com"
    assert user.check_password("secret-pass-123")
    assert not user.is_staff
    assert not user.is_superuser


@pytest.mark.django_db
def test_create_user_without_email_fails():
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="secret-pass-123")


@pytest.mark.django_db
def test_create_superuser():
    user = User.objects.create_superuser(email="admin@example.com", password="secret-pass-123")

    assert user.is_staff
    assert user.is_superuser


@pytest.mark.django_db
def test_email_is_unique_ignoring_letter_case():
    User.objects.create_user(email="martin@example.com", password="secret-pass-123")

    with pytest.raises(IntegrityError):
        User.objects.create_user(email="Martin@Example.com", password="secret-pass-123")


@pytest.mark.django_db
def test_anonymous_user_is_redirected_to_login(client):
    response = client.get(reverse("dashboard"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_login_page_is_public(client):
    response = client.get(reverse("login"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_login_with_email_in_other_letter_case(client):
    User.objects.create_user(email="martin@example.com", password="secret-pass-123")

    response = client.post(
        reverse("login"),
        {"username": "Martin@Example.com", "password": "secret-pass-123"},
    )

    assert response.status_code == 302
    assert response.url == reverse("dashboard")


@pytest.mark.django_db
def test_admin_user_pages_work(client):
    admin = User.objects.create_superuser(email="admin@example.com", password="secret-pass-123")
    client.force_login(admin)

    assert client.get(reverse("admin:accounts_user_changelist")).status_code == 200
    assert client.get(reverse("admin:accounts_user_add")).status_code == 200
    assert client.get(reverse("admin:accounts_user_change", args=[admin.pk])).status_code == 200


@pytest.mark.django_db
def test_settings_page_saves_preferences(client):
    from vocabulary.models import Language

    user = User.objects.create_user(email="martin@example.com", password="secret-pass-123")
    client.force_login(user)
    czech = Language.objects.get(code="cs")

    page = client.get(reverse("settings"))
    response = client.post(
        reverse("settings"),
        {
            "native_language": czech.pk,
            "default_direction": "N2F",
            "autoplay_pronunciation": "on",
            "autoplay_content": "sentence",
        },
    )

    assert page.status_code == 200
    # Suggestions are on for a new user, the check box is ticked
    assert 'id="id_show_suggestions" checked' in page.content.decode()
    assert response.url == reverse("settings")
    user.refresh_from_db()
    assert user.native_language == czech
    assert user.default_direction == "N2F"
    # The check box was not sent, so the suggestions are off now
    assert user.show_suggestions is False
    assert (user.autoplay_pronunciation, user.autoplay_content) == (True, "sentence")


@pytest.mark.django_db
def test_settings_link_in_navigation(client):
    user = User.objects.create_user(email="martin@example.com", password="secret-pass-123")
    client.force_login(user)

    assert reverse("settings") in client.get(reverse("dashboard")).content.decode()
