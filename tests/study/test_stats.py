"""Statistics page: totals, chart, streak and fun facts about hard words."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from study import stats
from study.models import Direction, Result, ReviewLog, ReviewState, StudySession
from vocabulary import services as vocabulary
from vocabulary.models import DeckTerm, Term

NOW = timezone.make_aware(timezone.datetime(2026, 10, 14, 12, 0))  # a Wednesday


@pytest.fixture
def deck(user, en, cs):
    return vocabulary.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)


def answer(
    user, term, days_ago, result=Result.CORRECT, rating="ok", think_ms=2000, direction=Direction.F2N
):
    ReviewLog.objects.create(
        user=user,
        term=term,
        direction=direction,
        rating=rating,
        rating_label=rating,
        result=result,
        chosen_interval=timedelta(days=1),
        think_ms=think_ms,
        decide_ms=1000,
        reviewed_at=NOW - timedelta(days=days_ago),
    )


def facts_of(user, now=NOW, period="7"):
    """The fun facts without the three of the dashboard (they come first on the statistics
    page and would take the words these tests are about)."""
    others = stats.STATS_FACTS[len(stats.TODAY_FACTS) :]
    return stats._facts(user, stats._logs(user), now, period, kinds=others)


def test_statistics_of_a_new_user(user):
    result = stats.user_statistics(user, now=NOW)

    assert result["totals"]["words"] == 0
    assert result["streak"]["current"] == 0
    assert result["facts"] == {"items": [], "answered": False}
    assert not result["has_terms"]


def test_totals_streak_and_charts(user, deck):
    hello = vocabulary.add_term(deck, foreign="hello", native="ahoj").term
    seat = vocabulary.add_term(deck, foreign="window seat", native="místo u okna").term
    Term.objects.filter(pk=hello.pk).update(created_at=NOW - timedelta(days=30))
    Term.objects.filter(pk=seat.pk).update(created_at=NOW)
    ReviewState.objects.filter(term=hello, direction="F2N").update(
        correct_streak=2, last_reviewed_at=NOW - timedelta(days=1)
    )
    # Three days in a row up to yesterday, and one older day
    for days_ago in (1, 2, 3, 10):
        answer(user, hello, days_ago)
    answer(user, hello, 1, Result.WRONG, "dontknow", think_ms=900)

    result = stats.user_statistics(user, now=NOW)

    totals = result["totals"]
    assert (totals["words"], totals["known"], totals["new"], totals["answers"]) == (2, 1, 1, 5)
    assert (result["streak"]["current"], result["streak"]["longest"]) == (3, 3)
    # The words chart ends with all words; the y axis goes up to a round number
    chart = result["words_chart"]
    # From the first word 30 days ago: by weeks, Monday 14. 9. … Monday 12. 10.
    assert [point["title"] for point in chart["points"]] == [
        "14. 9.: 1",
        "21. 9.: 1",
        "28. 9.: 1",
        "5. 10.: 1",
        "12. 10.: 2",
    ]
    assert chart["subtitle"] == "Slovíček celkem po týdnech od 14. 9. 2026"
    assert [tick["label"] for tick in chart["ticks"]] == ["0", "1", "2", "3", "4"]
    # Two words of 4 are in the middle; SVG needs a dot, not the Czech comma
    assert chart["points"][-1]["top"] == "50.00"
    facts = {fact["title"]: fact for fact in facts_of(user)["items"]}
    assert facts["Největší nepřítel"]["word"] == "hello"
    assert facts["Největší nepřítel"]["translation"] == "ahoj"


def test_facts_show_each_hard_word_once(user, deck):
    long = vocabulary.add_term(deck, foreign="window seat", native="místo u okna").term
    short = vocabulary.add_term(deck, foreign="ox", native="vůl").term
    easy = vocabulary.add_term(deck, foreign="cat", native="kočka").term
    answer(user, long, 1, Result.WRONG, "dontknow", think_ms=9000)
    answer(user, long, 2, Result.WRONG, "dontknow")
    answer(user, short, 1, Result.PARTIAL, "partial", direction=Direction.N2F)
    answer(user, easy, 1)
    # ox: native → foreign is hard, foreign → native was right last time
    ReviewState.objects.filter(term=short, direction=Direction.F2N).update(correct_streak=1)

    kinds = ["enemy", "one_way", "longest"]
    facts = stats._facts(user, stats._logs(user), NOW, "7", kinds=kinds)

    by_title = {fact["title"]: fact for fact in facts["items"]}
    assert by_title["Největší nepřítel"]["word"] == "window seat"
    assert by_title["Největší nepřítel"]["text"] == "2× vůbec nevím z 2 pokusů"
    assert by_title["Jen jedním směrem"]["word"] == "ox"
    assert by_title["Jen jedním směrem"]["text"] == "EN → CS ano, CS → EN ne"
    # The card shows first the side that is hard: native → foreign
    assert (by_title["Jen jedním směrem"]["front"], by_title["Jen jedním směrem"]["back"]) == (
        "vůl",
        "ox",
    )
    # The first card shows the foreign word first
    assert by_title["Největší nepřítel"]["front"] == "window seat"
    # Both words are used, so there is nothing left for the longest word
    assert "Nejdelší, co ti nejde" not in by_title
    # Every word only once, the easy word never
    words = [fact["word"] for fact in facts["items"]]
    assert sorted(words) == ["ox", "window seat"]
    # In the last 7 days only; the answers are 10 days old in the period of 30 days
    assert stats.user_statistics(user, now=NOW + timedelta(days=9), period="7")["facts"] == {
        "items": [],
        "answered": False,
    }
    later = facts_of(user, now=NOW + timedelta(days=9), period="30")
    assert len(later["items"]) == 2


def test_forgotten_and_oldest_hard_word(user, deck):
    enemy = vocabulary.add_term(deck, foreign="enemy", native="nepřítel").term
    cat = vocabulary.add_term(deck, foreign="cat", native="kočka").term
    dog = vocabulary.add_term(deck, foreign="dog", native="pes").term
    Term.objects.filter(pk=dog.pk).update(created_at=NOW - timedelta(days=45))
    dog.refresh_from_db()
    answer(user, enemy, 2, Result.WRONG, "dontknow")
    answer(user, enemy, 1, Result.WRONG, "dontknow")
    # cat: right twice in a row, then wrong = forgotten once
    answer(user, cat, 5)
    answer(user, cat, 4)
    answer(user, cat, 3, Result.WRONG, "dontknow")
    answer(user, dog, 3, Result.PARTIAL, "partial", think_ms=None)

    facts = facts_of(user)

    by_title = {fact["title"]: fact for fact in facts["items"]}
    assert by_title["Největší nepřítel"]["word"] == "enemy"
    assert by_title["Zapomínáš"]["word"] == "cat"
    assert by_title["Zapomínáš"]["text"] == "1× zapomenuto"
    assert by_title["Nejdelší, co ti nejde"]["word"] == "dog"
    assert stats._added_ago(dog, NOW) == "přidáno před 45 dny"
    assert stats._added_ago(dog, NOW - timedelta(days=44)) == "přidáno před 1 dnem"
    assert stats._added_ago(dog, NOW - timedelta(days=45)) == "přidáno dnes"


def test_one_direction_text(user, deck):
    ox = vocabulary.add_term(deck, foreign="ox", native="vůl").term

    assert stats._directions_text(ox, Direction.N2F) == "EN → CS ano, CS → EN ne"
    assert stats._directions_text(ox, Direction.F2N) == "CS → EN ano, EN → CS ne"


def test_streak_is_broken_after_a_day_without_answers(user, deck):
    hello = vocabulary.add_term(deck, foreign="hello", native="ahoj").term
    answer(user, hello, 2)
    answer(user, hello, 3)

    result = stats.user_statistics(user, now=NOW)

    assert (result["streak"]["current"], result["streak"]["longest"]) == (0, 2)


def test_stats_page(client, user, deck):
    hello = vocabulary.add_term(deck, foreign="hello", native="ahoj").term
    answer(user, hello, 0)
    client.force_login(user)

    html = client.get(reverse("study:stats")).content.decode()

    assert "Statistiky" in html
    assert "Slovíčka v čase" in html
    assert "<polyline" in html
    assert "Co ti nejde" in html
    assert "Za posledních 30 dní" in html
    assert "?period=" not in html


def test_stats_page_shows_only_own_data(client, user, other_user, deck):
    vocabulary.add_term(deck, foreign="hello", native="ahoj")
    client.force_login(other_user)

    html = client.get(reverse("study:stats")).content.decode()

    assert "Zatím tu nic není" in html


def test_round_top_of_the_y_axis():
    tops = [stats._nice_top(value) for value in (0, 3, 7, 63, 230, 1000)]
    assert tops == [4, 4, 8, 80, 250, 1000]


def test_dashboard_shows_all_hard_words(client, user, deck):
    for word in ("cat", "dog", "ox"):
        term = vocabulary.add_term(deck, foreign=word, native=word + " cs").term
        answer(user, term, 0, Result.WRONG, "dontknow")
    # The dashboard counts only today: the answers are from now, not from the fixed NOW
    ReviewLog.objects.filter(user=user).update(reviewed_at=timezone.now())
    client.force_login(user)

    html = client.get(reverse("dashboard")).content.decode()

    assert "Co ti dnes nejde" in html
    # Only 🐢 has a word: no word is right one way, and no word has 3 attempts for 🐘
    assert html.count('class="hard-word ') == 1
    assert "Nejdéle přemýšlíš u" in html
    assert "Nejdelší, co ti nejde" not in html


def test_dashboard_hides_hard_words_without_answers(client, user, deck):
    vocabulary.add_term(deck, foreign="cat", native="kočka")
    client.force_login(user)

    html = client.get(reverse("dashboard")).content.decode()

    assert "Co ti dnes nejde" not in html


def test_detail_link_uses_the_word_in_its_deck(client, user, deck):
    # dog is in two decks, so the numbers of cat and of its place in the deck differ
    other = vocabulary.create_deck(
        user, "Jiný", foreign_language=deck.foreign_language, native_language=deck.native_language
    )
    dog = vocabulary.add_term(deck, foreign="dog", native="pes")
    DeckTerm.objects.create(deck=other, term=dog.term)
    cat = vocabulary.add_term(deck, foreign="cat", native="kočka")
    assert cat.pk != cat.term.pk
    answer(user, cat.term, 0, Result.WRONG, "dontknow")
    client.force_login(user)

    html = client.get(reverse("study:stats")).content.decode()

    url = reverse("vocabulary:term_detail", args=[deck.pk, cat.pk])
    assert f'href="{url}"' in html
    assert client.get(url).status_code == 200


def test_word_in_no_deck_is_not_shown(user, deck):
    cat = vocabulary.add_term(deck, foreign="cat", native="kočka")
    answer(user, cat.term, 0, Result.WRONG, "dontknow")
    # Only the place in the deck is gone, the word itself is still there
    cat.delete()

    assert stats.user_statistics(user, now=NOW)["facts"]["items"] == []


def test_recent_tests(user, deck):
    from study import services as study

    cat = vocabulary.add_term(deck, foreign="cat", native="kočka").term
    dog = vocabulary.add_term(deck, foreign="dog", native="pes").term
    # Both directions: 2 words are 4 cards
    done = study.start_session(user, [deck])
    for term in (cat, dog):
        for direction in Direction.values:
            state = ReviewState.objects.get(term=term, direction=direction)
            rating = "dontknow" if term == dog and direction == Direction.N2F else "ok"
            study.record_answer(done, state, rating)
    study.finish_session(done)
    # One direction with a limit, stopped after one card
    stopped = study.start_session(user, [deck], direction="F2N", scope="all", max_cards=30)
    study.record_answer(stopped, ReviewState.objects.get(term=cat, direction="F2N"), "think")
    # Started and closed without an answer: not in the table
    study.start_session(user, [deck])

    tests = stats.recent_tests(user)

    newest, older = tests["rows"]
    assert (newest["cards"], newest["direction"], newest["scope"], newest["limit"]) == (
        1,
        "EN → CS",
        "všechna",
        "max 30",
    )
    assert not newest["finished"]
    # Both directions: every word twice
    assert (older["cards"], older["direction"]) == (4, "EN → CS + CS → EN")
    assert [item["count"] for item in older["ratings"]] == [3, 0, 0, 1]
    assert older["percent"] == 75
    assert older["finished"]
    assert older["paths"] == [{"short": "Angličtina", "full": "Angličtina"}]
    assert tests["summary"] == "Za 14 dní 2 testy · průměrně 2 slovíčka"


def test_recent_tests_after_deleting_words(user, deck):
    from study import services as study

    cat = vocabulary.add_term(deck, foreign="cat", native="kočka")
    dog = vocabulary.add_term(deck, foreign="dog", native="pes")
    only_cat = study.start_session(user, [deck], direction="F2N")
    study.record_answer(only_cat, ReviewState.objects.get(term=cat.term, direction="F2N"), "ok")
    both = study.start_session(user, [deck], direction="F2N")
    study.record_answer(both, ReviewState.objects.get(term=cat.term, direction="F2N"), "ok")
    study.record_answer(both, ReviewState.objects.get(term=dog.term, direction="F2N"), "dontknow")
    # Deleting a word deletes its answers, the counters of the tests stay
    vocabulary.remove_term_from_deck(cat)

    tests = stats.recent_tests(user)

    # The test with only cat has no answer left, the other one has one card of dog
    (row,) = tests["rows"]
    assert row["session"] == both
    assert (row["cards"], row["percent"]) == (1, 0)
    assert tests["summary"] == "Za 14 dní 1 test · průměrně 1 slovíčko"


def test_deck_path_in_recent_tests(user, deck):
    from study import services as study

    season = vocabulary.create_deck(user, "S01", parent=deck)
    episode = vocabulary.create_deck(user, "E02", parent=season)
    cat = vocabulary.add_term(episode, foreign="cat", native="kočka")
    session = study.start_session(user, [episode], direction="N2F")
    study.record_answer(session, ReviewState.objects.get(term=cat.term, direction="N2F"), "ok")

    (row,) = stats.recent_tests(user)["rows"]

    assert row["paths"] == [{"short": "Angličtina › S01 › E02", "full": "Angličtina › S01 › E02"}]
    assert row["direction"] == "CS → EN"


def test_long_deck_path_shows_the_last_three():
    names = {
        1: ("CzechEnglish", None),
        2: ("series", 1),
        3: ("Two and Half Men", 2),
        4: ("S01", 3),
        5: ("E02", 4),
    }

    path = vocabulary.deck_path(5, names)

    assert path["short"] == "… › Two and Half Men › S01 › E02"
    assert path["full"] == "CzechEnglish › series › Two and Half Men › S01 › E02"


def test_today_good_news_and_week(client, user, deck):
    from study import services as study

    cat = vocabulary.add_term(deck, foreign="cat", native="kočka").term
    dog = vocabulary.add_term(deck, foreign="dog", native="pes").term
    Term.objects.filter(pk=dog.pk).update(created_at=timezone.now() - timedelta(days=3))
    # dog: right yesterday, right again today = learned today
    yesterday = study.start_session(user, [deck], direction="F2N")
    study.record_answer(yesterday, ReviewState.objects.get(term=dog, direction="F2N"), "ok")
    ReviewLog.objects.filter(session=yesterday).update(
        reviewed_at=timezone.now() - timedelta(days=1)
    )
    StudySession.objects.filter(pk=yesterday.pk).update(
        started_at=timezone.now() - timedelta(days=1)
    )
    today = study.start_session(user, [deck])
    for term in (dog, cat):
        for direction in Direction.values:
            state = ReviewState.objects.get(term=term, direction=direction)
            study.record_answer(today, state, "ok")

    overview = stats.today_overview(user)

    metrics = {item["key"]: item for item in overview["metrics"]}
    values = {key: (item["value"], item["label"]) for key, item in metrics.items()}
    assert "added" not in values
    assert values["learned"] == ("1", "slovíčko naučeno")
    # cat was right for the first time today, dog was right yesterday already
    assert values["first"] == ("1", "poprvé správně")
    # 2 words in the test, each in both directions, counted once
    assert values["tested"] == ("2", "slovíčka v testech")
    # 7 days for each, today last; yesterday dog was right for the first time
    bars = metrics["first"]["bars"]
    assert len(bars) == stats.WEEK_DAYS
    assert [(bar["value"], bar["today"]) for bar in bars[-2:]] == [("1", False), ("1", True)]
    assert bars[-1]["label"] == "dnes"

    client.force_login(user)
    html = client.get(reverse("dashboard")).content.decode()
    assert "poprvé správně" in html
    assert 'data-today-chart="minutes"' in html


def test_today_without_tests(user, deck):
    overview = stats.today_overview(user)

    assert [item["value"] for item in overview["metrics"]] == ["0", "0", "0", "0 min"]


def test_word_known_before_is_not_learned_again(user, deck):
    cat = vocabulary.add_term(deck, foreign="cat", native="kočka").term
    for days_ago in (3, 2):
        ReviewLog.objects.create(
            user=user,
            term=cat,
            direction=Direction.F2N,
            rating="ok",
            rating_label="x",
            result=Result.CORRECT,
            chosen_interval=timedelta(days=1),
            reviewed_at=timezone.now() - timedelta(days=days_ago),
        )
    # Forgotten, then right twice again today
    ReviewLog.objects.create(
        user=user,
        term=cat,
        direction=Direction.F2N,
        rating="dontknow",
        rating_label="x",
        result=Result.WRONG,
        chosen_interval=timedelta(days=1),
        reviewed_at=timezone.now() - timedelta(days=1),
    )
    for minutes in (20, 10):
        ReviewLog.objects.create(
            user=user,
            term=cat,
            direction=Direction.F2N,
            rating="ok",
            rating_label="x",
            result=Result.CORRECT,
            chosen_interval=timedelta(days=1),
            reviewed_at=timezone.now() - timedelta(minutes=minutes),
        )

    values = {item["key"]: item["value"] for item in stats.today_overview(user)["metrics"]}

    assert values["learned"] == "0"


def test_dashboard_hard_words_are_only_from_today(client, user, deck):
    cat = vocabulary.add_term(deck, foreign="cat", native="kočka").term
    ReviewLog.objects.create(
        user=user,
        term=cat,
        direction=Direction.F2N,
        rating="dontknow",
        rating_label="x",
        result=Result.WRONG,
        chosen_interval=timedelta(days=1),
        think_ms=1000,
        reviewed_at=timezone.now() - timedelta(days=1, hours=1),
    )
    client.force_login(user)

    html = client.get(reverse("dashboard")).content.decode()

    assert "Co ti dnes nejde" not in html


def test_mixed_up_rollercoaster_and_rushed_words(user, deck):
    borrow = vocabulary.add_term(deck, foreign="borrow", native="půjčit").term
    lend = vocabulary.add_term(deck, foreign="lend", native="půjčit si").term
    Term.objects.filter(pk=lend.pk).update(main_native="půjčit")
    swing = vocabulary.add_term(deck, foreign="swing", native="houpat").term
    rush = vocabulary.add_term(deck, foreign="rush", native="spěch").term
    for term in (borrow, lend):
        answer(user, term, 3, Result.WRONG, "dontknow", think_ms=5000)
    # swing: wrong, right, wrong, right, wrong = 4 changes
    for days_ago, result in zip((6, 5, 4, 3, 2), "wcwcw", strict=True):
        if result == "w":
            answer(user, swing, days_ago, Result.WRONG, "dontknow", think_ms=5000)
        else:
            answer(user, swing, days_ago, think_ms=5000)
    answer(user, rush, 1, Result.WRONG, "dontknow", think_ms=1200)
    # The biggest enemy takes another word, so swing is free for the rollercoaster
    enemy = vocabulary.add_term(deck, foreign="enemy", native="nepřítel").term
    for days_ago in (1, 2, 3, 4):
        answer(user, enemy, days_ago, Result.WRONG, "dontknow", think_ms=5000)

    by_title = {fact["title"]: fact for fact in facts_of(user)["items"]}

    # The pair takes both words, so each of them is on no other card
    assert by_title["Pleteš si"]["word"] in ("borrow · lend", "lend · borrow")
    assert by_title["Pleteš si"]["translation"] == "půjčit"
    assert by_title["Horská dráha"]["word"] == "swing"
    assert by_title["Horská dráha"]["text"] == "4× změna vím ↔ nevím"
    assert by_title["Moc rychle"]["text"] == "za 1,2 s a vůbec nevím"
    words = [fact["word"] for fact in by_title.values()]
    assert sum("borrow" in word for word in words) == 1


def test_dashboard_word_again_and_again(user, deck):
    cat = vocabulary.add_term(deck, foreign="cat", native="kočka").term
    dog = vocabulary.add_term(deck, foreign="dog", native="pes").term
    # cat: 3 old attempts and a wrong answer today; dog: wrong only today
    for days_ago in (9, 8, 7):
        answer(user, cat, days_ago)
    answer(user, cat, 0, Result.WRONG, "dontknow", think_ms=1000)
    answer(user, dog, 0, Result.WRONG, "dontknow", think_ms=8000)

    cards = stats.hard_words(user, now=NOW)

    # 🐢 takes dog (longer thinking), 🐘 takes cat
    assert [(card["emoji"], card["word"]) for card in cards] == [("🐢", "dog"), ("🐘", "cat")]
    assert cards[1]["text"] == "zase nevím · už 4. pokus"


def test_statistics_start_with_the_three_of_the_dashboard():
    assert stats.STATS_FACTS[:3] == stats.TODAY_FACTS
    assert len(set(stats.STATS_FACTS)) == len(stats.STATS_FACTS)


def test_words_chart_by_days_months_and_quarters(user, deck):
    cat = vocabulary.add_term(deck, foreign="cat", native="kočka").term

    def chart(days_ago):
        Term.objects.filter(pk=cat.pk).update(created_at=NOW - timedelta(days=days_ago))
        return stats.user_statistics(user, now=NOW)["words_chart"]

    # 3 days after the first word: a point for each day, no empty start
    by_days = chart(2)
    titles = [point["title"] for point in by_days["points"]]
    assert titles == ["12. 10.: 1", "13. 10.: 1", "14. 10.: 1"]
    assert by_days["subtitle"].startswith("Slovíček celkem po dnech")
    # Half a year: by months; three years: by quarters
    assert chart(180)["points"][0]["title"] == "dub 2026: 1"
    assert chart(3 * 365)["points"][0]["title"].startswith("Q4 2023")
    # The first word today: one point in the middle
    single = chart(0)
    assert [point["left"] for point in single["points"]] == ["50.00"]


def test_known_needs_every_tested_direction(user, deck):
    both = vocabulary.add_term(deck, foreign="veal", native="telecí").term
    one_way = vocabulary.add_term(deck, foreign="hello", native="ahoj").term
    # veal: EN → CS right twice, CS → EN wrong last time; hello: only EN → CS, right twice
    for term, direction, streak in [
        (both, "F2N", 2),
        (both, "N2F", 0),
        (one_way, "F2N", 2),
    ]:
        ReviewState.objects.filter(term=term, direction=direction).update(
            correct_streak=streak, last_reviewed_at=NOW - timedelta(days=1)
        )

    assert stats.known_words(user) == 1


def test_learned_waits_for_the_other_direction(user, deck):
    veal = vocabulary.add_term(deck, foreign="veal", native="telecí").term
    # EN → CS right twice (known, if it were the only direction), but CS → EN came between
    # them and was wrong; known only when CS → EN is right twice as well, yesterday
    answer(user, veal, 5)
    answer(user, veal, 4, Result.WRONG, "dontknow", direction=Direction.N2F)
    answer(user, veal, 3)
    answer(user, veal, 2, direction=Direction.N2F)
    answer(user, veal, 1, direction=Direction.N2F)

    metrics = stats.today_overview(user, now=NOW)["metrics"]
    learned = next(metric for metric in metrics if metric["key"] == "learned")

    # Yesterday (not 3 days ago, when only EN → CS was right twice), nothing today
    assert [bar["value"] for bar in learned["bars"]][-3:] == ["0", "1", "0"]
