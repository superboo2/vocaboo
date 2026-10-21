import re
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from accounts.models import EmailVerification

User = get_user_model()

PASSWORD = "secret-pass-123"


def register(client, email="new@example.com", password=PASSWORD, **extra):
    data = {"email": email, "password1": password, "password2": password, **extra}
    return client.post(reverse("register"), data)


def code_from(mail):
    return re.search(r"\b(\d{6})\b", mail.body).group(1)


@pytest.mark.django_db
def test_register_page_is_public(client):
    response = client.get(reverse("register"))

    assert response.status_code == 200
    assert "Kód pozvánky" not in response.content.decode()


@pytest.mark.django_db
def test_login_page_links_to_register_and_password_reset(client):
    content = client.get(reverse("login")).content.decode()

    assert reverse("register") in content
    assert reverse("password_reset") in content


@pytest.mark.django_db
def test_register_creates_inactive_user_and_sends_code(client, mailoutbox):
    response = register(client, email="New@Example.com")

    assert response.status_code == 302
    assert response.url == reverse("verify_email")
    user = User.objects.get(email="new@example.com")
    assert not user.is_active
    assert user.check_password(PASSWORD)
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["new@example.com"]
    assert code_from(mailoutbox[0]) in mailoutbox[0].subject


@pytest.mark.django_db
def test_new_user_gets_the_language_of_the_page(client, cs):
    register(client)

    user = User.objects.get(email="new@example.com")
    assert user.ui_language == "cs"
    assert user.native_language == cs


@pytest.mark.django_db
def test_right_code_turns_on_the_account_and_logs_in(client, mailoutbox):
    register(client)

    response = client.post(reverse("verify_email"), {"code": code_from(mailoutbox[0])})

    assert response.status_code == 302
    assert response.url == reverse("dashboard")
    user = User.objects.get(email="new@example.com")
    assert user.is_active
    assert not EmailVerification.objects.filter(user=user).exists()
    assert client.get(reverse("dashboard")).status_code == 200


@pytest.mark.django_db
def test_code_with_a_space_works(client, mailoutbox):
    register(client)
    code = code_from(mailoutbox[0])

    client.post(reverse("verify_email"), {"code": f"{code[:3]} {code[3:]}"})

    assert User.objects.get(email="new@example.com").is_active


@pytest.mark.django_db
def test_wrong_code_shows_an_error(client, mailoutbox):
    register(client)
    wrong = "000000" if code_from(mailoutbox[0]) != "000000" else "111111"

    response = client.post(reverse("verify_email"), {"code": wrong})

    assert response.status_code == 200
    assert "Tenhle kód nesedí" in response.content.decode()
    assert not User.objects.get(email="new@example.com").is_active


@pytest.mark.django_db
def test_too_many_wrong_codes_block_the_code(client, mailoutbox, settings):
    register(client)
    code = code_from(mailoutbox[0])
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(settings.VERIFICATION_MAX_ATTEMPTS):
        client.post(reverse("verify_email"), {"code": wrong})

    response = client.post(reverse("verify_email"), {"code": code})

    assert "Moc špatných pokusů" in response.content.decode()
    assert not User.objects.get(email="new@example.com").is_active


@pytest.mark.django_db
def test_old_code_no_longer_works(client, mailoutbox, settings):
    register(client)
    EmailVerification.objects.update(
        sent_at=timezone.now() - timedelta(minutes=settings.VERIFICATION_CODE_MINUTES + 1)
    )

    response = client.post(reverse("verify_email"), {"code": code_from(mailoutbox[0])})

    assert "už neplatí" in response.content.decode()


@pytest.mark.django_db
def test_new_code_only_after_a_minute(client, mailoutbox):
    register(client)

    client.post(reverse("resend_code"))
    assert len(mailoutbox) == 1

    EmailVerification.objects.update(sent_at=timezone.now() - timedelta(minutes=2))
    client.post(reverse("resend_code"))
    assert len(mailoutbox) == 2

    # Only the newest code works
    client.post(reverse("verify_email"), {"code": code_from(mailoutbox[1])})
    assert User.objects.get(email="new@example.com").is_active


@pytest.mark.django_db
def test_verify_page_without_registration_goes_to_register(client):
    response = client.get(reverse("verify_email"))

    assert response.status_code == 302
    assert response.url == reverse("register")


@pytest.mark.django_db
def test_register_with_existing_email_looks_the_same_and_warns_the_owner(client, user, mailoutbox):
    response = register(client, email="Martin@Example.com", password="another-pass-456")

    assert response.status_code == 302
    assert response.url == reverse("verify_email")
    assert User.objects.filter(email__iexact="martin@example.com").count() == 1
    user.refresh_from_db()
    assert user.check_password("secret-pass-123")
    assert len(mailoutbox) == 1
    assert "/accounts/password-reset/" in mailoutbox[0].body


@pytest.mark.django_db
def test_register_again_before_confirming_keeps_one_account(client, mailoutbox):
    register(client)
    EmailVerification.objects.update(sent_at=timezone.now() - timedelta(minutes=2))

    register(client, password="another-pass-456")

    assert User.objects.filter(email="new@example.com").count() == 1
    assert User.objects.get(email="new@example.com").check_password("another-pass-456")
    assert len(mailoutbox) == 2


@pytest.mark.django_db
def test_passwords_must_match_and_follow_the_rules(client):
    response = client.post(
        reverse("register"),
        {"email": "new@example.com", "password1": "12345678", "password2": "12345678"},
    )

    assert response.status_code == 200
    assert not User.objects.filter(email="new@example.com").exists()

    response = register(client, password2="other-pass-456")
    assert "nejsou stejná" in response.content.decode()


@pytest.mark.django_db
def test_invitation_code_is_needed_when_set(client, settings, mailoutbox):
    settings.REGISTRATION_CODE = "Kamaradi"

    response = register(client, invitation="wrong")
    assert response.status_code == 200
    assert not User.objects.filter(email="new@example.com").exists()

    response = register(client, invitation=" kamaradi ")
    assert response.status_code == 302
    assert User.objects.filter(email="new@example.com").exists()


@pytest.mark.django_db
def test_robot_filling_the_hidden_field_gets_nothing(client, mailoutbox):
    response = register(client, website="http://spam.example.com")

    assert response.status_code == 200
    assert not User.objects.filter(email="new@example.com").exists()
    assert mailoutbox == []


@pytest.mark.django_db
def test_login_of_unconfirmed_account_sends_a_new_code(client, mailoutbox):
    register(client)
    EmailVerification.objects.update(sent_at=timezone.now() - timedelta(minutes=2))
    client.logout()

    response = client.post(reverse("login"), {"username": "new@example.com", "password": PASSWORD})

    assert response.status_code == 302
    assert response.url == reverse("verify_email")
    assert len(mailoutbox) == 2


@pytest.mark.django_db
def test_login_of_unconfirmed_account_with_wrong_password_says_nothing(client, mailoutbox):
    register(client)

    response = client.post(
        reverse("login"), {"username": "new@example.com", "password": "wrong-pass-999"}
    )

    assert response.status_code == 200
    assert len(mailoutbox) == 1


@pytest.mark.django_db
def test_password_reset_sends_a_link_that_sets_a_new_password(client, user, mailoutbox):
    response = client.post(reverse("password_reset"), {"email": "martin@example.com"})
    assert response.status_code == 302
    assert len(mailoutbox) == 1

    link = re.search(r"https?://[^/]+(/\S+)", mailoutbox[0].body).group(1)
    # The first visit moves the token into the session and redirects
    response = client.get(link)
    assert response.status_code == 302
    response = client.post(
        response.url, {"new_password1": "brand-new-pass-789", "new_password2": "brand-new-pass-789"}
    )

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password("brand-new-pass-789")


@pytest.mark.django_db
def test_password_reset_for_unknown_email_sends_nothing(client, mailoutbox):
    response = client.post(reverse("password_reset"), {"email": "nobody@example.com"})

    assert response.status_code == 302
    assert mailoutbox == []


@pytest.mark.django_db
def test_cleanup_deletes_old_unconfirmed_accounts_only(client, user, mailoutbox):
    register(client)
    register(client, email="fresh@example.com")
    User.objects.filter(email="new@example.com").update(
        date_joined=timezone.now() - timedelta(days=8)
    )
    # Turned off in the admin, not a new account: stays
    User.objects.filter(pk=user.pk).update(
        is_active=False, date_joined=timezone.now() - timedelta(days=30)
    )

    call_command("cleanup_unverified")

    assert not User.objects.filter(email="new@example.com").exists()
    assert User.objects.filter(email="fresh@example.com").exists()
    assert User.objects.filter(pk=user.pk).exists()
