# Vocaboo

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
- GNU gettext, only to change translations (`sudo apt install gettext`)

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

Other people create their own account on the login page (*Vytvořit účet*), see
[Registration](#registration). Your first account is created by hand. You log in with your
**email**:

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

A forgotten password is reset by email (*Zapomenuté heslo?* on the login page). Without email
it can be changed on the command line:

```bash
uv run python manage.py changepassword martin@example.com
```

#### Registration

1. *Vytvořit účet* on the login page: email, password twice and, when `VOCABOO_REGISTRATION_CODE`
   is set, the invitation code.
2. The account is created turned off (`is_active=False`) and a six-digit code goes to the email
   (only its hash is saved, in `accounts.EmailVerification`).
3. The user enters the code on `/accounts/verify/`: the account is turned on and logged in.

The code works for 15 minutes, a new one can be sent once a minute, 5 wrong tries block the code
(then a new one is needed). Logging in to an account that is not confirmed yet sends a new code
and opens the page for it. Signing up with the email of an existing account shows the same page
and sends the owner a note with a link to a new password, so nobody learns from the page which
emails have an account. A hidden field catches robots. The numbers are in `config/settings.py`
(`VERIFICATION_*`, `UNVERIFIED_ACCOUNT_DAYS`).

Locally (`DJANGO_DEBUG=1` without `VOCABOO_EMAIL_HOST`) the emails are printed in the terminal
of `runserver`:

```
Subject: 482915 je tvůj kód pro Vocaboo
...
    482915
```

Accounts that never entered their code are deleted after 7 days (on the server by the nightly
job of `deploy/install.sh`, see [Server › Backups](#8-backups)):

```bash
uv run python manage.py cleanup_unverified --dry-run
# would delete  someone@example.com
# Unverified accounts: 1.
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
| Sentence | `Hello, kids.` | under the button (*+ věta, poznámka*), where you saw the word; another form of the word in braces: `He {ran} away.` |
| Sentence translation | `Ahoj, děti.` | the same place, optional, to understand the sentence; a word can be marked in braces too |
| Note | | the same place |

There is no field for the episode: the deck is the episode (e.g. *Series 1 › Episode 1*).

The line under the button shows what is in the sentence fields instead of a plain *Více*:
*+ věta, poznámka* when they are empty, or the sentence and its translation (two lines at most)
with *upravit*; a click opens the fields, *hotovo* closes them. Choosing a translation
suggestion also fills in the sentence of that meaning from the dictionary (only when the
sentence fields are empty), so a new word usually has a sentence without typing it:

```
EN  elevator          CS  výtah
[ + Přidat slovíčko ]
„Let's take the elevator.“ · Pojeďme výtahem.        upravit ›
```

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
foreign text and meanings from the dictionary of the app) are read when they are shown: on the back of the
card and on the word page, where a dictionary meaning can be added with *+ Učit se i tento
význam*. The back of the card, from the most important:

```
dlaň                                   ← the answer
Učíš se i: palm → palma                ← your own word with the same foreign text
„She can read from her palm.“          ← the sentence
pracka · lehký · světlý +3             ← the dictionary, small; first variant of each meaning
```

The browser shows as many dictionary meanings as fit on one line and *+N* for the rest; a click
on it shows them all (`fitMeanings` in `static/js/study.js`), each word once. The word page
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

### 10. The dictionary of the app (suggestions, other meanings, IPA, examples)

The app has its own dictionary built on **concepts** (meanings that are the same in all
languages), so it can grow to more languages without a dictionary for every pair (docs/slovnik.md,
spec 5.2). Today it has about 10 000 English words with 12 500 concepts in English and Czech:
Czech meanings, the most common first, an example sentence with its translation for every
meaning, IPA, a frequency band (1 = the 1 000 most common words of spoken English, 2 = the next
1 000 …), a CEFR level and topic tags. The original is JSON lines files in `dictionary/data/`;
the folder is in `.gitignore`, so the data is not in the repository: copy it to the server
yourself.

```
dictionary/data/concepts.jsonl     one concept per line, with its texts in each language
dictionary/data/words_en.jsonl     one English word per line, pointing to its concepts
dictionary/data/lexicon_tags.json  the topic tags
```

One concept and one word (formatted here):

```json
{"id": "palm.noun.1", "tags": ["telo"],
 "texts": {"en": {"words": "palm", "sentence": "She read my {palm}."},
           "cs": {"words": "dlaň", "note": "", "sentence": "Četla mi z {dlaně}."}}}

{"word": "palm", "pos": "noun", "band": 5, "level": "B1", "ipa": "pɑːm", "forms": ["palms"],
 "senses": ["palm.noun.1", "palm.noun.2"]}
```

The id of a concept (`word.part_of_speech.number`) never changes. Think of a big table: a row is
a concept, every language is a "column" with the translation, a note and a sentence (separate
fields). A suggestion for any pair X → Y finds the typed word in the column of language X (every
variant: "kočka; kocour" → *kočka*, *kocour*; the import makes this index) and takes the column of
language Y, so two languages meet in a concept (`palm.noun.1`), not in the English word *palm*
(which also means a palm tree):

```
CS → EN:  "kočka" in the cs column → cat.noun.1 → en: cat
ES → CS:  "gato"  in the es column → cat.noun.1 → cs: kočka; kocour
```

The words of a language (`words_en.jsonl`) add what belongs to a word: other forms (*palms*),
IPA, frequency and level. A new language comes bit by bit: texts of concepts in that language
(then all pairs with it have suggestions and topic words), later its words with forms and IPA.

Import it into the database (the tables `Concept`, `ConceptText`, `ConceptTextForm`,
`LexiconWord`, `WordForm`, `WordSense`, `LexiconTag`); importing again replaces the old data, so after editing the files
just run it again:

```bash
uv run python manage.py import_lexicon            # the base and all packages
# Imported 12564 concepts and 10027 words (en), 60 tags, 0 packages.
uv run python manage.py import_lexicon --check    # only check the files
```

**Packages of new words** extend the dictionary without touching the base: one folder per round
in `dictionary/data/extensions/`, named by its day (`2026-11-02/` with `concepts.jsonl`,
`words_en.jsonl` and `report.txt`). A package adds concepts and words, gives known concepts the
texts of new languages, or replaces a word with the same language, word and part of speech
(e.g. a new form `kids` for `kid`); every concept and word remembers its source (`base` /
`2026-11-02`, a filter in the admin). The whole round (which words, the rules for the AI that
writes the package, the steps on the server) is in [docs/slovnik.md](docs/slovnik.md):

```bash
uv run python manage.py missing_words                          # 1. on the server: what is missing
# 2. here: "Rozšiř slovník podle docs/slovnik.md" + the list → a package
uv run python manage.py extend_lexicon dictionary/data/extensions/2026-11-02 --check
uv run python manage.py extend_lexicon dictionary/data/extensions/2026-11-02   # 3. on the server
# Package 2026-11-02: concepts added 21, changed 0; words added 21, changed 2.
```

English words the users added but the app had no hint for, because the dictionary does not
know them (for its next round: give the list to the AI, let it check the words and write new
entries, then import again). It reads the decks of all users and changes nothing:

```bash
uv run python manage.py missing_words
# fella
# kids
# ogre
# suit up
uv run python manage.py missing_words --output missing.txt   # the same list into a file
```

One word per line, each once, A–Z. A word is known when it is a headword or another spelling of
an entry (`mum`); forms like `kids` or `ran` are listed, so the AI decides whether they need an
entry. One letter and words with digits are left out.

What the app takes from it:

- **Translation suggestions** while a foreign word is typed: `present` → *dárek* (podst. jm.),
  *současnost* (podst. jm.), *představit* (slov.). A click puts the suggestion into the
  translation field. Other spellings are found too (`mum` → the entry `mom`). The edit form
  shows them too, right away for the word in the form. When the foreign word changes after a
  choice, the sentence filled in from the suggestion is taken away again (it belonged to the
  old word, e.g. `impose` → `trinket`); a sentence the user wrote or changed stays.
- **Other meanings** on the back of the card and on the word page (see above).
- **IPA** under the foreign word, when the user turns it on.
- **Example sentence** in the summary of a test (*Tohle slovíčko ti nejde*, *Použít*): the
  sentence of the meaning whose translation matches the user's word, with its translation.

Without the import the app works the same, it just shows none of these. Only English decks with
*Mluvím* = Czech get them for now.

```python
from dictionary.providers import get_suggestions, get_pronunciation

get_suggestions("palm", "en", "cs").suggestions[1].translation  # 'palma'
get_pronunciation("palm", "en").ipa  # 'pɑːm'
```

The sources are behind one interface in `dictionary/providers.py`, their order is the environment
variable `VOCABOO_SUGGESTION_PROVIDERS` (and `VOCABOO_PRONUNCIATION_PROVIDERS`), default `lexicon`, so
another source can be added later without changing the rest of the app.

**Pronunciation.** On the back of a test card and on the word page the foreign word gets a grey
🔊 (on the card always at the right edge, on the line of the foreign word; on the word page next
to the title); a click or the key **P** lets the **voice of the browser** (Web Speech API) read
the word. It also reads the sentence of the card (🔊 at its end, key **V**). The button comes
hidden and is shown when the browser can speak at all; the voice is chosen when it plays
(`voiceFor` in `static/js/app.js`, an American voice is preferred for English; without a known
voice the language alone is passed and the browser chooses). The speaker cannot be turned off. Voices are good on Android,
Windows, Mac and in Chrome on Linux, robotic or missing in Firefox on Linux. It plays by itself
(*Nastavení › Test › Audio › Přehrát automaticky*, on by default): foreign → native as
soon as the card comes (the foreign word is the question, so 🔊 is on the front), native →
foreign after *Ukázat* (the foreign word is the answer); it reads the *word* or the whole
*sentence* (the word when there is no sentence). Browsers do not let a page speak before the
user clicked on it, so the very first card of a test is not read by itself. The IPA from the
dictionary, e.g. `[pɑːm]` small under the word, is off by default (*Ukazovat zápis výslovnosti
(IPA)*). A server voice (e.g. Piper) can be added later as another pronunciation source.

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

The setup page shows how many cards the test would have next to the choices (*jen k opakování
a nová (42)*, *všechna (85)*), for the ticked decks and the direction; the
part is reloaded by HTMX after every change (`study:counts`, `services.card_counts`). From the
deck page (`?deck=<id>`) it shows only that deck instead of the tree, *Změnit* opens the tree.

- **Scope "due"**: first the cards that are due, then new cards. Inside both groups the order is
  **random**, so the two directions of a word are usually far apart (when they came one card
  apart, the second one was easy only thanks to short memory). Every test gets its own random
  number (`StudySession.shuffle_seed`) and the order is the hash of it and the card, so the order
  stays the same for the whole test, also after a reload or on another device. A card rated 😵
  comes back by itself after 10 minutes, at a random place.
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

Start a test from the bar (*Procvičit*, "practise") or from a deck (*Procvičit slovník*):
choose decks, direction and which cards. Then:

1. The card shows the question. In the foreign → native direction the sentence is shown too,
   with the word marked.
2. **Ukázat** or **Space** turns the card. The pronunciation of the foreign word, the answer,
   your other words with the same text, the sentence and other meanings are on the back.
   **P** (or 🔊) reads the word aloud.
3. Rate yourself with one of the buttons or keys **1–4**. Under each emoji is the real next
   interval of this card, e.g. `7 dní`. The next card comes without reloading the page.
4. At the end the summary shows the counts and the words rated 😕 or 😵, with
   *Procvičit chybné znovu* (a new test with only those words).
5. **Tohle slovíčko ti nejde:** the summary also offers one word of the test that fails for a
   long time and has no sentence yet, with two fields: the sentence under the foreign word and
   its translation under the native one (side by side on a computer, one under the other on a
   phone). "Fails for a long time" is counted from `ReviewLog` (nothing extra is stored): of the
   last 8 answers at least 3, and at least half wrong (😕 counts as half), so a known word that
   was forgotten once does not come. When the dictionary has a sentence for this meaning
   (`get_example_sentence` in `dictionary/providers.py`), it is offered
   with *Použít*, which fills both fields. Above the form are coloured dots of the last answers
   for each direction (`EN → CS`, `CS → EN`), oldest first, so it is clear in which direction the
   word fails and whether it gets better: the last 8, older ones behind *+N* (its tooltip says
   how they went), a click shows up to 30 and a link to the word page when there are more.

```python
services.hard_word_without_sentence(session)
# {'deck_term': <DeckTerm: palm → dlaň @ HIMYM>, 'bad': 5, 'total': 7}
```

With a sentence translation the native → foreign card shows it on the front above the gap
(`„Mně se ta písnička také nelíbí.“ / „I don't like this song ___.“`), the foreign → native card
on the back.

**✎** under the card (or the key **E**) opens the edit of the word, e.g. to fix a typo:
`/decks/4/words/19/edit/?test=52`. With a running test the form has *Uložit a zpět do testu* and
*Neukládat a zpět do testu* (no *Odebrat z tohoto slovníku*); both go back to the test, and the
same card comes again because it was not rated yet. Without `?test`, or with a finished test,
the form works as before.

The time until the card is turned (`think_ms`) and until the rating (`decide_ms`) is measured in
the browser and paused while the page is hidden (another app, locked phone).

### 14. Dashboard, statistics and word page

- **Colours:** one colour, indigo: `--primary` (`#5b4bc4`, `#a59af2` in the dark) with
  `--primary-light` (bars of other days, soft fills) and `--primary-dark` (the account circle,
  hover); Pico's `--pico-primary*` variables point to it, so links, buttons, check boxes and focus
  rings are indigo too. The ratings keep their own green, light green, orange and red, so no other
  strong colour is used.
- **Round corners:** one scale – cards `--radius-card` (0.75rem), buttons and fields
  `--radius-control` (0.5rem, also Pico's `--pico-border-radius`), small things `--radius-small`
  (0.25rem); only the account circle and `⋯` are round.
- **Look:** one column on every screen (at most 46rem wide, the same on a computer and a phone),
  the sections of the dashboard as cards. The bar has `Vocaboo`, a pill with an indigo frame `▶ Procvičit` (the same
  on a phone; the main action, on every page), `Statistiky`, `Nápověda` (both in the account menu on a phone) and a
  circle with the first letter of the e-mail, which opens the account menu (e-mail, the look `☀️ Den · 🌙 Noc · Auto` – `data-theme` on
  `<html>`, kept in `localStorage` of the browser and set before the page is drawn –, Nastavení,
  Admin for staff, Odhlásit; a Pico `details.dropdown`, closed by a click elsewhere). The dashboard starts with the card *Dnes*; `+ Nový` (new deck) is next to
  the heading *Slovníky*. The deck page and the test pages look the same: the deck page has its
  name with a small menu `⋯` (rename, move, delete), the button `▶ Procvičit slovník` (the same indigo frame as `▶ Procvičit` in the bar)
  and the cards *Nové slovíčko*, *Slovíčka* and *Podslovníky* (with `+ Nový`); the setup of a
  test has the cards *Slovníky*, *Směr* and *Které kartičky* and the big button `▶ Spustit test`;
  the test has a thin progress bar above the card. The summary of a test, the statistics and
  the word page use the same cards; the word page has `✎ Upravit` next to the word and a menu `⋯`
  (move, remove from this deck). The dashboard order is *Co ti dnes nejde* (only when there is
  something), *Slovníky*, *Dnes*.

- **Hledat** (a light strip `Hledat slovíčko…` over the deck tree in the card *Slovníky*, **/** jumps into it; the results under the heading; Enter without JavaScript opens `/search/?q=cetka`): all the user's words, in every variant, the sentence and its
  translation and the note, without accents and case (`cetka` finds `Četka`), from 2 letters,
  live while typing (HTMX). Words matching in the word or translation come first, then the ones
  with the text in a sentence or note; the match is marked, each word shows its decks (last 3
  levels of the path), a link to the word page and ✎ to edit; at most 50 results.

```python
services.search_terms(user, "impose")
# [SearchHit(term=impose → obtěžovat, ...), SearchHit(term=trinket → cetka, found_in=[...])]
```

- **Statistiky** (`/stats/`, in the navigation; on a phone only the icon 📊): tiles with the number
  of words, words known (foreign → native right at least twice in a row), the streak of days in a
  row 🔥 and answers; a line chart of all words from the day of the first word (by days for 2
  weeks, by weeks up to 4 months, by months up to 2 years, then by quarters; values on the y axis,
  e.g. 0 / 20 / 40 / 60 / 80; the exact number on hover over a dot), **Poslední testy** (the last 10
  tests with an answer, one row each: the date and time, the last 3 decks of the path, e.g. `… ›
  Seriály › HIMYM › S01` (the whole path in the title), the direction (`EN → CS`, `CS → EN`, `EN ↔
  CS`), the scope with the limit, the words, success as percent with a short bar of one colour
  (the counts of 😎 🤔 😕 😵 in its title), and the time of the test (⏹ when not finished); with ↔
  every word comes twice; above it e.g. `Za 14 dní 9 testů · průměrně 24 slovíček`; a click opens
  the summary of the test), and **Co ti nejde**: the words that are hard for you, each with its
  translation and a link to the word page, for the last 30 days (no choice of the period: enough
  words for the cards, and still about now). A word is hard when it had 😵 or 😕 in the period and is not known yet; each
  word is shown once, as a card that turns like in a test (click or Enter; a short 3D turn, none
  with reduced motion): in front the animal with the name of the kind and one side of the word
  (every second card the native side; 🦀 the hard direction), on the back the other side, a small
  note why and the link *Detail*: 🦈 *Největší nepřítel* (`suit up` – obleč se do obleku, 3×
  vůbec nevím z 5 pokusů), 🦀 *Jen jedním směrem* (`EN → CS ano, CS → EN ne`), 🐿️ *Zapomínáš*
  (wrong after 2 right answers in a row, `2× zapomenuto`), 🐒 *Horská dráha* (most changes between
  right and wrong, at least 3), 🐇 *Moc rychle* (the fastest 😵, under 3 s), 🦎 *Pleteš si* (two hard
  words with the same translation, `borrow · lend` – půjčit), 🦒 the longest hard word, 🐢 the
  longest thinking, 🐌 the oldest hard word (`přidáno před 45 dny`). Everything is counted from
  `Term` and `ReviewLog` when the page opens (`study/stats.py`); the chart is plain SVG without a
  chart library.
- Above the decks the dashboard shows **Dnes** (`stats.today_overview`), only good news of the tests:
  🎯 words right for the first time ever today (😎 or 🤔, any direction), 🎓 words learned today (for the first time right twice in a row foreign → native,
  the same "umíš" as on the statistics page), 📚 different words in today's tests and ⏱️ the
  time in tests. Each number is a tab: a click shows its last 7 days in a bar chart under
  them (the value above each bar, the other days light blue, today blue), without reloading the
  page.
- Under the decks the dashboard shows **Co ti dnes nejde**: up to 3 smaller flip cards in one row,
  only from today's answers: 🐢 the longest thinking, 🦀 only one direction and 🐘 *Pořád dokola*
  (a word hard today with the most attempts in the whole history, at least 3, e.g. `zase nevím ·
  už 12. pokus`). The section is not there when nothing was hard today.
- The card *Slovníky* has only `+ Nový`, the search and the tree (the totals are on the
  statistics page, moving by dragging is explained in the help).
- Each deck in the tree has its words in brackets right after the name, e.g.
  `HIMYM (26)`, so it is easy to see in a big tree; when some words are due, their number
  is in the brackets too: `HIMYM (26 ↻ 9)`, the `↻ 9` a bit smaller (title `9 k opakování`).
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
  next repetition and counts of ratings for each direction, a ring with the share of correct
  answers, coloured dots of the last 30 answers (oldest first, the colours of the rating
  buttons; `answer_dots` in `study/services.py`), and the history of answers.

#### The app on the home screen (PWA)

The app can be installed on a phone or a computer like an app (no store, no offline mode):

- **Android, Chrome / Edge on a computer:** *Nainstalovat* in *Nastavení › Aplikace* (and on
  the card on the overview) opens the browser's own *Install?* window (`beforeinstallprompt` in `static/js/app.js`).
- **iPhone / iPad:** Apple has no such window, so the same item shows the steps
  *Sdílet → Přidat na plochu → Přidat* (dialog `#install-guide-ios` in `templates/base.html`).
- **Android without the window** (Firefox and some other browsers, or Chrome before it offers
  the installation): the steps from the browser menu *⋮ → Instalovat aplikaci / Přidat na
  plochu* (dialog `#install-guide-android`). The system is told by `navigator.userAgent`.
- On a phone the overview offers it once (*Dej si Vocaboo na plochu*); after *Teď ne* it stays
  hidden in that browser (`localStorage` key `vocaboo.installDismissed`); the offer in
  *Nastavení* stays (only where the browser can install the app and it is not installed yet).

The browser offers the installation only over **HTTPS** (or on `localhost`) and with a valid
`static/manifest.webmanifest`. Check it in Chrome: *DevTools › Application › Manifest*. The
login lasts 90 days since the last visit (`SESSION_COOKIE_AGE`), because on an iPhone the app on
the home screen has its own cookies and its own login.

### 15. Help

The app has a help page for users (*Nápověda* / *Help* in the top bar, `/help/`) with tabs
*Slovníky*, *Slovíčka*, *Test* and *Přehled a statistiky*. Every tab is its own page in every
language: `templates/help/cs/`, `templates/help/en/` and `templates/help/es/<tab>.html` (a language without
its own page gets the English one); the frame with the tabs is `templates/help/base_help.html`
and the list of tabs is `HELP_TOPICS` in `config/views.py`. The
table of rating buttons is made from `study/ratings.py`, so it stays right when the buttons
change. When a feature changes, update its help tab too, in all languages.

### 16. Languages of the app (translations)

The app speaks Czech, English and Spanish (European, *tú*; `LANGUAGES` in `config/settings.py`). The source texts in
the code are **English**; Czech is a translation in `locale/cs/LC_MESSAGES/django.po`. The
compiled file `django.mo` is in git too, so the app and the tests work without gettext.

Which language a page has:

| Who | Language |
|---|---|
| logged in, *Nastavení › Aplikace › Jazyk aplikace* is set | that language (`User.ui_language`) |
| logged in, the setting is *Podle prohlížeče* | the browser language (`Accept-Language`) |
| not logged in | the switch *Čeština · English* under the login form (a cookie), else the browser |
| a browser language the app does not have | English (`LANGUAGE_CODE`) |

Mark every text for the user in the code, in English:

```python
from django.utils.translation import gettext as _, ngettext, pgettext

messages.success(request, _("Settings saved."))
# Plurals: Czech has 3 forms (1 slovíčko, 2 slovíčka, 5 slovíček), ngettext knows them
text = ngettext("%(count)s word", "%(count)s words", count) % {"count": count}
# The same English word with a different meaning gets a context
label = pgettext("rating", "Partly")
```

```django
{% load i18n %}
<h2>{% translate "Decks" %}</h2>
{% blocktranslate trimmed count counter=words %}
  {{ counter }} word
{% plural %}
  {{ counter }} words
{% endblocktranslate %}
```

After changing texts, update and compile the catalog, then fill the new Czech texts in
`django.po` (the test `tests/test_translations.py` fails while a text has no translation or
the `.mo` file is old):

```bash
# django = Python and templates, djangojs = the JavaScript files
for domain in django djangojs; do
  uv run python manage.py makemessages -d $domain -l cs --no-location \
      --ignore '.venv/*' --ignore 'templates/help/cs/*' --ignore 'templates/help/en/*' --ignore 'tests/*' \
      --ignore 'staticfiles/*' --ignore '*/migrations/*' --ignore 'static/vendor/*'
done
# ... translate the empty msgstr "" in locale/cs/LC_MESSAGES/django.po and djangojs.po ...
uv run python manage.py compilemessages -l cs --ignore '.venv/*'
```

In JavaScript use `gettext("…")` (and `ngettext`, `interpolate`); the texts come from
`/jsi18n/` (Django's `JavaScriptCatalog`), which `base.html` loads before the other scripts:

```javascript
button.setAttribute("aria-label", gettext("Show password"));
```

Names of languages (`Language.label`, e.g. *English* / *Angličtina*) are in `LANGUAGE_NAMES`
in `vocabulary/models.py`; a code that is not there shows the name from the database. Date
formats for each language are in `config/formats/<code>/formats.py`
(`SHORT_DATETIME_FORMAT`, `MONTH_DAY_FORMAT`); templates use them by name:

```django
{{ log.reviewed_at|date:"SHORT_DATETIME_FORMAT" }}   {# 8. 10. 2026 14:05 / 10/8/2026 2:05 PM #}
```

A new language, e.g. German: add `("de", "Deutsch")` to `LANGUAGES`, run `makemessages -l de`,
translate `locale/de/LC_MESSAGES/django.po` and compile it. Nothing else in the code changes.

The help pages are not in the catalog: each language has its own templates, see
[15. Help](#15-help).

### 17. Run the app

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
accounts/     custom user model (login with email), admin, login/logout, registration with a code from the email, forgotten password
vocabulary/   languages, decks (dictionary tree), words and their variants
  services.py   all rules for decks and words, views only call these functions
  sentences.py  the word in a sentence: found or {marked}, highlighted or replaced by a gap
dictionary/   the dictionary of the app (concepts and words of each language: import_lexicon, extend_lexicon, missing_words) and its sources (providers.py)
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
  js/study.js   test screen: turning the card, keyboard, time measuring, help window
  js/tree.js    dashboard tree: moving decks by drag and drop
  vendor/       third-party files kept in the repository (see below)
tests/        all tests, one folder per app
  conftest.py   shared pytest fixtures (users, languages, fast password hashing)
  project/      whole project: database, layout, help pages
  accounts/     users, login, settings
  vocabulary/   languages, decks, words, duplicates, sentences, seed_demo
  dictionary/   the dictionary of the app: import, suggestions, other meanings, IPA
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
| `DJANGO_ALLOWED_HOSTS` | Comma separated domain names the app answers to | `localhost,127.0.0.1` | `vocaboo.me` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma separated full addresses the app is opened at; forms do not work over HTTPS without it | (not needed) | `https://vocaboo.me` |
| `DJANGO_SECURE_SSL_REDIRECT` | Redirect HTTP to HTTPS in Django (only with `DJANGO_DEBUG=0`) | (not used) | `1` (default) |
| `DJANGO_HSTS_SECONDS` | How long browsers must use only HTTPS (only with `DJANGO_DEBUG=0`) | (not used) | `3600` (default), later `31536000` |
| `DJANGO_HSTS_INCLUDE_SUBDOMAINS` | HSTS also for all subdomains | (not used) | `0` (default) |
| `DJANGO_LOG_LEVEL` | Log level of Django messages | `INFO` | `INFO` |
| `VOCABOO_SUGGESTION_PROVIDERS` | Comma separated sources of translation suggestions | `lexicon` | `lexicon` |
| `VOCABOO_PRONUNCIATION_PROVIDERS` | Comma separated sources of pronunciation (IPA) | `lexicon` | `lexicon` |
| `VOCABOO_EMAIL_HOST` | SMTP server for emails (codes of new accounts, forgotten password); empty with `DJANGO_DEBUG=1` = emails in the console | (empty) | `smtp.gmail.com` |
| `VOCABOO_EMAIL_PORT` | SMTP port | (not used) | `587` (default) |
| `VOCABOO_EMAIL_USE_TLS` | STARTTLS on the SMTP connection | (not used) | `1` (default) |
| `VOCABOO_EMAIL_USER` | SMTP login | (not used) | `vocaboo.app@gmail.com` |
| `VOCABOO_EMAIL_PASSWORD` | SMTP password (Gmail: app password) | (not used) | `abcdabcdabcdabcd` |
| `VOCABOO_EMAIL_FROM` | Sender of the emails | (not used) | `Vocaboo <vocaboo.app@gmail.com>` |
| `VOCABOO_REGISTRATION_CODE` | Invitation code the registration asks for; empty = anybody can sign up | (empty) | `kamaradi2026` |

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
DJANGO_ALLOWED_HOSTS=vocaboo.me
DJANGO_CSRF_TRUSTED_ORIGINS=https://vocaboo.me

VOCABOO_EMAIL_HOST=smtp.gmail.com
VOCABOO_EMAIL_USER=vocaboo.app@gmail.com
VOCABOO_EMAIL_PASSWORD=abcdabcdabcdabcd
VOCABOO_EMAIL_FROM=Vocaboo <vocaboo.app@gmail.com>
VOCABOO_REGISTRATION_CODE=kamaradi2026
```

**Emails over Gmail** (free, about 500 emails a day):

1. Create a separate Google account for the app, e.g. `vocaboo.app@gmail.com`.
2. Turn on 2-step verification (*Google Account › Security*).
3. Create an app password on <https://myaccount.google.com/apppasswords> (name `vocaboo`); the
   16 letters without spaces go to `VOCABOO_EMAIL_PASSWORD`.
4. The sender (`VOCABOO_EMAIL_FROM`) must be that Gmail address.

Another SMTP service (Brevo, Resend, your own domain) needs only other `VOCABOO_EMAIL_*`
values. Test the sending on the server:

```bash
sudo -u vocaboo -H ~vocaboo/.local/bin/uv run python manage.py sendtestemail you@example.com
```

Make sure the file can be read only by the user that runs the app:

```bash
chmod 600 .env
```

### Server

The examples use Debian/Ubuntu, the domain `vocaboo.me` and the directory `/srv/vocaboo`.
Replace them with your own values.

```
browser ──HTTPS──> nginx ──> /static/ files from /srv/vocaboo/staticfiles
                      └────> gunicorn (unix socket) ──> Django ──> PostgreSQL
```

#### 1. System user and code

```bash
# A user without login that runs the app
sudo adduser --system --group --home /srv/vocaboo vocaboo

# uv for that user (or install it system-wide)
sudo -u vocaboo -H bash -c "curl -LsSf https://astral.sh/uv/install.sh | sh"

# The code
sudo -u vocaboo -H git clone https://example.com/your/vocaboo.git /srv/vocaboo/app
cd /srv/vocaboo/app
```

#### 2. Settings, dependencies, database tables

```bash
# Settings: copy the example and fill in the production values (see "Environment variables")
sudo -u vocaboo cp .env.example .env
sudo -u vocaboo nano .env
sudo chmod 600 .env

# Dependencies without the development tools
sudo -u vocaboo -H ~vocaboo/.local/bin/uv sync --no-dev

# Tables, static files, first user. With DJANGO_DEBUG=0 collectstatic gives every file a mark
# of its content in the name (css/app.css -> css/app.ec90807cc878.css, ManifestStaticFilesStorage),
# so after a new version browsers download the new file instead of an old copy.
sudo -u vocaboo -H ~vocaboo/.local/bin/uv run python manage.py migrate
sudo -u vocaboo -H ~vocaboo/.local/bin/uv run python manage.py collectstatic --noinput
sudo -u vocaboo -H ~vocaboo/.local/bin/uv run python manage.py createsuperuser

# Must end without errors. The two warnings about HSTS subdomains and preload are expected,
# see "HTTPS" below.
sudo -u vocaboo -H ~vocaboo/.local/bin/uv run python manage.py check --deploy
```

#### 3. The dictionary of the app

Optional: without it the app works, it only shows no translation suggestions, other meanings,
IPA and example sentences. The data is not in the repository (`dictionary/data/` is in
`.gitignore`), so copy the two files from your computer and import them; it takes a few seconds
and about 8 MB in the database, a Raspberry Pi is fine.

```bash
# On your computer
scp dictionary/data/concepts.jsonl dictionary/data/words_*.jsonl dictionary/data/lexicon_tags.json \
    pi@raspberrypi:/tmp/

# On the server
sudo mkdir -p /srv/vocaboo/app/dictionary/data
sudo mv /tmp/concepts.jsonl /tmp/words_*.jsonl /tmp/lexicon_tags.json /srv/vocaboo/app/dictionary/data/
sudo chown -R vocaboo:vocaboo /srv/vocaboo/app/dictionary/data
cd /srv/vocaboo/app
sudo -u vocaboo -H ~vocaboo/.local/bin/uv run python manage.py import_lexicon
# Imported 12564 concepts and 10027 words (en), 60 tags, 0 packages.
```

Check it in the shell:

```bash
sudo -u vocaboo -H ~vocaboo/.local/bin/uv run python manage.py shell -c \
    "from dictionary.providers import get_suggestions; print(get_suggestions('palm', 'en', 'cs'))"
```

The app does not need a restart after the import. A package of new words goes to
`/srv/vocaboo/app/dictionary/data/extensions/` and is added with `extend_lexicon` (see
[docs/slovnik.md](docs/slovnik.md)); keep the packages there, a full `import_lexicon` reads them
again. After you change the base files, copy them again and run the import again; it replaces
the old data.

#### 4. Service, nginx and nightly jobs: `deploy/install.sh`

The files for the system are in the repository, in `deploy/`:

```
deploy/
  vocaboo.service   the app as a systemd service (gunicorn on a unix socket)
  nginx.conf        nginx: static files from disk, the rest to gunicorn
  cron-daily        every night: a dump of the database (14 days kept) and cleanup_unverified
  install.sh        set up the server once (installs the three files above)
  deploy.sh         update the app (git pull, libraries, migrate, collectstatic, restart)
```

Set up the server once, after steps 1–3:

```bash
sudo /srv/vocaboo/app/deploy/install.sh
# ==> nginx
# ==> Access rights
# ==> The app as a service
# ==> Libraries
# ...
# ==> Check
#     The login page answers (HTTP 200).
# Done. At home open http://192.168.0.103/
```

It installs nginx when it is missing, locks `.env` (only `vocaboo` reads it), lets nginx
(`www-data`) into the `vocaboo` group, installs and starts the service, puts the nginx site in
place (and removes the welcome page of nginx), installs `/etc/cron.daily/vocaboo` and checks that
the login page answers. Running it again does no harm. The nginx file is installed only when it
is not there yet, because certbot adds its HTTPS part to it; to install a changed
`deploy/nginx.conf`, delete `/etc/nginx/sites-available/vocaboo` first and run certbot again.

Logs of the app (also Django errors):

```bash
journalctl -u vocaboo -f
sudo tail -f /var/log/nginx/error.log
```

The app reads `.env` from its directory, so the settings do not have to be in the service file.

To test at home over plain http before HTTPS works, put `DJANGO_SECURE_SSL_REDIRECT=0` and the
address of the Pi into `.env` (`DJANGO_ALLOWED_HOSTS=vocaboo.me,192.168.0.103`). The pages open,
but logging in works only over HTTPS (the session cookie is `Secure`). Remove the line when
HTTPS works.

#### 5. Commands of the app on the server

Every command runs as the `vocaboo` user (it owns the code, `.env` and `.venv`). A short alias
saves typing, e.g. in fish:

```fish
alias voc 'sudo -u vocaboo -H /srv/vocaboo/.local/bin/uv run --no-dev --directory /srv/vocaboo/app python manage.py'
funcsave voc
voc createsuperuser
voc import_lexicon
```

in bash (`~/.bashrc`):

```bash
alias voc='sudo -u vocaboo -H /srv/vocaboo/.local/bin/uv run --no-dev --directory /srv/vocaboo/app python manage.py'
```

`--no-dev` keeps the development tools (pytest, ruff) off the server. `--directory` is needed
because only `vocaboo` (and nginx) may enter `/srv/vocaboo/app`, your own user may not.

#### 6. HTTPS

Two ways: **Cloudflare Tunnel** (no open port on the router, works behind a second router of the
internet provider or a shared IP address) or **certbot** (the router forwards ports 80 and 443
to the server, which needs a public IP address).

**Cloudflare Tunnel** (free; this server uses it):

1. Add the domain to Cloudflare (*Connect a domain*, plan *Free*) and replace the nameservers at
   the registrar (Porkbun: *Domain Management › Nameservers*) with the two from Cloudflare.
   DNSSEC at the registrar must be off.
2. *Cloudflare One › Networks › Tunnels › Create a tunnel* (*Cloudflared*), choose *Debian* and
   *arm64*, run the shown commands on the server. The second one installs the service:
   `sudo cloudflared service install <token>` (keep the token secret). Do not run
   `cloudflared tunnel run` by hand as well.
3. In the tunnel *Add route › Published application*: domain `vocaboo.me`, service
   `http://localhost:80`. Cloudflare creates the DNS record by itself.
4. Cloudflare *SSL/TLS › Edge Certificates*: *Always Use HTTPS* on.
5. In `.env` remove `DJANGO_SECURE_SSL_REDIRECT=0` and `sudo systemctl restart vocaboo`.

nginx behind the tunnel gets plain http; `deploy/nginx.conf` tells Django the protocol from
Cloudflare's `X-Forwarded-Proto` header (the `map` at the top), otherwise the HTTPS redirect of
Django would never end. No certbot, the certificate is Cloudflare's. Check the tunnel:

```bash
sudo systemctl status cloudflared
journalctl -u cloudflared -n 30
```

**certbot** (with forwarded ports):


```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d vocaboo.me
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

On your computer `git push`, then on the server:

```bash
sudo /srv/vocaboo/app/deploy/deploy.sh
# ==> Getting the new code
# ==> Libraries
# ==> Database tables
# ==> New packages of the dictionary
# No new packages of the dictionary.
# ==> Static files
# ==> Checking the settings
# ==> Restarting the app
# ==> Done: 3f2a9c1 feat: ...
```

It stops at the first error; when the app does not start again, it prints the last lines of its
log.

A new package of the dictionary (not in git): copy its folder to the server, `deploy.sh` adds
it (`extend_lexicon --new` adds every folder of `extensions/` that is not in the database yet;
the added ones are in the admin under *Slovník › Balíčky slovníku*):

```bash
# On your computer
scp -r dictionary/data/extensions/2026-10-23 pi:/tmp/
# On the server
sudo mv /tmp/2026-10-23 /srv/vocaboo/app/dictionary/data/extensions/
sudo chown -R vocaboo:vocaboo /srv/vocaboo/app/dictionary/data
sudo /srv/vocaboo/app/deploy/deploy.sh
```

Newer dictionary data (only when the files changed): copy `concepts.jsonl`, `words_*.jsonl` and
`lexicon_tags.json` to `dictionary/data/` again and run `import_lexicon` as in *The dictionary of
the app*. **Once, after the update that brought concepts** (migration `dictionary.0005_concepts`,
which drops the old tables), copy the new files and run `import_lexicon` in any case; the old
`lexicon_en_cs.jsonl` is not read any more.

#### 8. Backups

A daily dump of the database to `/var/backups/vocaboo/`, the last 14 days are kept
(`/etc/cron.daily/vocaboo`, installed by `deploy/install.sh` from `deploy/cron-daily`). Try it
by hand:

```bash
sudo /etc/cron.daily/vocaboo
ls -l /var/backups/vocaboo/
```

The same nightly job deletes new accounts that never entered the code from the email
(`cleanup_unverified`).

Restore a backup (this replaces the current data; `vokie` is `DB_NAME` / `DB_USER` from `.env`):

```bash
sudo systemctl stop vocaboo
sudo -u postgres pg_restore --clean --if-exists --no-owner --role=vokie \
    --dbname=vokie /var/backups/vocaboo/vocaboo-2026-10-08.dump
sudo systemctl start vocaboo
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
