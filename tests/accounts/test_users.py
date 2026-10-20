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


@pytest.mark.django_db
def test_password_change_keeps_the_user_logged_in(client):
    user = User.objects.create_user(email="martin@example.com", password="secret-pass-123")
    client.force_login(user)

    page = client.get(reverse("password_change"))
    response = client.post(
        reverse("password_change"),
        {
            "old_password": "secret-pass-123",
            "new_password1": "new-ghost-pass-456",
            "new_password2": "new-ghost-pass-456",
        },
    )

    assert page.status_code == 200
    assert response.url == reverse("settings")
    user.refresh_from_db()
    assert user.check_password("new-ghost-pass-456")
    # Still logged in after the change
    assert client.get(reverse("settings")).status_code == 200


@pytest.mark.django_db
def test_password_change_needs_the_old_password(client):
    user = User.objects.create_user(email="martin@example.com", password="secret-pass-123")
    client.force_login(user)

    response = client.post(
        reverse("password_change"),
        {
            "old_password": "wrong-pass",
            "new_password1": "new-ghost-pass-456",
            "new_password2": "new-ghost-pass-456",
        },
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password("secret-pass-123")


@pytest.mark.django_db
def test_password_change_needs_login(client):
    response = client.get(reverse("password_change"))

    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_wrong_login_shows_red_error_and_red_fields(client):
    User.objects.create_user(email="martin@example.com", password="secret-pass-123")

    response = client.post(
        reverse("login"), {"username": "martin@example.com", "password": "wrong-pass"}
    )

    html = response.content.decode()
    assert response.status_code == 200
    assert '<p class="form-error" role="alert">' in html
    assert "E-mail nebo heslo není správně. Zkus to znovu." in html
    assert html.count('aria-invalid="true"') == 2
    # The cursor waits in the password field
    assert 'autofocus required id="id_password"' in html


@pytest.mark.django_db
def test_login_page_without_error_has_no_error_text(client):
    html = client.get(reverse("login")).content.decode()

    assert "form-error" not in html
    assert 'aria-invalid="true"' not in html


def test_password_rules_have_czech_texts():
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError) as error:
        validate_password("1234")

    assert error.value.messages == [
        "Heslo je moc krátké, potřebuje aspoň 8 znaků.",
        "Heslo je moc běžné, vymysli jiné.",
        "Heslo nemůže být jen z čísel.",
    ]


@pytest.mark.django_db
def test_language_of_the_account_wins_over_the_browser(client):
    user = User.objects.create_user(email="martin@example.com", password="secret-pass-123")
    user.ui_language = "en"
    user.save()
    client.force_login(user)

    html = client.get(reverse("settings"), HTTP_ACCEPT_LANGUAGE="cs").content.decode()

    assert '<html lang="en">' in html


@pytest.mark.django_db
def test_empty_language_follows_the_browser(client):
    user = User.objects.create_user(email="martin@example.com", password="secret-pass-123")
    client.force_login(user)

    html = client.get(reverse("settings"), HTTP_ACCEPT_LANGUAGE="en").content.decode()

    assert user.ui_language == ""
    assert '<html lang="en">' in html


@pytest.mark.django_db
def test_language_switch_works_without_login(client):
    response = client.post(reverse("set_language"), {"language": "en", "next": "/accounts/login/"})

    assert response.status_code == 302
    assert response.cookies["django_language"].value == "en"
    assert '<html lang="en">' in client.get(reverse("login")).content.decode()
    assert 'class="language-switch"' in client.get(reverse("login")).content.decode()


@pytest.mark.django_db
def test_settings_save_the_language_and_the_cookie(client):
    from vocabulary.models import Language

    user = User.objects.create_user(email="martin@example.com", password="secret-pass-123")
    client.force_login(user)

    response = client.post(
        reverse("settings"),
        {
            "ui_language": "en",
            "native_language": Language.objects.get(code="cs").pk,
            "default_direction": "N2F",
            "autoplay_content": "word",
        },
    )

    user.refresh_from_db()
    assert user.ui_language == "en"
    assert response.cookies["django_language"].value == "en"


@pytest.mark.django_db
def test_language_switch_names_each_language_in_itself(client):
    html = client.get(reverse("login"), HTTP_ACCEPT_LANGUAGE="es").content.decode()

    for name in ("Čeština", "English", "Español"):
        assert f">{name}</button>" in html
