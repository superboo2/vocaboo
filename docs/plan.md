# Vokie – plán implementace MVP

**Stav: MVP hotové (kroky 0–12).** Další práce podle fází 2–4 ve `spec.md`.

Plán vychází z `docs/spec.md`. MVP je rozdělené do malých kroků. Každý krok končí ve funkčním stavu, který jde vyzkoušet a commitnout.

**Postup u každého kroku:**
1. Claude popíše, co přesně v kroku udělá (soubory, modely, chování).
2. Autor odsouhlasí, případně upraví.
3. Claude kód napíše a spustí testy.
4. Autor zkontroluje a commitne sám.

---

## Potvrzená rozhodnutí

| Téma | Návrh | Poznámka |
|---|---|---|
| Verze Djanga | **6.1** (aktuální 6.1.2) | Django 6 má vestavěné *template partials* (`{% partialdef %}`), které se hodí pro HTMX: jedna šablona, ze které jde vykreslit jen kus. Alternativa je 5.2 LTS (podpora do 2028). Z 6.1 se později přejde na 6.2 LTS. |
| DB driver | `psycopg` 3 | |
| HTMX, Pico.css | stažené do `static/` (ne CDN) | Funguje bez internetu, verze je pod kontrolou. |
| Testy | `pytest` + `pytest-django` | Testují se hlavně servisní funkce. |
| Lint, formátování | `ruff` | |
| Konfigurace | proměnné prostředí v souboru `.env` (není v gitu) + `.env.example` (v gitu) | |
| README | průběžně aktualizované, s návodem na lokální vývoj **i nasazení** (databáze, proměnné prostředí, migrace…) | Každý krok, který mění způsob spuštění nebo nasazení, doplní README. |

---

## Krok 0: Příprava prostředí
- **bez Dockeru:** používá se lokálně nainstalovaný PostgreSQL, autor jen vytvoří databázi a uživatele (příkazy v README)
- databázový uživatel potřebuje lokálně právo `CREATEDB`, protože testy si vytváří vlastní testovací databázi
- `.env.example` (DB připojení, `SECRET_KEY`, `DEBUG`), `.env` v `.gitignore`
- závislosti v `pyproject.toml` přes `uv add` (django, psycopg, dev: pytest, pytest-django, ruff)
- odstranit vygenerovaný `main.py`
- `.gitignore`
- `README.md`: popis projektu, lokální vývoj, sekce **Nasazení** (vytvoření databáze a uživatele, proměnné prostředí)

**Hotovo, když:** jde se připojit k databázi `vokie` a `uv run python -c "import django"` funguje.

## Krok 1: Django projekt
- `django-admin startproject config .`
- nastavení čtené z prostředí, připojení na PostgreSQL
- `LANGUAGE_CODE = "cs"`, `TIME_ZONE = "Europe/Prague"`, `USE_TZ = True`
- texty v kódu a šablonách obalené pro překlad (`gettext`), i když UI je zatím jen česky
- `templates/`, `static/`
- **zatím žádná migrace** (kvůli vlastnímu User modelu v dalším kroku)

**Hotovo, když:** `uv run python manage.py check` projde.

## Krok 2: Uživatelé a přihlášení (`accounts`)
- vlastní `User` (dědí z `AbstractUser`), přihlášení e-mailem (`USERNAME_FIELD = "email"`), vlastní manager
- e-mail unikátní bez ohledu na velikost písmen (omezení nad `Lower("email")`)
- `native_language` přibude v kroku 4 (s modelem `Language`), `default_direction` v kroku 10 (typ „směr“ patří aplikaci `study`)
- `AUTH_USER_MODEL = "accounts.User"`, **první migrace až teď**
- Django admin pro uživatele
- přihlášení a odhlášení (vestavěné views, vlastní šablona)
- všechny stránky kromě přihlášení vyžadují přihlášeného uživatele (`LoginRequiredMiddleware`)

**Hotovo, když:** `createsuperuser` vytvoří účet s e-mailem a jde se přihlásit a odhlásit.

## Krok 3: Základní layout
- `base.html`: Pico.css, HTMX, horní navigace, zprávy (Django messages)
- mobile-first, vyzkoušet na šířce telefonu
- prázdný dashboard jako úvodní stránka

**Hotovo, když:** po přihlášení se ukáže dashboard, který vypadá dobře na mobilu i na počítači.

## Krok 4: Jazyky (`vocabulary`)
- model `Language` (ISO 639-1)
- datová migrace: `cs`, `en`, `es`
- migrace se zapnutím rozšíření `unaccent`
- doplnění `User.native_language`
- admin pro jazyky

**Hotovo, když:** jazyky jsou v adminu a v databázi je rozšíření `unaccent`.

## Krok 5: Slovníky (strom)
**Model a služby:**
- `Deck` včetně omezení (unikátní název v rámci rodiče + zvlášť pro kořeny)
- služby: vytvořit kořen nebo podslovník (převzetí jazykového páru), přejmenovat, smazat (s podstromem), přesunout (kontrola cyklu, jazykového páru a hloubky max. 5), posun ↑ ↓, seznam potomků, cesta pro drobečkovou navigaci
- testy služeb

**UI:**
- strom slovníků na dashboardu (složky, vždy rozbalený), jazykový pár u kořenů
- vytvoření, úprava, přesun, smazání (s potvrzením a počty), šipky ↑ ↓
- detail slovníku s drobečkovou navigací (zatím bez slovíček)

**Hotovo, když:** jde postavit strom `Angličtina (EN → CS) › Seriály › HIMYM › S01 › E01` a nejde vytvořit 6. úroveň ani cyklus.

Poznámky z implementace: unikátnost názvu jedním omezením s `nulls_distinct=False`; pořadí kořenových slovníků na zvláštní stránce; drobečková navigace má vlastní styl, protože ta z Pico se nezalamuje.

## Krok 6: Slovíčka – model a ruční přidávání
**Model a služby:**
- `Term`, `TermVariant`, `DeckTerm` včetně omezení (`Lower(main_foreign)`, `Lower(text)`)
- `ReviewState` (zakládá se tady, protože vzniká spolu se slovíčkem: 2 řádky, pro každý směr)
- učesání textu (NFC, mezery), rozdělení variant podle `;`
- služby: přidat slovíčko do slovníku, upravit varianty a poznámku, upravit kontext ve slovníku, odebrat ze slovníku (smazání slovíčka bez slovníku po potvrzení)
- testy služeb

**UI:**
- formulář v detailu slovníku: cizí výraz, překlad, „Více“ (věta, poznámka). Po uložení zůstane otevřený a kurzor skočí do prvního pole.
- seznam slovíček ve slovníku, řazení (datum přidání / abecedně / termín opakování)
- úprava a odebrání slovíčka

**Hotovo, když:** jde rychle přidat několik slovíček za sebou, včetně variant a věty.

Poznámky z implementace: `ReviewState` je v aplikaci `study` (vzniká se slovíčkem); pole zdroj (díl) bylo později zrušené, díl určuje slovník; výchozí řazení seznamu je od nejnovějšího; všechna pole formulářů mají šablonu `templates/forms/field.html` (nápověda a chyby pod polem, styl Pico); mazání slovníku maže i slovíčka, která nejsou v jiném slovníku.

## Krok 7: Kontrola duplicit
- služba, která pro rozepsané slovíčko vrátí:
  1. shody na cizí straně (bez ohledu na velikost písmen),
  2. shody jen na straně překladu,
  3. podobná slova bez diakritiky (`unaccent`)
- HTMX endpoint volaný během psaní (s malým zpožděním)
- akce: „Přidat i sem“, „Přidat jako variantu“, „Uložit samostatně“
- zablokování, pokud slovíčko už v daném slovníku je
- testy služby

**Hotovo, když:** `hello` v druhé epizodě nabídne „přidat i sem“, `hi → ahoj` nabídne „přidat jako variantu k hello“ a `cau` upozorní na `čau`.

Poznámky z implementace: slova se stejným textem a jiným překladem (homonyma) mají v panelu vlastní sekci „už máš s jiným překladem“; jiný význam se prostě uloží (homonyma rozlišuje překlad, pole „rozlišení“ bylo zrušené). Blokuje se jen stejné cizí slovo se stejným překladem.

## Krok 8: Hodnocení a výpočet intervalu (`study`)
- `study/ratings.py`: 4 tlačítka (klíč, emoji, název, výsledek, minimum, násobek, maximum, klávesa)
- funkce pro výpočet: stav opakování + hodnocení → nový interval, termín, série a počet chyb
- **testy podle příkladu `ahoj → hello` ze specu (6.3)**, včetně stropu 1 rok a vynulování růstu
- pomocná funkce, která pro kartičku spočítá náhled intervalu všech tlačítek

**Hotovo, když:** testy projdou a příklad ze specu sedí na den přesně.

Poznámky z implementace: intervaly od 1 dne se zaokrouhlují na celé dny; `apply_rating` stav jen změní, uloží ho až služba „uložit odpověď“ v kroku 9 spolu s historií; typ `Result` (správně / napůl / chyba) je v `study/models.py`.

## Krok 9: Výběr karet do testu
- `StudySession`, `ReviewLog` (včetně indexu `(user, term, reviewed_at)`)
- služba „další karta“:
  - slovíčka ze slovníků a jejich podslovníků, bez duplicit,
  - zvolené směry, rozsah `due` nebo `all`, limit karet,
  - pořadí: nejdřív po termínu (od nejstaršího), pak nová,
  - stejné slovíčko ne v obou směrech hned po sobě, homonyma ne hned po sobě
- služba „uložit odpověď“: aktualizuje `ReviewState`, zapíše `ReviewLog` s kopiemi hodnocení a časy
- testy služeb

**Hotovo, když:** test nad stromem slovníků vrací každé slovíčko jen jednou a respektuje termíny.

Poznámky z implementace: rozsah „všechna“ nevyžaduje frontu, kartička zodpovězená v tomto sezení (`last_reviewed_at` ≥ začátek sezení) se vrátí, jen když je znovu na řadě; rozestupy hlídá výběr z prvních 20 kandidátů; `record_answer` zamyká řádek stavu (`select_for_update`), aby dvě zařízení nezměnila stejnou kartičku najednou; `ReviewLog.reviewed_at` má `default=timezone.now`, aby šel zadat čas v testech.

## Krok 10: Obrazovka testu
- pole `User.default_direction` (výchozí směr testu)
- nastavení testu: výběr slovníků (strom se zaškrtávátky), směr, rozsah, max. počet; předvyplněné z `default_direction`
- kartička: přední strana (hlavní varianta velkým písmem, ostatní menším; věta podle pravidel; nápověda u homonym a kolizí), „Ukázat“, zadní strana (všechny varianty, vlastní další významy, věta, poznámka, významy ze slovníku)
- 4 tlačítka s emoji a skutečným příštím intervalem, barvy, `aria-label`, tooltip
- legenda při prvním testu a ikona „?“
- klávesnice: mezerník otočí kartičku, `1`–`4` ohodnotí
- měření `think_ms` a `decide_ms` v prohlížeči (pauza při `visibilitychange`, nad 5 min → `null`)
- přechod na další kartu přes HTMX bez znovunačtení stránky
- souhrn sezení: počet karet, rozložení hodnocení, chybná slovíčka, „Procvičit chybné znovu“

**Hotovo, když:** jde projít celý test na mobilu palcem a na počítači jen klávesnicí.

Poznámky z implementace: „Procvičit chybné znovu“ zakládá sezení jen nad vybranými slovíčky (`StudySession.terms`); dvojité odeslání stejné odpovědi se uloží jednou (formulář nese `reviews_count` kartičky); konec testu přes HTMX hlavičku `HX-Redirect`; obsah kartičky sestavuje `study/cards.py`; české intervaly a zvýraznění slova ve větě jsou v `study/formatting.py`; barvy tlačítek jsou průhledné, aby fungovaly ve světlém i tmavém režimu.

## Krok 11: Dashboard a detail slovíčka
- dashboard: kolik karet je dnes na řadě, počty ve stromu (včetně podslovníků, každé slovíčko jednou), „Spustit test“, u slovníku „Testovat tento slovník“
- detail slovíčka: varianty, slovníky a kontexty, stav opakování pro oba směry, počty hodnocení a historie odpovědí pro každý směr (spec 7.1)

**Hotovo, když:** z dashboardu je vidět, co je dnes na řadě, a u slovíčka jeho historie.

Poznámky z implementace: počty se počítají po slovíčkách (slovíčko je „k opakování“, když je na řadě aspoň jeden směr; „nové“, když ještě nebylo v testu); celý strom stačí 3 dotazy (`study.services.annotate_deck_counts`); klik na slovíčko v seznamu otevře jeho detail, úprava je odtamtud.

## Krok 12: Nastavení a dokončení
- stránka nastavení: rodný jazyk, výchozí směr
- kontrola na skutečném telefonu (přes místní síť: `runserver 0.0.0.0:8000`, `ALLOWED_HOSTS`)
- kontrola přístupnosti (klávesnice, `aria-label`, kontrast)
- `README.md`: kontrola, že lokální spuštění podle README funguje od nuly; doplnění sekce **Nasazení** o produkční server (aplikační server, statické soubory, reverzní proxy, HTTPS, zálohy)
- volitelně příkaz `seed_demo`, který naplní ukázková data (slovníky, slovíčka)

**Hotovo, když:** projekt jde podle README rozběhnout od nuly a MVP je použitelné na mobilu i na počítači.

Poznámky z implementace: statické soubory servíruje nginx (bez `whitenoise`); `gunicorn` přes unix socket a systemd; HTTPS nastavení (`SECURE_*`, HSTS) se zapne jen s `DJANGO_DEBUG=0` a řídí se proměnnými prostředí; `check --deploy` hlásí jen záměrná varování k HSTS pro subdomény a preload; v produkci je nastavený SMTP backend, MVP ale e-maily neposílá; příkaz `seed_demo` naplní účet ukázkovými daty; README bylo ověřeno instalací od nuly na čisté databázi.

---

## Závislosti mezi kroky
```
0 → 1 → 2 → 3 → 4 → 5 → 6 → 7
                         ↓
                         8 → 9 → 10 → 11 → 12
```
Krok 7 (kontrola duplicit) a krok 8 (výpočet intervalů) na sobě nezávisí, takže jde zvolit pořadí.

## Testování
- Servisní funkce mají testy (`pytest`), protože obsahují veškerou logiku: strom, duplicity, intervaly, výběr karet.
- Views a šablony se ověřují hlavně ručně v prohlížeči. Pár základních testů ověří, že stránky vyžadují přihlášení a nevrací chybu.
- Testy běží proti lokálnímu PostgreSQL (kvůli `unaccent` a `Lower()` omezením).
