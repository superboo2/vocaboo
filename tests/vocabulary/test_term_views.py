import pytest
from django.urls import reverse

from vocabulary import services
from vocabulary.models import DeckTerm, Term


@pytest.fixture
def logged_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def himym(user, en, cs):
    english = services.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)
    return services.create_deck(user, "HIMYM", parent=english)


def add_url(deck):
    return reverse("vocabulary:term_add", args=[deck.pk])


def test_deck_page_shows_form_with_languages(logged_client, himym):
    html = logged_client.get(reverse("vocabulary:deck_detail", args=[himym.pk])).content.decode()

    assert 'id="term-form"' in html
    assert "Angličtina (EN)" in html
    assert "Čeština (CS)" in html


def test_add_term_with_htmx(logged_client, himym):
    response = logged_client.post(
        add_url(himym),
        {"foreign": "hello; hi", "native": "ahoj"},
        headers={"HX-Request": "true"},
    )
    html = response.content.decode()

    assert response.status_code == 200
    assert Term.objects.get().main_foreign == "hello"
    # Fresh form, cursor in the first field
    assert 'id="term-form"' in html
    assert "autofocus" in html
    # Updated list comes "out of band"
    assert 'hx-swap-oob="true"' in html
    assert "hello" in html
    assert "<html" not in html


def test_add_term_error_keeps_values(logged_client, himym):
    response = logged_client.post(
        add_url(himym),
        {"foreign": "hello", "native": ""},
        headers={"HX-Request": "true"},
    )
    html = response.content.decode()

    assert response.status_code == 200
    assert not Term.objects.exists()
    assert 'value="hello"' in html


def test_add_duplicate_shows_message(logged_client, himym):
    services.add_term(himym, foreign="hello", native="ahoj")

    response = logged_client.post(
        add_url(himym), {"foreign": "Hello", "native": "ahoj"}, headers={"HX-Request": "true"}
    )

    assert "už máš" in response.content.decode()
    assert Term.objects.count() == 1


def test_add_term_without_htmx_redirects(logged_client, himym):
    response = logged_client.post(add_url(himym), {"foreign": "hello", "native": "ahoj"})

    assert response.status_code == 302
    assert response.url == reverse("vocabulary:deck_detail", args=[himym.pk])
    assert Term.objects.count() == 1


def test_deck_page_lists_words(logged_client, himym):
    services.add_term(
        himym, foreign="hello; hi", native="ahoj; čau", context_sentence="Hello, kids."
    )

    html = logged_client.get(reverse("vocabulary:deck_detail", args=[himym.pk])).content.decode()

    assert "hello" in html
    assert "· hi" in html
    assert "ahoj · čau" in html
    assert "<mark>Hello</mark>, kids." in html


def test_edit_term(logged_client, himym):
    deck_term = services.add_term(himym, foreign="hello", native="ahoj")
    url = reverse("vocabulary:term_edit", args=[himym.pk, deck_term.pk])

    assert 'value="hello"' in logged_client.get(url).content.decode()
    response = logged_client.post(
        url,
        {"foreign": "hello; hi", "native": "ahoj", "context_sentence": "Hi!"},
    )

    assert response.status_code == 302
    deck_term.refresh_from_db()
    assert deck_term.context_sentence == "Hi!"
    assert Term.objects.get().main_foreign == "hello"


def test_remove_term_deletes_last_copy(logged_client, himym):
    deck_term = services.add_term(himym, foreign="hello", native="ahoj")
    url = reverse("vocabulary:term_remove", args=[himym.pk, deck_term.pk])

    assert "smaže úplně" in logged_client.get(url).content.decode()
    logged_client.post(url)

    assert not Term.objects.exists()


def test_word_of_other_user_gives_404(client, other_user, himym):
    deck_term = services.add_term(himym, foreign="hello", native="ahoj")
    client.force_login(other_user)

    for name in ["term_edit", "term_remove"]:
        url = reverse(f"vocabulary:{name}", args=[himym.pk, deck_term.pk])
        assert client.get(url).status_code == 404
    assert client.post(add_url(himym), {"foreign": "x", "native": "y"}).status_code == 404


def test_word_must_belong_to_the_deck_in_url(logged_client, himym, user):
    other_deck = services.create_deck(user, "Jiný", parent=himym)
    deck_term = services.add_term(himym, foreign="hello", native="ahoj")

    url = reverse("vocabulary:term_edit", args=[other_deck.pk, deck_term.pk])
    assert logged_client.get(url).status_code == 404


def test_delete_deck_page_counts_words(logged_client, himym):
    services.add_term(himym, foreign="hello", native="ahoj")

    html = logged_client.get(reverse("vocabulary:deck_delete", args=[himym.pk])).content.decode()

    assert "1 slovíčko" in html
    assert DeckTerm.objects.count() == 1


def test_word_form_layout_fits_a_phone(logged_client, himym):
    html = logged_client.get(reverse("vocabulary:deck_detail", args=[himym.pk])).content.decode()

    # Variants are explained by grey samples in the fields, not by help lines under them
    assert 'placeholder="hello; hi"' in html
    assert 'placeholder="ahoj; čau"' in html
    assert "Víc variant odděl středníkem" not in html
    # Fields, then the row of suggestions, then the button, then "Více"
    order = [
        html.index('id="id_foreign"'),
        html.index('id="id_native"'),
        html.index('id="term-suggest"'),
        html.index("Přidat slovíčko"),
        html.index("Více (věta"),
    ]
    assert order == sorted(order)
