# Vokie

Web app for learning vocabulary. You build your own dictionaries (for example one per TV series
episode), add words to them and practise them as flash cards with spaced repetition.

- Specification (Czech): [docs/spec.md](docs/spec.md)
- MVP implementation plan (Czech): [docs/plan.md](docs/plan.md)

## Tech stack

- Python 3.13, managed with [uv](https://docs.astral.sh/uv/)
- Django 6.1
- PostgreSQL 17 (15 or newer is required)
- Django templates + HTMX, Pico.css

---

## Local development

### Requirements

- PostgreSQL 15+ running locally (no Docker)
- `uv`
- Python 3.13 (uv installs it if missing)

Check versions:

```bash
psql --version          # psql (PostgreSQL) 17.x
uv --version
```

### 1. Create the database

The app needs its own database user and database. Locally the user also needs the `CREATEDB`
right, because tests create their own database (`test_vokie`).

**Option A: command line**

```bash
sudo -u postgres psql -c "CREATE ROLE vokie LOGIN PASSWORD 'vokie' CREATEDB;"
sudo -u postgres createdb -O vokie -E UTF8 -T template0 vokie
```

**Option B: pgAdmin**

1. *Login/Group Roles → Create → Login/Group Role*
   - General → Name: `vokie`
   - Definition → Password: `vokie`
   - Privileges → turn on *Can login?* and *Create databases?*
2. *Databases → Create → Database*
   - General → Database: `vokie`, Owner: `vokie`
   - Definition → Encoding: `UTF8`, Template: `template0`

**Check the connection:**

```bash
PGPASSWORD=vokie psql -h localhost -U vokie -d vokie -c "select current_user, version();"
```

### 2. Configure the app

```bash
cp .env.example .env
```

The default values in `.env.example` match the database from step 1. Change them if your
database uses a different name, user, password or port.

### 3. Install dependencies

```bash
uv sync
```

### 4. Check the setup

```bash
uv run python manage.py check     # System check identified no issues (0 silenced).
uv run pytest                     # all tests pass - this also checks the database connection
```

### 5. Create the database tables

```bash
uv run python manage.py migrate
```

Run it again after every `git pull` that brings new migrations. You can see which migrations
are applied with:

```bash
uv run python manage.py showmigrations
```

### 6. Create your user account

There is no public registration. Accounts are created by hand. You log in with your **email**:

```bash
uv run python manage.py createsuperuser
# Email: martin@example.com
# Password: ********
# Password (again): ********
```

More accounts can be added later in the admin (<http://127.0.0.1:8000/admin/>) under
*Uživatelé → Přidat*. Login ignores letter case in the email: `Martin@Example.com` works too.

To try the app right away, fill your account with sample decks and words (HIMYM, Big Bang
Theory, Shrek, a Spanish deck). Running it again changes nothing:

```bash
uv run python manage.py seed_demo martin@example.com
# Added sample decks with 15 words.
```

The sample decks are called *Angličtina (ukázka)* and *Španělština (ukázka)*; delete them in the
app when you do not need them any more.

Your native language, the default test direction, the translation suggestions and the meanings
from the dictionary on the test card (both on by default) can be set on the *Nastavení* page.

To change a forgotten password (there is no password reset by email yet):

```bash
uv run python manage.py changepassword martin@example.com
```

### 7. Languages

The first migration adds three languages: `cs` Čeština, `en` Angličtina, `es` Španělština.
More languages can be added in the admin under *Vocabulary → Jazyky → Přidat*.

The code must be an [ISO 639-1](https://en.wikipedia.org/wiki/List_of_ISO_639_language_codes)
code: two lowercase letters.

| Language | Code | Common mistake |
|---|---|---|
| Czech | `cs` | ~~`cz`~~ is the country code |
| German | `de` | ~~`ger`~~ is a 3-letter code |
| French | `fr` | |
| Italian | `it` | |
| Japanese | `ja` | ~~`jp`~~ is the country code |

Or from the shell:

```bash
uv run python manage.py shell -c "from vocabulary.models import Language; Language.objects.create(code='de', name='Němčina')"
```

Your own native language (used as the default for new decks) can be set in the admin on your
user: *Uživatelé → your email → Mluvím*, or on the *Nastavení* page.

### 8. Decks (dictionaries)

Decks form a tree, for example:

```
Angličtina (EN → CS)
├── Seriály
│   ├── HIMYM
│   │   └── S01
│   │       ├── E01
│   │       └── E02
│   └── Big Bang Theory
└── Filmy
    └── Shrek
```

Rules (checked in `vocabulary/services.py`):

- A root deck has a language pair, e.g. EN → CS. Child decks always use the pair of the parent.
- The tree has at most **5 levels**. `Angličtina › Seriály › HIMYM › S01 › E01` is the deepest
  possible path.
- Deck names are unique under one parent, letter case does not matter (`HIMYM` = `himym`).
- A deck can be moved only under a deck with the same language pair, never into itself or its
  own children, and only if the tree stays within 5 levels.
- Deleting a deck deletes all its child decks too.

Example in the shell:

```bash
uv run python manage.py shell
```

```python
from accounts.models import User
from vocabulary.models import Language
from vocabulary import services

me = User.objects.get(email="martin@example.com")
en, cs = Language.objects.get(code="en"), Language.objects.get(code="cs")

english = services.create_deck(me, "Angličtina", foreign_language=en, native_language=cs)
series = services.create_deck(me, "Seriály", parent=english)
himym = services.create_deck(me, "HIMYM", parent=series)

services.get_ancestors(himym)  # [<Deck: Angličtina>, <Deck: Seriály>, <Deck: HIMYM>]
services.move_deck(himym, english)  # HIMYM is now directly under Angličtina
```

### 9. Words

Words are added on the deck page. Only the first two fields are required:

| Field | Example | Note |
|---|---|---|
| Foreign language | `hello; hi` | more variants (synonyms) separated by `;` |
| Native language | `ahoj; čau` | the same |
| Sentence | `Hello, kids.` | under *Více*, where you saw the word; another form of the word in braces: `He {ran} away.` |
| Note | | under *Více* |

There is no field for the episode: the deck is the episode (e.g. *Series 1 › Episode 1*).

After saving, the form is empty again and the cursor is back in the first field, so you can
type the next word right away (Enter sends the form).

While you type, the app looks for words you already have and shows what to do:

| You type | You already have | The app offers |
|---|---|---|
| `hello` in Big Bang Theory | `hello → ahoj` in HIMYM | **Přidat i sem** (same word, now in both decks) |
| `hello; hi` | `hello → ahoj` | the same, and `hi` is added to `hello` as a new variant |
| `hey → ahoj` | `hello → ahoj` | **Přidat „hey“ jako variantu k „hello“**, or save it separately |
| `palm → palma` | `palm → dlaň` | a note about the other translation: *same meaning* (add as a variant), or just save it as another meaning |
| `cau` | `čau` | only a note "Podobné (bez diakritiky)"; `byt` and `být` are different words |

The *Přidat slovíčko* button is disabled while the word cannot be saved: the same foreign word
with the same translation already exists. The same foreign word with another translation is
another meaning and is saved as its own word (`palm → dlaň`, `palm → palma`).

Only the chosen meaning is saved. Other meanings of the word (the user's own words with the same
foreign text and meanings from Wiktionary) are read when they are shown: on the back of the
card and on the word page, where a dictionary meaning can be added with *+ Učit se i tento
význam*. The back of the card, from the most important:

```
dlaň                                   ← the answer
Učíš se i: palm → palma                ← your own word with the same foreign text
„She can read from her palm.“          ← the sentence
pracka · lehký · světlý +3             ← dictionaries, small; first variant of each meaning
(další významy z Wiktionary)           ← the sources
```

The browser shows as many dictionary meanings as fit on one line and *+N* for the rest; a click
on it shows them all (`fitMeanings` in `static/js/study.js`). Meanings of all dictionaries go
into the same line, each word once, and the line under it names all sources. The word page
shows all meanings with all variants. The
meanings from the dictionary on the card can be turned off on the *Nastavení* page.

The word in the sentence is found automatically (whole words, any foreign variant, letter case
ignored) and shown marked. For another form of the word put it in braces, e.g. `He {ran} away.`
for the word `run`; `{}` alone means the main variant. In the native → foreign test the front of
the card shows the sentence with a gap instead of the word:

```
dlaň
„She can read from her ___.“      → back: palm  „She can read from her palm.“
```

Rules:

- A word belongs to you, not to a deck. Decks only point to it, so one word can be in more
  decks and is tested only once.
- The same word (same first foreign variant and same first translation, letter case ignored)
  cannot be added twice. Another translation is another meaning: `palm → dlaň`, `palm → palma`.
- Input is tidied: spaces at the ends are removed, more spaces become one, and Unicode is unified
  (NFC), so `čau` typed on any device is the same text.
- **Moving words:** in the word list click *Vybrat*, tick the words (or *Vše*) and click
  *Přesunout…*, then choose the deck. *Přesunout* moves them, *Přidat i tam* keeps them in both
  decks. Only decks with the same languages are offered. The sentence and the review progress
  stay; a word that is already in the target deck is not doubled. One word can be moved from
  its page (*Přesunout*).
- Removing a word from its last deck deletes it, including its review history. Deleting a deck
  deletes the words that are in no other deck.

Example in the shell:

```python
from vocabulary.models import Deck
from vocabulary import services

himym = Deck.objects.get(name="HIMYM")
item = services.add_term(
    himym,
    foreign="hello; hi",
    native="ahoj; čau",
    context_sentence="Hello, kids.",
)
item.term.foreign_variants  # ['hello', 'hi']
```

### 10. Translation suggestions (Wiktionary)

While you type a foreign word, the app suggests Czech translations with the part of speech, e.g.
`present` → *současnost, dárek* (podstatné jméno), *představit* (sloveso). A click puts the
suggestion into the translation field. The data come from the
[Czech Wiktionary](https://cs.wiktionary.org) as extracted by [kaikki.org](https://kaikki.org)
(licence CC BY-SA, so the source is shown under the suggestions). Every user can turn the
suggestions off on the *Nastavení* page (*Přidávání slovíček › Navrhovat překlad*).

Import the data once (about 40 MB download, ~10 s, ~35 MB in the database):

```bash
curl -fLO https://kaikki.org/dictionary/downloads/cs/cs-extract.jsonl.gz
uv run python manage.py import_wiktionary cs-extract.jsonl.gz
# Imported 113645 entries (en 17504, fr 16449, de 13658, ...).

# Only some languages (smaller table):
uv run python manage.py import_wiktionary cs-extract.jsonl.gz --languages en,es
```

Run it again from time to time with a new download; it replaces the old data. Without the
import the app works the same, it just shows no suggestions. Only decks whose *Mluvím* language
is Czech get suggestions (the Czech Wiktionary has meanings in Czech). It knows about 14 000
English words (most common words are there), Spanish only about 2 600.

The sources of suggestions are in `dictionary/providers.py` and their order is the environment
variable `VOKIE_SUGGESTION_PROVIDERS` (default `wiktionary`), so another source can be added
later without changing the rest of the app.

**Pronunciation.** The same import has the pronunciation: IPA (about 75 % of English words) and
recordings of real speakers (about 44 %, mostly American). On the back of a test card and on the
word page the foreign word gets a grey 🔊 (on the card always at the right edge, on the line of
the foreign word; on the word page next to the title); a click or the key **P** plays the mp3 directly
from Wikimedia Commons (nothing is stored, the browser needs internet). Only the main foreign
variant is looked up, so phrases like `suit up` usually have none. Without a recording the
**voice of the browser** (Web Speech API) reads the word; it also reads the sentence of the card
(🔊 at its end, key **V**). That button comes hidden and is shown only when the browser has a
voice for the language (`voiceFor` in `static/js/app.js`, an American voice is preferred for
English). Voices are good on Android, Windows, Mac and in Chrome on Linux, robotic or missing in
Firefox on Linux. Users can turn it off or let it
play right after the card is turned (*Nastavení › Test*). The written pronunciation in IPA,
e.g. `[pɑːm]` small under the word, is off by default (*Ukazovat zápis výslovnosti (IPA)*); a
word with only IPA and no recording then shows nothing. The sources are
`VOKIE_PRONUNCIATION_PROVIDERS` (default `wiktionary`); a server voice (e.g. Piper) can be added
there later.

```python
from dictionary.providers import get_pronunciation

get_pronunciation("palm", "en")
# Pronunciation(ipa='pɑːm', audio_url='https://upload.wikimedia.org/...En-us-palm.ogg.mp3',
#               source_label='Wiktionary')
```

### 11. Repetition intervals

After a card is turned, you rate yourself. The interval grows with every good answer and is
capped at one year. Intervals of a day or more are rounded to whole days.

| Button | Meaning | First time | Next time |
|---|---|---|---|
| 😎 `1` | Vím | 7 days | last interval × 4 |
| 🤔 `2` | Vím po zamyšlení | 3 days | last interval × 2.5 |
| 😕 `3` | Vzpomínám si napůl | 1 day | always 1 day |
| 😵 `4` | Vůbec nevím | 10 minutes | always 10 minutes |

Example, always 😎: 7 days → 28 → 112 → 365. After 😕 or 😵 the growth starts again from the
first value. The buttons are defined in `study/ratings.py`.

### 12. Tests (study sessions)

A test is a `StudySession`: chosen decks (child decks are included), direction and scope. The
next card is always computed from the database, so the app works the same on more devices.

- **Scope "due"**: cards that are due (oldest first), then new cards in the order they were
  added. A card rated 😵 comes back by itself after 10 minutes.
- **Scope "all"**: every card once.
- A word that is in more chosen decks comes only once, and a rating counts in all its decks.
- The same word (other direction) or another meaning of it (palm / palm) does not come twice in
  a row when there is something else to show.
- Every answer is saved in `ReviewLog` with copies of the rating, the result, the interval and
  the time needed (`think_ms`, `decide_ms`).

Example in the shell:

```python
from accounts.models import User
from vocabulary.models import Deck
from study import services

me = User.objects.get(email="martin@example.com")
session = services.start_session(me, [Deck.objects.get(name="HIMYM")])

card = services.next_card(session)  # ReviewState, e.g. "hello" F2N
services.record_answer(session, card, "ok", think_ms=1800)
services.session_summary(session)
```

### 13. The test screen

Start a test from the dashboard (*Spustit test*) or from a deck (*Testovat tento slovník*):
choose decks, direction and which cards. Then:

1. The card shows the question. In the foreign → native direction the sentence is shown too,
   with the word marked.
2. **Ukázat** or **Space** turns the card. The pronunciation of the foreign word, the answer,
   your other words with the same text, the sentence and other meanings are on the back.
   **P** (or 🔊) plays the recording.
3. Rate yourself with one of the buttons or keys **1–4**. Under each emoji is the real next
   interval of this card, e.g. `7 dní`. The next card comes without reloading the page.
4. At the end the summary shows the counts and the words rated 😕 or 😵, with
   *Procvičit chybné znovu* (a new test with only those words).

The time until the card is turned (`think_ms`) and until the rating (`decide_ms`) is measured in
the browser and paused while the page is hidden (another app, locked phone).

### 14. Dashboard and word page

- The dashboard shows the decks as a tree of folders (📂 open, 📁 closed, 📄 deck without child
  decks). The whole tree is always open when the page loads; a click on a folder closes it
  until the next reload.
- **Drag a deck** to move it. Rows do not move while dragging; the place is shown instead:
  - over the **middle of a row** the row is highlighted: the deck goes **into** it (also into a
    deck that has no child decks yet),
  - near the **top or bottom edge** of a row a line is shown: the deck goes **before / after** it.

  With a mouse just drag it; on a phone hold it for a moment first, so a normal swipe still
  scrolls the page. The server checks the same rules as *Přesunout* and puts the deck back with
  a message when the move is not allowed.
- It also shows how many words are due now, how many are new (never tested) and, next
  to every deck, the number of its words including child decks. A word that is in more decks
  is counted once. A word is *due* when at least one of its directions is due.
- Clicking a word in a deck opens its page: variants, the decks it is in (with sentences), the
  next repetition and counts of ratings for each direction, and the history of answers.

### 15. Help

The app has a help page for users (*Nápověda* in the top bar, `/help/`) with tabs *Slovníky*,
*Slovíčka*, *Test* and *Přehled a statistiky*. Every tab is its own page
(`templates/help/<tab>.html`); the list of tabs is `HELP_TOPICS` in `config/views.py`. The
table of rating buttons is made from `study/ratings.py`, so it stays right when the buttons
change. When a feature changes, update its help tab too.

### 16. Run the app

```bash
uv run python manage.py runserver
```

Open <http://127.0.0.1:8000/>. Every page except the login page needs a logged in user, so you
are sent to the login page first.

To try the app from a phone on the same network:

```bash
# 1. Find the IP address of your computer, e.g. 192.168.1.20
hostname -I

# 2. Allow it in .env
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.20

# 3. Listen on all network interfaces
uv run python manage.py runserver 0.0.0.0:8000
```

Then open `http://192.168.1.20:8000/` on the phone.

### Project layout

```
config/       Django project: settings, root URLs, WSGI/ASGI entry points
accounts/     custom user model (login with email), admin, login/logout
vocabulary/   languages, decks (dictionary tree), words and their variants
  services.py   all rules for decks and words, views only call these functions
  sentences.py  the word in a sentence: found or {marked}, highlighted or replaced by a gap
dictionary/   imported Wiktionary and the sources of translation suggestions (providers.py)
study/        tests: review states, sessions, history, the test screen
  cards.py      what one card shows (question, answer, sentence, hints)
  formatting.py intervals in Czech ("8 dní")
  ratings.py    the rating buttons 😎 🤔 😕 😵 and their intervals - change them only here
  services.py   how a rating changes the next interval, which card comes next, saving answers
templates/    project-wide templates (base.html = layout of all pages,
              forms/field.html = how every form field looks,
              help/ = the help pages, one template per tab)
static/       project-wide static files
  css/app.css   small custom styles on top of Pico.css
  js/app.js     helpers for all pages ("other meaning" button)
  js/study.js   test screen: turning the card, keyboard, time measuring, legend
  js/tree.js    dashboard tree: moving decks by drag and drop
  vendor/       third-party files kept in the repository (see below)
tests/        all tests, one folder per app
  conftest.py   shared pytest fixtures (users, languages, fast password hashing)
  project/      whole project: database, layout, help pages
  accounts/     users, login, settings
  vocabulary/   languages, decks, words, duplicates, sentences, seed_demo
  dictionary/   Wiktionary import and translation suggestions
  study/        intervals, sessions, cards, test screen, dashboard numbers
docs/         specification and plan (Czech)
```

### Front-end libraries

Pico.css and HTMX are stored in `static/vendor/` instead of loading them from a CDN, so the app
works without internet and the versions do not change by surprise.

| Library | Version | File |
|---|---|---|
| [Pico.css](https://picocss.com) | 2.1.1 | `static/vendor/pico/pico.min.css` |
| [HTMX](https://htmx.org) | 2.0.11 | `static/vendor/htmx/htmx.min.js` |
| [SortableJS](https://sortablejs.github.io/Sortable/) | 1.15.7 | `static/vendor/sortable/Sortable.min.js` |

To update a library, download the new version over the old file and change the version in the
table above:

```bash
# Example: HTMX 2.0.12
curl -fL -o static/vendor/htmx/htmx.min.js \
  https://cdn.jsdelivr.net/npm/htmx.org@2.0.12/dist/htmx.min.js

# Example: Pico.css 2.1.2
curl -fL -o static/vendor/pico/pico.min.css \
  https://cdn.jsdelivr.net/npm/@picocss/pico@2.1.2/css/pico.min.css
```

```bash
# Example: SortableJS 1.15.8
curl -fL -o static/vendor/sortable/Sortable.min.js \
  https://cdn.jsdelivr.net/npm/sortablejs@1.15.8/Sortable.min.js
```

The latest versions can be found at <https://www.jsdelivr.com/package/npm/htmx.org>,
<https://www.jsdelivr.com/package/npm/@picocss/pico> and
<https://www.jsdelivr.com/package/npm/sortablejs>.

HTMX requests send the CSRF token automatically (`hx-headers` on `<body>` in `base.html`), so
`hx-post` works without extra code.

### Useful commands

```bash
uv run ruff check           # lint
uv run ruff check --fix     # lint and fix what can be fixed automatically
uv run ruff format          # format code
uv run pytest               # run all tests
uv run pytest tests/study   # only the tests of one app
uv run pytest -k duplicate  # only tests with "duplicate" in the name
```

---

## Deployment

### Database

**Requirements:**

- PostgreSQL **15 or newer** (required by Django 6.1). PostgreSQL 17 is recommended.
- The `unaccent` extension must be available. It is part of the standard PostgreSQL packages on
  Debian/Ubuntu (`postgresql-17`), so usually there is nothing to install.

**Create the user and the database** (on the server, as the `postgres` superuser):

```bash
# Generate a strong password and save it, you will need it in .env
openssl rand -base64 24
```

```sql
-- Run in: sudo -u postgres psql
CREATE ROLE vokie LOGIN PASSWORD 'paste-the-generated-password-here';
CREATE DATABASE vokie OWNER vokie ENCODING 'UTF8' TEMPLATE template0;
```

Notes:

- On the server the user does **not** get `CREATEDB` (it is needed only for running tests).
- The `unaccent` extension is created by a Django migration. Since PostgreSQL 13 it is a
  "trusted" extension, so the database owner can create it and no superuser is needed.
- `TEMPLATE template0` makes sure the database really uses UTF8, even if the server default
  is different.

**Check the connection:**

```bash
psql -h localhost -U vokie -d vokie -c "select current_user, version();"
```

### Environment variables

The app reads its settings from environment variables (or from the `.env` file in the project
directory).

| Variable | Description | Local value | Production example |
|---|---|---|---|
| `DB_NAME` | Database name | `vokie` | `vokie` |
| `DB_USER` | Database user | `vokie` | `vokie` |
| `DB_PASSWORD` | Database password | `vokie` | generated password |
| `DB_HOST` | Database host | `localhost` | `localhost` |
| `DB_PORT` | Database port | `5432` | `5432` |
| `DJANGO_SECRET_KEY` | Secret key for signing sessions etc. **Must be secret and unique.** | `change-me` | generated key (see below) |
| `DJANGO_DEBUG` | Debug mode, `1` = on, `0` = off. **Must be `0` in production.** | `1` | `0` |
| `DJANGO_ALLOWED_HOSTS` | Comma separated domain names the app answers to | `localhost,127.0.0.1` | `vokie.example.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma separated full addresses the app is opened at; forms do not work over HTTPS without it | (not needed) | `https://vokie.example.com` |
| `DJANGO_SECURE_SSL_REDIRECT` | Redirect HTTP to HTTPS in Django (only with `DJANGO_DEBUG=0`) | (not used) | `1` (default) |
| `DJANGO_HSTS_SECONDS` | How long browsers must use only HTTPS (only with `DJANGO_DEBUG=0`) | (not used) | `3600` (default), later `31536000` |
| `DJANGO_HSTS_INCLUDE_SUBDOMAINS` | HSTS also for all subdomains | (not used) | `0` (default) |
| `DJANGO_LOG_LEVEL` | Log level of Django messages | `INFO` | `INFO` |
| `VOKIE_SUGGESTION_PROVIDERS` | Comma separated sources of translation suggestions | `wiktionary` | `wiktionary` |
| `VOKIE_PRONUNCIATION_PROVIDERS` | Comma separated sources of pronunciation | `wiktionary` | `wiktionary` |

With `DJANGO_DEBUG=0` the app refuses to start when `DJANGO_SECRET_KEY` is missing or still
`change-me`:

```
django.core.exceptions.ImproperlyConfigured: Set DJANGO_SECRET_KEY to a secret value (see README.md).
```

Generate a secret key:

```bash
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Example production `.env`:

```bash
DB_NAME=vokie
DB_USER=vokie
DB_PASSWORD=Xk3...generated...9q
DB_HOST=localhost
DB_PORT=5432

DJANGO_SECRET_KEY=...generated...
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=vokie.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://vokie.example.com
```

Make sure the file can be read only by the user that runs the app:

```bash
chmod 600 .env
```

### Server

The examples use Debian/Ubuntu, the domain `vokie.example.com` and the directory `/srv/vokie`.
Replace them with your own values.

```
browser ──HTTPS──> nginx ──> /static/ files from /srv/vokie/staticfiles
                      └────> gunicorn (unix socket) ──> Django ──> PostgreSQL
```

#### 1. System user and code

```bash
# A user without login that runs the app
sudo adduser --system --group --home /srv/vokie vokie

# uv for that user (or install it system-wide)
sudo -u vokie -H bash -c "curl -LsSf https://astral.sh/uv/install.sh | sh"

# The code
sudo -u vokie -H git clone https://example.com/your/vokie.git /srv/vokie/app
cd /srv/vokie/app
```

#### 2. Settings, dependencies, database tables

```bash
# Settings: copy the example and fill in the production values (see "Environment variables")
sudo -u vokie cp .env.example .env
sudo -u vokie nano .env
sudo chmod 600 .env

# Dependencies without the development tools
sudo -u vokie -H ~vokie/.local/bin/uv sync --no-dev

# Tables, static files, first user
sudo -u vokie -H ~vokie/.local/bin/uv run python manage.py migrate
sudo -u vokie -H ~vokie/.local/bin/uv run python manage.py collectstatic --noinput
sudo -u vokie -H ~vokie/.local/bin/uv run python manage.py createsuperuser

# Must end without errors. The two warnings about HSTS subdomains and preload are expected,
# see "HTTPS" below.
sudo -u vokie -H ~vokie/.local/bin/uv run python manage.py check --deploy
```

#### 3. Translation suggestions (Czech Wiktionary)

Optional: without it the app works, it only shows no translation suggestions. It needs about
40 MB download, ~10 seconds, ~150 MB of memory while importing and ~35 MB in the database, so
a Raspberry Pi is fine.

```bash
# Download the data next to the app (not into the app directory)
sudo -u vokie -H curl -fLo /srv/vokie/cs-extract.jsonl.gz \
    https://kaikki.org/dictionary/downloads/cs/cs-extract.jsonl.gz

# Import (replaces older imported data)
cd /srv/vokie/app
sudo -u vokie -H ~vokie/.local/bin/uv run python manage.py import_wiktionary \
    /srv/vokie/cs-extract.jsonl.gz
# Imported 113645 entries (en 17504, fr 16449, de 13658, ...).
```

To keep the table smaller, import only the languages you learn:

```bash
sudo -u vokie -H ~vokie/.local/bin/uv run python manage.py import_wiktionary \
    /srv/vokie/cs-extract.jsonl.gz --languages en,es
```

Check it in the shell:

```bash
sudo -u vokie -H ~vokie/.local/bin/uv run python manage.py shell -c \
    "from dictionary.providers import get_suggestions; print(get_suggestions('palm', 'en', 'cs'))"
```

The app does not need a restart after the import. Wiktionary grows all the time, so repeat the
download and the import from time to time (e.g. every few months), see *Updating the app*.

#### 4. gunicorn as a systemd service

`/etc/systemd/system/vokie.service`:

```ini
[Unit]
Description=Vokie (gunicorn)
After=network.target postgresql.service

[Service]
User=vokie
Group=vokie
WorkingDirectory=/srv/vokie/app
# Creates /run/vokie for the socket, owned by the vokie user
RuntimeDirectory=vokie
ExecStart=/srv/vokie/app/.venv/bin/gunicorn config.wsgi \
    --bind unix:/run/vokie/gunicorn.sock \
    --workers 3 \
    --timeout 30 \
    --access-logfile -
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vokie
sudo systemctl status vokie
journalctl -u vokie -f        # logs, also Django errors
```

The app reads `.env` from its directory, so the settings do not have to be in the service file.

#### 5. nginx

`/etc/nginx/sites-available/vokie`:

```nginx
server {
    listen 80;
    server_name vokie.example.com;

    # Static files straight from disk, Django does not serve them in production
    location /static/ {
        alias /srv/vokie/app/staticfiles/;
        expires 7d;
        access_log off;
    }

    location / {
        proxy_pass http://unix:/run/vokie/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        # Django knows from this that the browser uses HTTPS
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/vokie /etc/nginx/sites-enabled/vokie
sudo nginx -t && sudo systemctl reload nginx
```

nginx must be able to read the static files and to connect to the socket:

```bash
# Let nginx (user www-data) into the vokie group
sudo usermod -aG vokie www-data
sudo chmod 750 /srv/vokie /srv/vokie/app
sudo systemctl restart nginx
```

#### 6. HTTPS

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d vokie.example.com
```

certbot adds the HTTPS part to the nginx file and renews the certificate by itself
(`systemctl list-timers | grep certbot`).

HSTS tells browsers to use only HTTPS. The app starts with `DJANGO_HSTS_SECONDS=3600` (one hour).
When everything works over HTTPS for a few days, raise it to one year:

```bash
DJANGO_HSTS_SECONDS=31536000
```

`check --deploy` also warns about `SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD`.
Turn on `DJANGO_HSTS_INCLUDE_SUBDOMAINS=1` only if **all** subdomains of your domain use HTTPS;
preload is not needed.

#### 7. Updating the app

```bash
cd /srv/vokie/app
sudo -u vokie git pull
sudo -u vokie -H ~vokie/.local/bin/uv sync --no-dev
sudo -u vokie -H ~vokie/.local/bin/uv run python manage.py migrate
sudo -u vokie -H ~vokie/.local/bin/uv run python manage.py collectstatic --noinput
sudo systemctl restart vokie
```

Newer dictionary data (not needed with every update):

```bash
sudo -u vokie -H curl -fLo /srv/vokie/cs-extract.jsonl.gz \
    https://kaikki.org/dictionary/downloads/cs/cs-extract.jsonl.gz
sudo -u vokie -H ~vokie/.local/bin/uv run python manage.py import_wiktionary \
    /srv/vokie/cs-extract.jsonl.gz
```

#### 8. Backups

A daily dump of the database, the last 14 days are kept.

`/etc/cron.daily/vokie-backup` (make it executable: `sudo chmod +x /etc/cron.daily/vokie-backup`):

```bash
#!/bin/sh
set -e
mkdir -p /var/backups/vokie
sudo -u postgres pg_dump --format=custom vokie > /var/backups/vokie/vokie-$(date +%F).dump
find /var/backups/vokie -name "vokie-*.dump" -mtime +14 -delete
```

Restore a backup (this replaces the current data):

```bash
sudo systemctl stop vokie
sudo -u postgres pg_restore --clean --if-exists --no-owner --role=vokie \
    --dbname=vokie /var/backups/vokie/vokie-2026-10-08.dump
sudo systemctl start vokie
```

Copy the backups to another machine from time to time; a backup on the same disk does not help
when the disk breaks.

---

## Upgrading PostgreSQL (Debian/Ubuntu)

Each major PostgreSQL version stores data in its own format. To upgrade, the old and the new
version must be installed **at the same time** while the data is converted.

Example: upgrade from 14 to 17.

```bash
# 1. Add the official PostgreSQL repository (once)
sudo apt install -y postgresql-common
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh
sudo apt update

# 2. Install the new version next to the old one
sudo apt install -y postgresql-17

# 3. If the install created an empty 17 cluster, remove it
pg_lsclusters
sudo pg_dropcluster 17 main --stop      # only if "17 main" is listed

# 4. Convert the data: new cluster takes port 5432, old one is stopped
sudo pg_upgradecluster 14 main
pg_lsclusters                           # 17 main 5432 online, 14 main 5433 down

# 5. Only after you checked that everything works, remove the old version
sudo pg_dropcluster 14 main
sudo apt purge -y postgresql-14
```

**Do not remove the old packages before step 4.** Without them the old data cannot be read.
