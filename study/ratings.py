"""Rating buttons shown after the card is turned (spec 6.3).

To change the buttons (names, times, how much the interval grows), change only this list.
The order of the list is the order on the screen: best answer first.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.utils.translation import gettext_lazy as _

from .models import Result

# No interval is longer than this
MAX_INTERVAL = timedelta(days=365)


@dataclass(frozen=True)
class Rating:
    key: str
    emoji: str
    label: str
    result: str
    # First interval, and the shortest one after growing
    min_interval: timedelta
    # Next interval = last interval × multiplier. None means always min_interval.
    multiplier: float | None
    hotkey: str
    max_interval: timedelta = MAX_INTERVAL


RATINGS = [
    Rating(
        key="ok",
        emoji="😎",
        label=_("I know"),
        result=Result.CORRECT,
        min_interval=timedelta(days=7),
        multiplier=4,
        hotkey="1",
    ),
    Rating(
        key="think",
        emoji="🤔",
        label=_("I know after thinking"),
        result=Result.CORRECT,
        min_interval=timedelta(days=3),
        multiplier=2.5,
        hotkey="2",
    ),
    Rating(
        key="partial",
        emoji="😕",
        label=_("I half remember"),
        result=Result.PARTIAL,
        min_interval=timedelta(days=1),
        multiplier=None,
        hotkey="3",
    ),
    Rating(
        key="dontknow",
        emoji="😵",
        label=_("No idea"),
        result=Result.WRONG,
        min_interval=timedelta(minutes=10),
        multiplier=None,
        hotkey="4",
    ),
]

RATINGS_BY_KEY = {rating.key: rating for rating in RATINGS}


def get_rating(key):
    try:
        return RATINGS_BY_KEY[key]
    except KeyError:
        raise ValueError(f"Unknown rating: {key!r}") from None
