"""Search in the user's words (services.search_terms and the page "Hledat")."""

import pytest
from django.urls import reverse

from vocabulary import services


@pytest.fixture
def series(user, en, cs):
    english = services.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)
    show = services.create_deck(user, "Two and Half Men", parent=english)
    season = services.create_deck(user, "S01", parent=show)
    return services.create_deck(user, "E06", parent=season)


def words(hits):
    return [hit.term.main_foreign for hit in hits]


def marked(parts):
    return [text for text, match in parts if match]


def test_finds_word_and_translation_without_accents_and_case(user, series):
    services.add_term(series, foreign="trinket", native="Četka; tretka")
    services.add_term(series, foreign="cat", native="kočka")

    assert words(services.search_terms(user, "cetka")) == ["trinket"]
    assert words(services.search_terms(user, "TRIN")) == ["trinket"]
    hit = services.search_terms(user, "cetka")[0]
    # The match is marked in the original text, with its accent
    assert marked(hit.native) == ["Četka"]


def test_words_first_then_sentences_and_notes(user, series):
    services.add_term(series, foreign="impose", native="obtěžovat")
    services.add_term(
        series,
        foreign="trinket",
        native="cetka",
        context_sentence="I don't want to {impose}.",
    )
    services.add_term(series, foreign="bother", native="obtěžovat", note="like impose")

    hits = services.search_terms(user, "impose")

    assert words(hits) == ["impose", "bother", "trinket"]
    # In a sentence the braces are not shown
    assert marked(hits[2].found_in) == ["impose"]
    assert "".join(text for text, _ in hits[2].found_in) == "I don't want to impose."


def test_short_query_and_other_users_words(user, other_user, series, en, cs):
    services.add_term(series, foreign="trinket", native="cetka")
    other = services.create_deck(other_user, "Jiný", foreign_language=en, native_language=cs)
    services.add_term(other, foreign="trick", native="trik")

    assert services.search_terms(user, "t") == []
    assert words(services.search_terms(user, "tri")) == ["trinket"]


def test_hit_has_short_path_and_all_decks(user, series):
    deck_term = services.add_term(series, foreign="trinket", native="cetka")

    (hit,) = services.search_terms(user, "trinket")

    assert hit.deck_term == deck_term
    assert hit.paths[0]["short"] == "… › Two and Half Men › S01 › E06"
    assert hit.paths[0]["full"] == "Angličtina › Two and Half Men › S01 › E06"


def test_search_page_and_live_results(client, user, series):
    deck_term = services.add_term(series, foreign="trinket", native="cetka")
    client.force_login(user)
    url = reverse("vocabulary:search")

    page = client.get(url, {"q": "cetka"}).content.decode()
    live = client.get(url, {"q": "cetka"}, headers={"HX-Request": "true"}).content.decode()
    nothing = client.get(url, {"q": "zzz"}, headers={"HX-Request": "true"}).content.decode()

    assert "data-search-input" in page
    assert "<mark>cetka</mark>" in page
    assert "<html" not in live
    assert reverse("vocabulary:term_edit", args=[series.pk, deck_term.pk]) in live
    assert "se nic nenašlo" in nothing


def test_dashboard_has_the_search_field(client, user, series):
    client.force_login(user)

    html = client.get(reverse("dashboard")).content.decode()

    assert "data-search-input" in html
    assert reverse("vocabulary:search") in html


def test_edit_goes_back_where_it_was_opened(client, user, series):
    deck_term = services.add_term(series, foreign="trinket", native="cetka")
    client.force_login(user)
    edit = reverse("vocabulary:term_edit", args=[series.pk, deck_term.pk])
    detail = reverse("vocabulary:term_detail", args=[series.pk, deck_term.pk])

    # From the word page: the link carries the way back, saving and cancelling go there
    page = client.get(detail).content.decode()
    assert f"{edit}?next={detail}" in page
    response = client.post(f"{edit}?next={detail}", {"foreign": "trinket", "native": "cetka"})
    assert response.url == detail
    assert f'href="{detail}"' in client.get(f"{edit}?next={detail}").content.decode()

    # From the search on the dashboard
    live = client.get(
        reverse("vocabulary:search"),
        {"q": "cetka"},
        headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/"},
    ).content.decode()
    assert f'{edit}?next=/"' in live

    # Another site is never a way back
    response = client.post(
        f"{edit}?next=https://evil.example/", {"foreign": "trinket", "native": "cetka"}
    )
    assert response.url == reverse("vocabulary:deck_detail", args=[series.pk])
