"""Dashboard numbers and the word page (spec 7.1, 8)."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from study import services
from study.models import Direction, ReviewLog, ReviewState
from study.templatetags.study_tags import due_text, seconds
from vocabulary import services as vocabulary
from vocabulary.models import DeckTerm


@pytest.fixture
def tree(user, en, cs):
    english = vocabulary.create_deck(user, "Angličtina", foreign_language=en, native_language=cs)
    series = vocabulary.create_deck(user, "Seriály", parent=english)
    return {
        "english": english,
        "series": series,
        "himym": vocabulary.create_deck(user, "HIMYM", parent=series),
        "bbt": vocabulary.create_deck(user, "Big Bang Theory", parent=series),
    }


def add(deck, word):
    return vocabulary.add_term(deck, foreign=word, native=word).term


def make_due(term):
    ReviewState.objects.filter(term=term, direction=Direction.F2N).update(
        due_at=timezone.now() - timedelta(hours=1)
    )


def make_later(term):
    ReviewState.objects.filter(term=term).update(due_at=timezone.now() + timedelta(days=5))


# Deck counts


def test_counts_include_children_and_count_shared_words_once(user, tree):
    hello = add(tree["himym"], "hello")
    DeckTerm.objects.create(deck=tree["bbt"], term=hello)
    add(tree["bbt"], "physics")
    add(tree["english"], "general")

    roots = vocabulary.load_tree(user)
    totals = services.annotate_deck_counts(roots, user)

    english = roots[0]
    series = english.tree_children[0]
    himym, bbt = series.tree_children
    assert (english.word_count, series.word_count, himym.word_count, bbt.word_count) == (3, 2, 1, 2)
    assert totals == {"words": 3, "due": 0, "new": 3}


def test_due_and_new_counts(user, tree):
    due = add(tree["himym"], "due")
    later = add(tree["himym"], "later")
    add(tree["himym"], "new")
    make_due(due)
    make_later(later)

    roots = vocabulary.load_tree(user)
    totals = services.annotate_deck_counts(roots, user)

    assert totals == {"words": 3, "due": 1, "new": 1}
    himym = roots[0].tree_children[0].tree_children[0]
    assert (himym.due_count, himym.new_count) == (1, 1)


def test_counts_use_few_queries(user, tree, django_assert_max_num_queries):
    for word in ["a", "b", "c", "d"]:
        add(tree["himym"], word)
    roots = vocabulary.load_tree(user)

    with django_assert_max_num_queries(3):
        services.annotate_deck_counts(roots, user)


def test_dashboard_shows_counts(client, user, tree):
    due = add(tree["himym"], "due")
    add(tree["himym"], "new")
    make_due(due)
    client.force_login(user)

    html = client.get(reverse("dashboard")).content.decode()

    # The counts are only in the tree: the words, then ↻ with the words to review
    assert '<small class="deck-counts">(2 <span class="deck-due" title="1 k opakování">' in html
    assert "k opakování ·" not in html


# Word history


def test_term_history(user, tree):
    hello = add(tree["himym"], "hello")
    session = services.start_session(user, [tree["himym"]])
    # The order of the directions is random
    first = services.next_card(session)
    services.record_answer(session, first, "ok")
    services.record_answer(session, services.next_card(session), "dontknow")

    history = services.term_history(hello)

    by_direction = {row["direction"]: row for row in history["directions"]}
    assert by_direction["F2N"]["total"] == 1
    assert by_direction["N2F"]["total"] == 1
    assert by_direction["F2N"]["label"] == "EN → CS"
    assert by_direction["N2F"]["label"] == "CS → EN"
    assert [p["key"] for p in by_direction[first.direction]["chart"]["points"]] == ["ok"]
    assert [log.rating for log in history["logs"]] == ["dontknow", "ok"]
    assert [log.emoji for log in history["logs"]] == ["😵", "😎"]


def answers(term, direction, days_and_ratings):
    """Answers of a word saved straight to the history: (days ago, rating)."""
    now = timezone.now()
    for days_ago, rating in days_and_ratings:
        ReviewLog.objects.create(
            user=term.owner,
            term=term,
            direction=direction,
            rating=rating,
            rating_label=rating,
            result="correct",
            chosen_interval=timedelta(days=1),
            reviewed_at=now - timedelta(days=days_ago),
        )


def test_answer_chart_puts_better_answers_higher(user, tree):
    hello = add(tree["himym"], "hello")
    answers(hello, "F2N", [(3, "dontknow"), (2, "partial"), (1, "ok")])

    chart = services.answer_charts(hello)["F2N"]

    points = chart["points"]
    # From the oldest, left to right; 😎 at the top (the smallest y), 😵 at the bottom
    assert [p["key"] for p in points] == ["dontknow", "partial", "ok"]
    assert points[0]["x"] < points[1]["x"] < points[2]["x"]
    assert points[0]["y"] > points[1]["y"] > points[2]["y"]
    # The chart fills the width (percent), three answers are joined by lines
    assert points[0]["x"] == 2 and points[-1]["x"] == 98
    assert len(chart["lines"]) == 2
    assert [level["emoji"] for level in chart["levels"]] == ["😵", "😕", "🤔", "😎"]


def test_answer_chart_answers_of_one_day_stand_next_to_each_other(user, tree):
    hello = add(tree["himym"], "hello")
    # One test with the word 4× (😕 🤔 😎 😵), then one more answer 3 days later
    answers(
        hello,
        "F2N",
        [(3.01, "partial"), (3.009, "think"), (3.008, "ok"), (3.007, "dontknow"), (0, "ok")],
    )

    xs = [p["x"] for p in services.answer_charts(hello)["F2N"]["points"]]

    steps = [round(b - a, 1) for a, b in zip(xs, xs[1:], strict=False)]
    # Nothing covers anything: the same distance inside the day, a bigger one after 3 days
    assert len(set(steps[:3])) == 1
    assert steps[3] > steps[0]


def test_answer_charts_share_one_time_axis(user, tree):
    hello = add(tree["himym"], "hello")
    # Both directions in the same tests (at noon, a few minutes apart), and one test with
    # EN → CS only (in the middle)
    noon = timezone.localtime().replace(hour=12, minute=0, second=0, microsecond=0)
    for days_ago, minute, direction, rating in [
        (10, 0, "F2N", "partial"),
        (10, 3, "N2F", "dontknow"),
        (5, 0, "F2N", "think"),
        (1, 0, "F2N", "ok"),
        (1, 3, "N2F", "partial"),
    ]:
        ReviewLog.objects.create(
            user=user,
            term=hello,
            direction=direction,
            rating=rating,
            rating_label=rating,
            result="correct",
            chosen_interval=timedelta(days=1),
            reviewed_at=noon - timedelta(days=days_ago) + timedelta(minutes=minute),
        )

    charts = services.answer_charts(hello)

    f2n = [p["x"] for p in charts["F2N"]["points"]]
    n2f = [p["x"] for p in charts["N2F"]["points"]]
    # One axis: a test with both directions is exactly one under the other (also at the
    # start and the end), the test with EN → CS only lies between them
    assert f2n[0] == n2f[0] == 2
    assert f2n[2] == n2f[1] == 98
    assert f2n[0] < f2n[1] < f2n[2]
    # Each chart has its own dates: under its first and last answer (here the same places)
    assert [d["x"] for d in charts["F2N"]["dates"]] == [2, 98]
    assert [d["x"] for d in charts["N2F"]["dates"]] == [2, 98]


def test_answer_chart_dates_stand_under_its_own_first_and_last_answer(user, tree):
    hello = add(tree["himym"], "hello")
    # EN → CS from day 10, CS → EN only from day 5: the lower chart starts later
    answers(hello, "F2N", [(10, "partial"), (5, "think"), (1, "ok")])
    answers(hello, "N2F", [(5, "partial"), (1, "ok")])

    charts = services.answer_charts(hello)

    n2f = charts["N2F"]
    assert [d["x"] for d in n2f["dates"]] == [n2f["points"][0]["x"], n2f["points"][-1]["x"]]
    assert n2f["dates"][0]["x"] > charts["F2N"]["dates"][0]["x"]


def test_answer_chart_dashes_the_line_over_a_pause(user, tree):
    hello = add(tree["himym"], "hello")
    # Two weeks of tests, a month nothing, one test
    answers(hello, "F2N", [(75, "partial"), (72, "think"), (68, "ok"), (31, "partial")])

    chart = services.answer_charts(hello)["F2N"]

    # The line over the pause is dashed, the others not; no labels of the pause
    assert [line["dashed"] for line in chart["lines"]] == [False, False, True]
    assert "pauses" not in chart
    # Only the first and the last date, not where the learning after the pause starts
    assert len(chart["dates"]) == 2


def test_answer_chart_ends_with_the_date_of_the_last_answer(user, tree):
    hello = add(tree["himym"], "hello")
    # One learning period of two weeks, the last answer 10 days ago
    answers(hello, "F2N", [(24, "partial"), (20, "think"), (16, "ok"), (10, "ok")])

    chart = services.answer_charts(hello)["F2N"]

    # The last point at the right end, under it its date
    assert chart["points"][-1]["x"] == 98
    assert [date["anchor"] for date in chart["dates"]] == ["start", "end"]
    assert chart["dates"][-1]["x"] == 98


def test_answer_chart_with_one_answer_has_no_line(user, tree):
    hello = add(tree["himym"], "hello")
    answers(hello, "F2N", [(1, "ok")])

    charts = services.answer_charts(hello)

    assert len(charts["F2N"]["points"]) == 1
    assert charts["F2N"]["lines"] == []
    assert len(charts["F2N"]["dates"]) == 1
    assert "N2F" not in charts


def test_answer_chart_joins_two_answers(user, tree):
    hello = add(tree["himym"], "hello")
    answers(hello, "F2N", [(3, "partial"), (1, "ok")])

    chart = services.answer_charts(hello)["F2N"]

    assert len(chart["lines"]) == 1
    assert [d["anchor"] for d in chart["dates"]] == ["start", "end"]


def test_answer_chart_shows_one_date_for_one_day(user, tree):
    hello = add(tree["himym"], "hello")
    answers(hello, "F2N", [(1.001, "partial"), (1, "ok")])

    chart = services.answer_charts(hello)["F2N"]

    # Both answers the same day: one date, under the last one
    assert len(chart["dates"]) == 1
    assert chart["dates"][0]["x"] == chart["points"][-1]["x"]


def test_word_page(client, user, tree):
    item = vocabulary.add_term(
        tree["himym"], foreign="hello; hi", native="ahoj", context_sentence="Hello, kids."
    )
    DeckTerm.objects.create(deck=tree["bbt"], term=item.term, context_sentence="Hello, Penny.")
    session = services.start_session(user, [tree["himym"]], direction="F2N")
    services.record_answer(session, services.next_card(session), "think", think_ms=2400)
    client.force_login(user)

    url = reverse("vocabulary:term_detail", args=[tree["himym"].pk, item.pk])
    html = client.get(url).content.decode()

    assert "hello · hi" in html
    assert "Big Bang Theory" in html and "<mark>Hello</mark>, Penny." in html
    assert "Vím po zamyšlení" in html
    assert "2,4 s" in html
    assert "za 3 dny" in html
    assert "Nové, ještě nebylo v testu" in html  # the N2F direction was never reviewed
    # The status in the head of "Reviews": tested once, F2N not right twice in a row yet
    assert "word-status word-status-learning" in html
    assert "<strong>Učíš se</strong>" in html
    assert "1× v testu" in html
    assert "Umíš, až bude každý testovaný směr 2× po sobě správně" in html
    # The chart instead of the ring, dots and counts; the history folded
    assert 'class="answer-chart"' in html
    assert "point-think" in html
    assert 'class="card-section answer-history"' in html


def test_word_list_links_to_word_page(client, user, tree):
    item = vocabulary.add_term(tree["himym"], foreign="hello", native="ahoj")
    client.force_login(user)

    html = client.get(reverse("vocabulary:deck_detail", args=[tree["himym"].pk])).content.decode()

    assert reverse("vocabulary:term_detail", args=[tree["himym"].pk, item.pk]) in html


def test_word_page_of_other_user_gives_404(client, other_user, tree):
    item = vocabulary.add_term(tree["himym"], foreign="hello", native="ahoj")
    client.force_login(other_user)

    url = reverse("vocabulary:term_detail", args=[tree["himym"].pk, item.pk])
    assert client.get(url).status_code == 404


# Filters


def test_due_text():
    now = timezone.now()

    assert due_text(None) == "nové"
    assert due_text(now - timedelta(minutes=1)) == "teď"
    assert due_text(now + timedelta(days=3, minutes=1)) == "za 3 dny"


def test_seconds():
    assert seconds(1530) == "1,5 s"
    assert seconds(None) == ""


def test_word_status_follows_the_statistics(user, tree):
    hello = add(tree["himym"], "hello")
    assert services.term_history(hello)["status"] == "new"
    assert services.term_history(hello)["tested"] == 0

    answers(hello, "F2N", [(3, "ok")])
    assert services.term_history(hello)["status"] == "learning"

    # Known: the tested direction right twice in a row (kept in the review state)
    ReviewState.objects.filter(term=hello, direction="F2N").update(
        correct_streak=2, last_reviewed_at=timezone.now()
    )
    history = services.term_history(hello)
    assert history["status"] == "known"
    assert history["tested"] == 1

    # The other direction tested and wrong: learning again, until it is right twice too
    answers(hello, "N2F", [(1, "dontknow")])
    ReviewState.objects.filter(term=hello, direction="N2F").update(
        correct_streak=0, last_reviewed_at=timezone.now()
    )
    assert services.term_history(hello)["status"] == "learning"
    ReviewState.objects.filter(term=hello, direction="N2F").update(correct_streak=2)
    assert services.term_history(hello)["status"] == "known"
