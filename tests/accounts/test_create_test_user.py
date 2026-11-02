"""The command create_test_user: an account for trying the app, without registration."""

import io

import pytest
from django.core.management import CommandError, call_command

from accounts.models import User


def run(*args):
    out = io.StringIO()
    call_command("create_test_user", *args, stdout=out)
    return out.getvalue()


@pytest.fixture(autouse=True)
def debug(settings):
    settings.DEBUG = True


@pytest.mark.django_db
def test_each_call_takes_the_next_free_email():
    run()
    run()
    output = run()

    assert output.strip().endswith("test3@example.cz  (password: test3@example.cz)")
    user = User.objects.get(email="test3@example.cz")
    assert user.is_active
    assert user.check_password("test3@example.cz")
    assert user.native_language.code == "cs"


@pytest.mark.django_db
def test_a_deleted_number_is_used_again():
    run()
    run()
    User.objects.get(email="test1@example.cz").delete()

    assert "test1@example.cz" in run()


@pytest.mark.django_db
def test_language_and_email(lexicon):
    run("--email", "Me@Example.cz", "--language", "it", "--ui", "en")

    user = User.objects.get(email="me@example.cz")
    assert (user.native_language.code, user.ui_language) == ("it", "en")


@pytest.mark.django_db
def test_wrong_choices_are_refused():
    with pytest.raises(CommandError, match="Unknown language"):
        run("--language", "xx")
    with pytest.raises(CommandError, match="not translated"):
        run("--ui", "pt")
    run("--email", "a@example.cz")
    with pytest.raises(CommandError, match="already exists"):
        run("--email", "a@example.cz")


@pytest.mark.django_db
def test_only_with_debug(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DJANGO_DEBUG"):
        run()
    assert not User.objects.exists()
