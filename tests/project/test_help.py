import pytest
from django.urls import reverse

from study.ratings import RATINGS

TOPICS = ["slovniky", "slovicka", "test", "prehled"]


@pytest.fixture
def logged_client(client, user):
    client.force_login(user)
    return client


def test_help_opens_first_tab(logged_client):
    response = logged_client.get(reverse("help_index"))

    assert response.url == reverse("help", args=["slovniky"])


@pytest.mark.parametrize("topic", TOPICS)
def test_help_tabs(logged_client, topic):
    html = logged_client.get(reverse("help", args=[topic])).content.decode()

    # All tabs are there, the current one is marked
    for other in TOPICS:
        assert reverse("help", args=[other]) in html
    assert f'href="{reverse("help", args=[topic])}" aria-current="page"' in html


def test_unknown_help_tab_gives_404(logged_client):
    assert logged_client.get(reverse("help", args=["nothing"])).status_code == 404


def test_help_table_of_buttons_comes_from_ratings(logged_client):
    html = logged_client.get(reverse("help", args=["test"])).content.decode()

    for rating in RATINGS:
        assert rating.emoji in html
        assert str(rating.label) in html
    assert "předchozí interval × 2,5" in html
    assert "vždy 10 min" in html
    assert "1 rok" in html


def test_help_link_in_navigation(logged_client):
    html = logged_client.get(reverse("dashboard")).content.decode()

    assert reverse("help_index") in html
    assert "Nápověda" in html


def test_help_needs_login(client, db):
    response = client.get(reverse("help", args=["test"]))

    assert response.url.startswith(reverse("login"))


@pytest.mark.parametrize("topic", TOPICS)
def test_help_comes_in_the_language_of_the_page(logged_client, user, topic):
    czech = logged_client.get(reverse("help", args=[topic])).content.decode()
    user.ui_language = "en"
    user.save()
    english = logged_client.get(reverse("help", args=[topic])).content.decode()

    assert "<h1>Nápověda</h1>" in czech
    assert "<h1>Help</h1>" in english
    # The frame is English too (the title and the tabs)
    assert "Nápověda" not in english


def test_help_falls_back_to_english(logged_client, settings):
    from django.utils import translation

    from config.views import help_page

    settings.LANGUAGES = [*settings.LANGUAGES, ("de", "Deutsch")]
    with translation.override("de"):
        request = logged_client.get(reverse("help", args=["test"])).wsgi_request
        response = help_page(request, "test")

    assert response.status_code == 200
