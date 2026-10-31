"""The button ▶︎ Practice: a test at once, the cards picked by the settings."""

import random
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from study import services
from study.models import Direction, ReviewState, StudySession
from vocabulary import services as vocabulary

NOW = timezone.now()


@pytest.fixture
def logged_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def deck(user, en, cs):
    return vocabulary.create_deck(user, "Seriály", foreign_language=en, native_language=cs)


def add_words(deck, count):
    return [
        vocabulary.add_term(deck, foreign=f"{deck.name}{index}", native=f"slovo{index}").term
        for index in range(count)
    ]


def set_due(term, due_at, direction=Direction.F2N):
    ReviewState.objects.filter(term=term, direction=direction).update(
        due_at=due_at, last_reviewed_at=NOW - timedelta(days=5), last_interval=timedelta(days=1)
    )


def pick(user, deck, limit=5, direction="F2N"):
    return services.pick_practice_cards(
        user, [deck], direction, limit, now=NOW, rng=random.Random(1)
    )


def test_due_cards_come_first_the_oldest_first(user, deck):
    words = add_words(deck, 8)
    set_due(words[0], NOW - timedelta(hours=1))
    set_due(words[1], NOW - timedelta(days=3))

    cards = pick(user, deck)

    assert [card.term for card in cards[:2]] == [words[1], words[0]]


def test_due_and_new_then_up_to_the_limit_the_ones_coming_soon(user, deck):
    words = add_words(deck, 8)
    set_due(words[0], NOW - timedelta(days=1))
    for index, term in enumerate(words[1:]):
        set_due(term, NOW + timedelta(days=index + 1))
    # One new word is left (words[7] is set too, so add one more)
    new_word = add_words(vocabulary.create_deck(user, "Nová", parent=deck), 1)[0]

    cards = pick(user, deck, limit=5)

    assert len(cards) == 5
    assert cards[0].term == words[0] and cards[1].term == new_word
    # The rest are the ones coming soonest
    assert all(card.due_at > NOW for card in cards[2:])


def test_without_a_limit_only_due_and_new(user, deck):
    words = add_words(deck, 3)
    set_due(words[0], NOW + timedelta(days=1))

    assert len(pick(user, deck, limit=None)) == 2


def test_nothing_waiting_and_no_limit_takes_the_ones_coming_soon(user, deck):
    words = add_words(deck, 20)
    for index, term in enumerate(words):
        set_due(term, NOW + timedelta(days=index + 1))

    cards = pick(user, deck, limit=None)

    assert len(cards) == services.PRACTICE_FILL_WITHOUT_LIMIT


def test_a_word_comes_in_one_direction_when_there_are_enough_words(user, deck):
    words = add_words(deck, 6)
    for term in words:
        for direction in Direction.values:
            set_due(term, NOW + timedelta(days=1), direction)

    cards = pick(user, deck, limit=5, direction="MIXED")

    assert len({card.term_id for card in cards}) == 5
    # Too few words: both directions
    assert len(pick(user, deck, limit=10, direction="MIXED")) == 10


def test_practice_from_a_deck_tests_only_the_picked_cards(logged_client, user, deck):
    user.practice_cards = 3
    user.default_direction = "F2N"
    user.save()
    add_words(deck, 6)

    response = logged_client.post(reverse("study:practice"), {"deck": deck.pk})

    session = StudySession.objects.get()
    assert response.url == reverse("study:card", args=[session.pk])
    assert session.picked_cards.count() == 3 and list(session.decks.all()) == [deck]
    assert services.session_cards(session).count() == 3


def test_practice_from_the_bar_takes_all_decks(logged_client, user, deck, en, cs):
    other = vocabulary.create_deck(user, "Kniha", foreign_language=en, native_language=cs)
    child = vocabulary.create_deck(user, "Kapitola", parent=other)
    add_words(child, 1)

    logged_client.post(reverse("study:practice"))

    session = StudySession.objects.get()
    assert set(session.decks.all()) == {deck, other}
    assert session.picked_cards.count() == 2


def test_practice_without_words_says_so(logged_client, deck):
    response = logged_client.post(reverse("study:practice"), {"deck": deck.pk}, follow=True)

    assert not StudySession.objects.exists()
    assert "Zatím tu nejsou slovíčka k procvičení." in response.content.decode()


def test_practice_without_decks_opens_its_page(logged_client):
    response = logged_client.post(reverse("study:practice"))

    assert response.url == reverse("study:new")


def test_other_users_deck_cannot_be_practised(client, other_user, deck):
    add_words(deck, 2)
    client.force_login(other_user)

    assert client.post(reverse("study:practice"), {"deck": deck.pk}).status_code == 404


def test_a_card_that_was_not_picked_cannot_be_answered(logged_client, user, deck):
    user.practice_cards = 1
    user.default_direction = "F2N"
    user.save()
    add_words(deck, 2)
    logged_client.post(reverse("study:practice"), {"deck": deck.pk})
    session = StudySession.objects.get()
    other = ReviewState.objects.exclude(pk__in=session.picked_cards.all()).get(direction="F2N")

    response = logged_client.post(
        reverse("study:answer", args=[session.pk]),
        {"state": other.pk, "reviews_count": 0, "rating": "ok"},
    )

    assert response.status_code == 400


def test_line_under_the_deck_button(logged_client, user, deck):
    words = add_words(deck, 2)
    url = reverse("vocabulary:deck_detail", args=[deck.pk])

    html = logged_client.get(url).content.decode()
    # Both directions (the default): 2 words are 4 cards
    assert "4 kartičky" in html and "Nastavit" in html
    assert f"{reverse('study:new')}?deck={deck.pk}" in html
    assert "Vlastní test" not in html and "nic k opakování" not in html

    for term in words:
        for direction in Direction.values:
            set_due(term, NOW + timedelta(days=2), direction)
    assert "nic k opakování" in logged_client.get(url).content.decode()
    # With all cards nothing is missing
    user.practice_scope = "all"
    user.save()
    assert "nic k opakování" not in logged_client.get(url).content.decode()


def test_deck_without_words_has_no_practice_button(logged_client, deck):
    html = logged_client.get(reverse("vocabulary:deck_detail", args=[deck.pk])).content.decode()

    assert reverse("study:practice") not in html.split("</header>", 1)[1]


def page_data(**extra):
    return {
        "direction": "F2N",
        "scope": "due",
        "practice_cards": "20",
        **extra,
    }


def test_page_saves_the_choices_and_goes_back(logged_client, user, deck):
    response = logged_client.post(reverse("study:new"), page_data(deck=deck.pk))

    assert response.url == reverse("vocabulary:deck_detail", args=[deck.pk])
    assert not StudySession.objects.exists()
    user.refresh_from_db()
    assert (user.default_direction, user.practice_scope, user.practice_cards) == ("F2N", "due", 20)
    # The button of a deck does not change the decks of the bar button
    assert not user.practice_decks.exists()

    # An empty limit means no limit
    logged_client.post(reverse("study:new"), page_data(deck=deck.pk, practice_cards=""))
    user.refresh_from_db()
    assert user.practice_cards is None


def test_page_starts_the_test_and_saves(logged_client, user, deck):
    add_words(deck, 3)

    response = logged_client.post(
        reverse("study:new"), page_data(deck=deck.pk, scope="all", practice_cards="2", start="1")
    )

    session = StudySession.objects.get()
    assert response.url == reverse("study:card", args=[session.pk])
    # All cards: every card once, nothing picked, the limit as the most cards
    assert not session.picked_cards.exists() and services.session_cards(session).count() == 3
    assert session.max_cards == 2
    user.refresh_from_db()
    assert user.practice_scope == "all"


def test_page_from_the_bar_saves_the_decks(logged_client, user, deck, en, cs):
    other = vocabulary.create_deck(user, "Kniha", foreign_language=en, native_language=cs)
    add_words(deck, 1)
    add_words(other, 1)

    response = logged_client.post(reverse("study:new"), page_data(decks=[deck.pk]))

    assert response.url == reverse("dashboard")
    assert list(user.practice_decks.all()) == [deck]
    assert "Procvičit bere kartičky z: Seriály" in logged_client.get(response.url).content.decode()
    # The bar button takes only this deck now
    logged_client.post(reverse("study:practice"))
    assert list(StudySession.objects.get().decks.all()) == [deck]
    # The page has it ticked
    html = logged_client.get(reverse("study:new")).content.decode()
    assert f'value="{deck.pk}" checked' in html and f'value="{other.pk}" checked' not in html

    # All top decks ticked: saved as none, so a new deck is in too
    logged_client.post(reverse("study:new"), page_data(decks=[deck.pk, other.pk]))
    assert not user.practice_decks.exists()


def test_page_needs_a_deck(logged_client, user, deck):
    response = logged_client.post(reverse("study:new"), page_data(start="1"))

    assert "Vyber aspoň jeden slovník" in response.content.decode()
    assert not StudySession.objects.exists()


def test_page_refuses_other_users_deck(client, other_user, deck):
    client.force_login(other_user)

    assert client.get(reverse("study:new") + f"?deck={deck.pk}").status_code == 404
    client.post(reverse("study:new"), page_data(decks=[deck.pk], start="1"))
    assert not StudySession.objects.exists()


def test_settings_link_to_the_page(logged_client):
    html = logged_client.get(reverse("settings")).content.decode()

    assert f'href="{reverse("study:new")}"' in html
