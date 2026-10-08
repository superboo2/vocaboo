import pytest
from django.urls import reverse

from . import services
from .models import Deck


@pytest.fixture
def logged_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def english(user, en, cs):
    return services.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)


def test_create_root_deck(logged_client, en, cs):
    response = logged_client.post(
        reverse("vocabulary:deck_create"),
        {"name": "Angličtina", "foreign_language": en.pk, "native_language": cs.pk},
    )

    deck = Deck.objects.get()
    assert response.status_code == 302
    assert response.url == reverse("vocabulary:deck_detail", args=[deck.pk])
    assert deck.language_pair == "EN → CS"


def test_create_form_shows_error_for_same_languages(logged_client, cs):
    response = logged_client.post(
        reverse("vocabulary:deck_create"),
        {"name": "Čeština", "foreign_language": cs.pk, "native_language": cs.pk},
    )

    assert response.status_code == 200
    assert "musí být různé" in response.content.decode()
    assert not Deck.objects.exists()


def test_create_form_shows_error_for_duplicate_name(logged_client, english, en, cs):
    response = logged_client.post(
        reverse("vocabulary:deck_create"),
        {"name": "angličtina", "foreign_language": en.pk, "native_language": cs.pk},
    )

    assert response.status_code == 200
    assert "už tu existuje" in response.content.decode()


def test_native_language_is_prefilled(logged_client, user, cs):
    user.native_language = cs
    user.save()

    response = logged_client.get(reverse("vocabulary:deck_create"))

    assert response.context["form"].initial["native_language"] == cs


def test_dashboard_shows_tree(logged_client, english):
    services.create_deck(english.owner, "Seriály", parent=english)

    html = logged_client.get(reverse("dashboard")).content.decode()

    assert "Angličtina" in html
    assert "(EN → CS)" in html
    assert "Seriály" in html


def test_detail_shows_breadcrumbs_and_children(logged_client, english):
    series = services.create_deck(english.owner, "Seriály", parent=english)
    services.create_deck(english.owner, "HIMYM", parent=series)

    response = logged_client.get(reverse("vocabulary:deck_detail", args=[series.pk]))
    html = response.content.decode()

    assert response.status_code == 200
    assert reverse("vocabulary:deck_detail", args=[english.pk]) in html
    assert "HIMYM" in html


def test_other_users_deck_gives_404(client, other_user, english):
    client.force_login(other_user)

    for name in ["deck_detail", "deck_edit", "deck_move", "deck_delete", "deck_create_child"]:
        response = client.get(reverse(f"vocabulary:{name}", args=[english.pk]))
        assert response.status_code == 404, name


def test_create_child_deck(logged_client, english):
    response = logged_client.post(
        reverse("vocabulary:deck_create_child", args=[english.pk]),
        {"name": "Seriály"},
    )

    child = Deck.objects.get(name="Seriály")
    assert response.status_code == 302
    assert child.parent == english


def test_edit_deck(logged_client, english):
    logged_client.post(
        reverse("vocabulary:deck_edit", args=[english.pk]),
        {"name": "English", "description": "Moje angličtina"},
    )

    english.refresh_from_db()
    assert english.name == "English"
    assert english.description == "Moje angličtina"


def test_move_deck(logged_client, english):
    series = services.create_deck(english.owner, "Seriály", parent=english)
    films = services.create_deck(english.owner, "Filmy", parent=english)

    page = logged_client.get(reverse("vocabulary:deck_move", args=[films.pk])).content.decode()
    assert "Angličtina › Seriály" in page

    logged_client.post(reverse("vocabulary:deck_move", args=[films.pk]), {"target": series.pk})
    films.refresh_from_db()
    assert films.parent == series

    logged_client.post(reverse("vocabulary:deck_move", args=[films.pk]), {"target": ""})
    films.refresh_from_db()
    assert films.parent is None


def test_delete_needs_confirmation(logged_client, english):
    services.create_deck(english.owner, "Seriály", parent=english)
    url = reverse("vocabulary:deck_delete", args=[english.pk])

    page = logged_client.get(url).content.decode()
    assert "1 podslovník" in page
    assert Deck.objects.count() == 2

    response = logged_client.post(url)
    assert response.url == reverse("dashboard")
    assert Deck.objects.count() == 0


def test_reorder_with_htmx_returns_list(logged_client, english):
    services.create_deck(english.owner, "A", parent=english)
    b = services.create_deck(english.owner, "B", parent=english)

    response = logged_client.post(
        reverse("vocabulary:deck_reorder", args=[b.pk, "up"]),
        headers={"HX-Request": "true"},
    )

    html = response.content.decode()
    assert response.status_code == 200
    assert 'id="sibling-list"' in html
    assert "<html" not in html
    assert html.index(">B<") < html.index(">A<")


def test_reorder_without_htmx_redirects(logged_client, english):
    a = services.create_deck(english.owner, "A", parent=english)

    response = logged_client.post(reverse("vocabulary:deck_reorder", args=[a.pk, "down"]))

    assert response.status_code == 302
    assert response.url == reverse("vocabulary:deck_detail", args=[english.pk])


def test_reorder_needs_post(logged_client, english):
    response = logged_client.get(reverse("vocabulary:deck_reorder", args=[english.pk, "up"]))

    assert response.status_code == 405


def test_dashboard_tree_is_open_folders(logged_client, english):
    series = services.create_deck(english.owner, "Two and half men", parent=english)
    season = services.create_deck(english.owner, "Series 1", parent=series)
    services.create_deck(english.owner, "Episode 1", parent=season)

    html = logged_client.get(reverse("dashboard")).content.decode()

    # All levels are in the page and folders are open by default
    for name in ["Two and half men", "Series 1", "Episode 1"]:
        assert name in html
    assert html.count("<details open>") == 3
    assert "deck-icon-folder" in html
    assert "📄" in html


def place(client, deck, parent, index):
    url = reverse("vocabulary:deck_place", args=[deck.pk])
    return client.post(url, {"parent": parent.pk if parent else "", "index": index})


def test_place_view_moves_deck(logged_client, english):
    series = services.create_deck(english.owner, "series", parent=english)
    show = services.create_deck(english.owner, "Two and half men", parent=english)

    response = place(logged_client, show, series, 0)

    assert response.json() == {"ok": True}
    show.refresh_from_db()
    assert show.parent == series


def test_place_view_returns_error(logged_client, english):
    series = services.create_deck(english.owner, "series", parent=english)

    response = place(logged_client, english, series, 0)

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert "podslovníku" in response.json()["error"]


def test_place_view_needs_index(logged_client, english):
    url = reverse("vocabulary:deck_place", args=[english.pk])

    assert logged_client.post(url, {"parent": ""}).status_code == 400


def test_place_view_refuses_other_users_decks(client, other_user, english, en, cs):
    mine = services.create_deck(other_user, "Moje", foreign_language=en, native_language=cs)
    client.force_login(other_user)

    assert place(client, english, None, 0).status_code == 404
    assert place(client, mine, english, 0).status_code == 404


def test_dashboard_tree_has_data_for_drag_and_drop(logged_client, english):
    services.create_deck(english.owner, "Seriály", parent=english)

    html = logged_client.get(reverse("dashboard")).content.decode()

    # Every deck can be dropped on, every list knows its parent
    assert f'data-deck-id="{english.pk}"' in html
    assert f'data-parent-id="{english.pk}"' in html
    assert 'data-parent-id=""' in html
    assert "Sortable.min.js" in html
