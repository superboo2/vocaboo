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
