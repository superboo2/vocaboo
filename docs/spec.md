# Vokie – specifikace

Webová aplikace na učení slovíček. Uživatel si skládá vlastní slovníky (např. podle seriálů), přidává do nich slovíčka a nechává se z nich zkoušet s ručně volenými intervaly opakování.

---

## 1. Cíle a principy

- **Jednoduchost:** MVP má obsahovat jen to nutné, další funkce přibývají po fázích.
- **Mobil i počítač:** responzivní UI navržené mobile-first, později PWA.
- **Data na serveru:** jeden účet, víc zařízení a všude stejný stav bez zvláštní synchronizace.
- **Jedno slovíčko = jeden stav opakování:** i když je ve více slovnících.
- **Logika mimo views:** business logika patří do `services.py`, aby šlo později přidat API (mobilní aplikace, Vue apod.).

---

## 2. Technologie

| Oblast | Volba |
|---|---|
| Jazyk | Python 3.13, správa přes `uv` |
| Backend | Django 6.1 |
| Frontend | Django šablony + HTMX (případně Alpine.js na drobnou interaktivitu) |
| Databáze | PostgreSQL pro produkci **i pro vývoj** (lokálně nainstalovaný, bez Dockeru), aby se vývoj choval stejně jako produkce. SQLite se nepoužívá. |
| Autentizace | Vestavěná Django auth, přihlášení **e-mailem** |
| CSS | **Pico.css** (bez build kroku) |
| Nasazení | MVP běží **jen lokálně**. Později vlastní malý server. |

### Struktura projektu (návrh)

```
vokie/
├── config/            # Django project (settings, urls, wsgi)
├── accounts/          # custom User model, registration, login, settings
├── vocabulary/        # languages, decks, terms
│   └── services.py    # add term, dedup, move deck...
├── study/             # test sessions, review states, review log
│   └── services.py    # pick next card, check answer, schedule
├── templates/
├── static/
└── docs/
```

---

## 3. Pojmy

| Pojem | Význam |
|---|---|
| **Slovník (Deck)** | Složka slovíček. Může mít podslovníky (strom). |
| **Slovíčko (Term)** | Dvojice „cizí výraz ↔ překlad“. Patří uživateli, ne slovníku. |
| **Zařazení (DeckTerm)** | Vazba slovíčka na slovník, včetně kontextu (věta, díl). |
| **Směr** | `F→N` (cizí → rodný, `hello → ahoj`) nebo `N→F` (rodný → cizí, `ahoj → hello`). |
| **Stav opakování (ReviewState)** | Kdy se má slovíčko v daném směru znovu ukázat. Každý směr má vlastní. |
| **Režim testu** | Volný, striktní (psaní), výběr z 6. |

---

## 4. Datový model

### 4.1 Language
Seznam jazyků, spravuje se přes Django admin.

| Pole | Typ | Poznámka |
|---|---|---|
| `code` | char(2), unique | kód **ISO 639-1**, ukládá se malými písmeny: `cs`, `en`, `de`… |
| `name` | char | „Čeština“, „Angličtina“… |

Počáteční jazyky (datová migrace): `cs` Čeština, `en` Angličtina, `es` Španělština. Typické páry: EN → CS, ES → CS.

Pozor: čeština je `cs`, ne `cz` (`CZ` je kód země, ne jazyka).

Do budoucna lze rozšířit na **BCP 47** (`en-GB`, `en-US`), pokud bude potřeba rozlišovat varianty jazyka, např. kvůli výslovnosti přes TTS.

### 4.2 User (vlastní model)

Vlastní User model (`accounts.User`, dědí z `AbstractUser`) se zakládá **hned na začátku projektu**, ještě před první migrací. Dodatečná výměna User modelu je v Djangu velmi pracná. Nastavení uživatele jsou přímo na něm, samostatná tabulka `UserSettings` není potřeba.

Přihlašuje se **e-mailem**: `email` je unikátní a `USERNAME_FIELD = "email"`.

V MVP **není veřejná registrace ani reset hesla**. Účty zakládá admin ručně (`createsuperuser` / Django admin). Na začátku je jediný uživatel: autor aplikace.

Pole navíc oproti `AbstractUser`:

| Pole | Typ | Poznámka |
|---|---|---|
| `native_language` | FK Language | výchozí rodný jazyk |
| `default_direction` | enum | `F2N` / `N2F` / `MIXED` |
| `show_suggestions` | bool, výchozí `True` | návrhy překladu při přidávání i úpravě slovíčka (5.2), vypíná se v Nastavení |
| `show_other_meanings` | bool, výchozí `True` | další významy ze slovníku na zadní straně kartičky (6.4) |
| `autoplay_pronunciation` | bool, výchozí `True` | přečíst cizí slovo samo (F→N hned, N→F po otočení) |
| `autoplay_content` | `word` / `sentence`, výchozí `word` | co se přečte: slovo, nebo celá věta (bez věty slovo) |
| `show_ipa` | bool, výchozí `False` | zápis výslovnosti (IPA) na kartičce a v detailu slovíčka |
| `strict_ignore_case` | bool | default `True` (fáze 2) |
| `strict_ignore_diacritics` | bool | default `False` (fáze 2) |
| `strict_allow_typo` | bool | default `False`, tolerance 1 překlepu (fáze 2) |

### 4.3 Deck

| Pole | Typ | Poznámka |
|---|---|---|
| `owner` | FK User | |
| `parent` | FK Deck, null | `null` = kořenový slovník |
| `name` | char | |
| `description` | text, blank | |
| `foreign_language` | FK Language | jazyk, který se učím (v UI „Chci se naučit“) |
| `native_language` | FK Language | jazyk překladu (v UI „Mluvím“) |
| `position` | int | pořadí mezi sourozenci, nižší číslo je výš |
| `created_at` | datetime | |

Výchozí řazení: `position`, potom `name`.

Pravidla:
- Strom má **max. 5 úrovní** (kořen = úroveň 1).
- **Každý uzel může mít slovíčka i podslovníky.** Složka a slovník se nerozlišují, např. „Seriály“ může být čistě složka, nebo obsahovat i vlastní slovíčka.
- Podslovník **musí mít stejný jazykový pár** jako rodič. Pár se ukládá na každý slovník (kvůli jednoduchým dotazům), při vytvoření se převezme z rodiče a nejde změnit. Shodu hlídá servisní vrstva.
- Slovník lze přesunout pod jiného rodiče jen se stejným jazykovým párem. Nesmí vzniknout cyklus (slovník pod vlastním potomkem) a nesmí se překročit limit hloubky (počítá se i hloubka přesouvaného podstromu).
- Název je unikátní v rámci jednoho rodiče, **bez ohledu na velikost písmen** (`HIMYM` = `himym`). Jedno omezení `UniqueConstraint(Lower(name), owner, parent, nulls_distinct=False)` pokryje i kořenové slovníky: PostgreSQL 15+ umí `NULLS NOT DISTINCT`, takže dva kořeny se stejným názvem neprojdou.
- Oba jazyky musí být různé (omezení v databázi).
- V UI se jazyky jmenují **„Chci se naučit“** a **„Mluvím“** (srozumitelnější než „cizí / rodný“ nebo „zdrojový / cílový“, které by se v testu oběma směry pletly).
- Nový slovník se zařadí na konec mezi sourozence.
- Potomky slovníku dohledává funkce v `services.py` (jednoduché procházení stromu). Žádná knihovna typu `django-mptt` nebo `treebeard`. Kdyby to bylo pomalé, přejde se na rekurzivní dotaz (CTE).

Příklad struktury:
```
Angličtina (EN → CS)
├── Seriály
│   ├── HIMYM
│   └── Big Bang Theory
└── Filmy
    └── Shrek
```

Zobrazení:
- U kořenového slovníku se za názvem ukazuje jazykový pár velkými písmeny, např. **Angličtina (EN → CS)**. Podslovníky pár dědí, takže se u nich ve stromu neopakuje. V detailu slovníku a v nastavení testu se zobrazuje vždy.
- **Strom složek** (📂 / 📁 slovník s podslovníky, 📄 slovník bez nich) s čarami vlevo. Po načtení stránky je vždy celý rozbalený; kliknutím jde složka sbalit do dalšího načtení, stav se nikam neukládá.
- Počty ve stromu se počítají včetně podslovníků a slovíček celkem hned za názvem, např. `Seriály (124)`, a když něco čeká, i počet k opakování v téže závorce: `Seriály (124 ↻ 8)`, `↻ 8` o něco menší (titulek „8 k opakování“); počet k opakování celkem je na tlačítku `Spustit test · 12 k opakování` (samostatný řádek s čísly na přehledu není).
- V detailu slovníku je **drobečková navigace**: `Angličtina › Seriály › HIMYM`.
- **Přetahování ve stromu na přehledu** (SortableJS jen pro samotné tažení): během tažení se řádky nehýbou, jen se ukazuje cíl. **Střed řádku** = vložit dovnitř (řádek se zvýrazní, funguje i u slovníku bez podslovníků), **horní / dolní okraj** = zařadit před / za (ukáže se čára). Řádky dřív při tažení uhýbaly a do složky se nedalo trefit. Myší hned, na dotykovém displeji po podržení zhruba 0,3 s, aby šlo normálně scrollovat. Uloží se hned po puštění; server zkontroluje pravidla a při chybě se strom vrátí a ukáže se hláška.
- Záloha pro ovládání klávesnicí: šipky ↑ ↓ u podslovníků v detailu slovníku a akce „Přesunout“.
- Akce se slovníkem (upravit, přesunout, smazat, přidat podslovník) jsou v detailu slovníku.

### 4.4 Term

| Pole | Typ | Poznámka |
|---|---|---|
| `owner` | FK User | |
| `foreign_language` | FK Language | |
| `native_language` | FK Language | |
| `main_foreign` | char | kopie textu hlavní cizí varianty (viz 4.5), slouží jen pro unikátní omezení |
| `main_native` | char | kopie textu hlavního překladu (viz 4.5), spolu s `main_foreign` slouží pro unikátní omezení |
| `note` | text, blank | |
| `origin` | enum | `manual` / `translated` / `voice` / `import` |
| `created_at` | datetime | |
| `example_sentence` | text, blank | příkladová věta k **významu** (**budoucí fáze**, plní se z předgenerovaného slovníku, viz 5.2) |

Samotné texty slovíčka nejsou na `Term`, ale v `TermVariant` (4.5).

Unikátnost: `(owner, foreign_language, native_language, Lower(main_foreign), Lower(main_native))`, tedy unikátní omezení nad výrazy `Lower()`, které Django podporuje přímo. Pole `main_foreign` a `main_native` jsou záměrná drobná duplicita dat: díky němu databáze spolehlivě zablokuje duplicitní slovíčko, i kdyby v kódu byla chyba nebo se ukládalo souběžně ze dvou zařízení. Nastavuje je servisní vrstva při každé změně hlavních variant.

**Homonyma** (`palm` = dlaň / palma, `present` = dárek / přítomnost / prezentovat) jsou **samostatná slovíčka** a rozlišuje je **překlad** (žádné zvláštní pole na rozlišení):
```
palm  ↔ dlaň
palm  ↔ palma
```
Varianty `palm ↔ dlaň; palma` by byly špatně, protože `dlaň` ≠ `palma`. Varianty jsou jen pro synonyma.

### 4.5 TermVariant
Texty slovíčka. Každá strana (cizí i rodná) může mít **víc variant**.

| Pole | Typ | Poznámka |
|---|---|---|
| `term` | FK Term | |
| `side` | enum | `F` (cizí) / `N` (rodná) |
| `text` | char | text tak, jak ho uživatel napsal (po učesání, viz níže), např. `Čau` |
| `position` | int | pořadí na dané straně, `0` = hlavní varianta |

Unikátnost: `(term, side, Lower(text))`, takže jedno slovíčko nemůže mít stejnou variantu dvakrát.

Každé slovíčko musí mít aspoň jednu variantu na každé straně (hlídá servisní vrstva).

Příklad: slovíčko `hello; hi` ↔ `Ahoj; čau`

| term | side | text | position |
|---|---|---|---|
| 100 | F | hello | 0 |
| 100 | F | hi | 1 |
| 100 | N | Ahoj | 0 |
| 100 | N | čau | 1 |

**Varianty znamenají „každá vlevo odpovídá každé vpravo“.** Když to neplatí (`hello; hi` ↔ `ahoj; dobrý den`, kde `hi` ≠ `dobrý den`), je lepší vytvořit dvě slovíčka. Aplikace to nerozhodne za uživatele, ale upozorní na kolize (viz 5.1).

#### Učesání textu a porovnávání
Normalizované kopie textu se **neukládají**. Porovnává se až při dotazu, protože PostgreSQL (i při vývoji) umí `lower()` správně i pro češtinu a má rozšíření `unaccent`.

Ukládá se **jen jedna podoba textu** (`text`). Původní neučesaný vstup se neuchovává, protože rozdíl je neviditelný. Normalizovaná kopie (malá písmena, bez diakritiky) se taky neukládá, protože porovnání zvládne PostgreSQL při dotazu.

**Při uložení** servisní vrstva jen „učeše“ vstup a výsledek uloží rovnou do `text`:
1. Unicode NFC: `č` je vždy jeden znak, ne `c` + samostatný háček. To databáze sama neumí a různé klávesnice posílají různé tvary.
2. oříznout krajní mezery, vícenásobné mezery sloučit do jedné

**Při porovnávání:**

| Účel | Jak | Diakritika |
|---|---|---|
| Kontrola duplicit | v DB, bez ohledu na velikost písmen (`iexact`) | **zachovat**: `byt` ≠ `být`, `pas` ≠ `pás`, `schon` ≠ `schön` |
| Upozornění „podobné“, vyhledávání | v DB přes `unaccent` (`text__unaccent__iexact`, `__unaccent__icontains`) | ignorovat: `cau` najde `čau` |
| Striktní režim (fáze 2) | v Pythonu, jedna funkce porovná odpověď s variantami jednoho slovíčka | podle nastavení uživatele |

Poznámky:
- Rozšíření `unaccent` se zapne migrací (`UnaccentExtension` z `django.contrib.postgres`).
- Dotazy se vždy filtrují nejdřív podle uživatele a jazykového páru, takže běžný index není potřeba. Kdyby vyhledávání bylo pomalé, přidá se index nad výrazem.
- Python funkce pro striktní režim a `unaccent` v DB můžou mít v okrajových případech mírně odlišná pravidla. To je přijatelné.
- Do budoucna lze přidat rozšíření `pg_trgm`, aby upozornění „podobné“ zachytilo i překlepy (`helo` → `hello`).

### 4.6 DeckTerm

| Pole | Typ | Poznámka |
|---|---|---|
| `deck` | FK Deck | |
| `term` | FK Term | |
| `context_sentence` | text, blank | věta, ve které slovo zaznělo: „Hello, Penny.“ |
| `context_sentence_native` | text, blank | překlad věty, volitelný: „Ahoj, Penny.“ (k pochopení; na kartě v obou směrech, viz 6.4) |
| `added_at` | datetime | |

Unikátnost: `(deck, term)`.

**Věta z epizody × příkladová věta:**
- `DeckTerm.context_sentence` patří k **výskytu** (kde jsem slovo viděl). Jedno slovíčko jich může mít víc, v každém slovníku jednu.
- `Term.example_sentence` (budoucí fáze) patří k **významu** a je obecná.
- V testu má přednost věta z epizody. Když chybí, použije se příkladová věta.

### 4.7 ReviewState

| Pole | Typ | Poznámka |
|---|---|---|
| `term` | FK Term | |
| `direction` | enum | `F2N` / `N2F` |
| `due_at` | datetime, null | `null` = ještě nikdy neopakováno (nové) |
| `last_reviewed_at` | datetime, null | |
| `last_rating` | char, blank | klíč naposledy zvoleného hodnocení (`ok` / `think` / `partial` / `dontknow`) |
| `last_interval` | duration, null | naposledy použitý interval |
| `correct_streak` | int | správně za sebou |
| `lapses` | int | kolikrát celkem výsledek `wrong` (`partial` se nepočítá) |
| `reviews_count` | int | |

Unikátnost: `(term, direction)`. Oba stavy se vytvoří spolu se slovíčkem.

### 4.8 ReviewLog
Kompletní historie každé odpovědi, slouží pro statistiky a chytré intervaly.

| Pole | Typ | Poznámka |
|---|---|---|
| `user` | FK User | |
| `term` | FK Term | |
| `session` | FK StudySession, null | sezení, ve kterém odpověď padla |
| `direction` | enum | |
| `rating` | char | klíč zvoleného hodnocení (`ok` / `think` / `partial` / `dontknow`) |
| `rating_label` | char | **kopie** názvu tlačítka v okamžiku odpovědi |
| `result` | enum | **kopie** výsledku: MVP `correct` / `partial` / `wrong`; fáze 2 přidá `typo` |
| `chosen_interval` | duration | **kopie** použitého intervalu |
| `think_ms` | int, null | doba od zobrazení kartičky do otočení (ms) |
| `decide_ms` | int, null | doba od otočení do zvolení hodnocení (ms) |
| `reviewed_at` | datetime | |
| `mode` | enum | `free` / `strict` / `choice` (**fáze 2**) |
| `answer_given` | char, blank | co uživatel napsal nebo vybral (**fáze 2**) |

Pole označená fází 2 se v MVP nevytvářejí, přidají se migrací.

Hodnocení, výsledek a interval se ukládají jako **kopie**, ne jako odkaz na nastavení. Když se později tlačítka změní (jiný název, jiný čas, vlastní tlačítka), historie zůstane správná.

**Měření času (`think_ms`, `decide_ms`):**
- Měří se v prohlížeči (`performance.now()`) a posílá se spolu s hodnocením. Měření na serveru by zkreslovala rychlost sítě.
- Když uživatel během kartičky přepne aplikaci nebo zhasne telefon (událost `visibilitychange`), čas se pozastaví.
- Hodnoty nad 5 minut se uloží jako `null`, protože uživatel nejspíš odešel.
- Využití: statistiky (průměrná doba odpovědi), odhalení slovíček, která „vím“, ale dlouho přemýšlím, a později podklad pro chytré intervaly.

### 4.9 StudySession

| Pole | Typ | Poznámka |
|---|---|---|
| `user` | FK User | |
| `decks` | M2M Deck | vybrané slovníky (podslovníky se přidají automaticky) |
| `direction` | enum | `F2N` / `N2F` / `MIXED` |
| `mode` | enum | `free` / `strict` / `choice` (**fáze 2**, v MVP se nevytváří) |
| `scope` | enum | `due` (jen k opakování + nová) / `all` (vše bez ohledu na termín) |
| `max_cards` | int, null | limit karet v sezení |
| `started_at`, `finished_at` | datetime | |
| `answered`, `correct` | int | průběžné počítadlo |

Sezení si **nedrží frontu karet**, další karta se vždy vypočítá z databáze (viz 6.2). Díky tomu je stav stejný na všech zařízeních a karta odložená na 10 minut se sama vrátí, jakmile je zase na řadě.

### 4.10 Mazání

- **Odebrání slovíčka ze slovníku** smaže `DeckTerm`. Pokud slovíčko nezůstane v žádném jiném slovníku, smaže se celé, včetně historie (po potvrzení uživatelem).
- **Smazání slovníku** smaže i podslovníky (po potvrzení s počtem dotčených slovníků a slovíček). Slovíčka, která tím zůstanou bez slovníku, se smažou.

---

## 5. Přidávání slovíček

### 5.1 Ručně (fáze 1)

Formulář ve slovníku:
- **Cizí výraz**, varianty se oddělují středníkem (`hello; hi`)
- **Překlad**, varianty se oddělují středníkem (`ahoj; čau`)
- **Použití ve větě**, volitelné, uživatel ho v MVP píše sám (`She read my palm.`). Uloží se do `DeckTerm.context_sentence`. Slovo ve větě aplikace najde sama (celé slovo, kterákoliv cizí varianta, bez ohledu na velikost písmen). **Jiný tvar** slova se označí složenými závorkami: `He {ran} away.` u slovíčka `run`; prázdné `{}` znamená hlavní variantu. Závorky se nikde nezobrazují, slovo je zvýrazněné (seznam, detail, kartička) nebo nahrazené mezerou (přední strana N→F).
- Poznámka, volitelná

Formulář musí být rychlý: povinné jsou jen první dvě pole, ostatní (věta, překlad věty, poznámka) jsou schovaná pod řádkem pod tlačítkem. Ten místo „Více“ ukazuje, co v polích je: *„+ věta, poznámka“*, nebo větu s překladem (nejvýš 2 řádky) a *„upravit“*; po rozbalení *„hotovo“*. Výběr návrhu překladu doplní i větu a její překlad z daného významu ve slovníku, jen když jsou pole věty prázdná (vlastní věta se nikdy nepřepíše); náhled je pod tlačítkem, takže tlačítko neposkočí. Po uložení zůstane formulář otevřený a kurzor skočí zpět do prvního pole, aby šlo hned psát další slovíčko. Enter formulář odešle. Pole „zdroj“ (díl) není: díl určuje slovník (*Series 1 › Episode 1*), cokoliv navíc patří do poznámky.

Pole jsou označená kódem jazyka slovníku (`EN`, `CS`), aby se strany nepletly. Později se dá udělat zadávání variant jako „štítků“ (napíšeš, Enter, další).

**Kontrola duplicit (HTMX, během psaní, na obou stranách):**
Hledá se mezi slovíčky téhož uživatele a jazykového páru, a to podle **všech variant** (nejen hlavní).

1. **Shoda na cizí straně** (bez ohledu na velikost písmen, např. `hello` už existuje):
   *„Už máš v: HIMYM, Big Bang Theory (hello; hi → ahoj; čau)“*
   - **Přidat i sem:** vytvoří jen `DeckTerm` s kontextem z formuláře. Slovíčko, varianty i stav opakování zůstávají sdílené. Nové varianty z formuláře se nabídnou k připojení.
   - Pokud už slovíčko v aktuálním slovníku je, uložení se zablokuje s hláškou.
2. **Shoda jen na straně překladu** (např. píšu `hi → ahoj` a `ahoj` už je překladem `hello`):
   *„ahoj“ už máš jako překlad slova **hello** (HIMYM)*
   - **Přidat „hi“ jako variantu k hello** (doporučeno)
   - **Uložit jako samostatné slovíčko:** hodí se při jiném odstínu významu (např. `hi` = neformální), případně s poznámkou.
3. **Stejný text, jiný překlad** (např. píšu `palm → palma` a existuje `palm → dlaň`):
   *„palm“ už máš s jiným překladem: „palm → dlaň“ (HIMYM)*
   - **Stejný význam: přidat jako variantu / přidat sem**
   - **Jiný význam:** stačí slovíčko uložit, vznikne další význam. Uložení se neblokuje.
   - Blokuje se jen přesná shoda (stejné hlavní cizí slovo **i** stejný hlavní překlad).
4. **Podobné bez diakritiky** (`unaccent`, např. píšu `cau` a existuje `čau`):
   *„Podobné: čau (HIMYM)“*. Je to jen upozornění, uložení se neblokuje. Slova lišící se diakritikou můžou být opravdu různá (`byt` × `být`).

Velikost písmen se při kontrole ignoruje (`Ahoj` = `ahoj`), zobrazí se ale tak, jak je uživatel napsal.

**Přesun slovíček do jiného slovníku** (třeba omylem do `S01` místo `E01`):
- V seznamu slovíček „Vybrat“ ukáže zaškrtávátka a dole lištu: *Vše*, *Přesunout…*, *Zrušit*. Jedno slovíčko jde přesunout i z jeho detailu.
- Na další stránce se vybere cílový slovník (celá cesta, jen stejný jazykový pár) a akce **Přesunout**, nebo **Přidat i tam** (slovíčko zůstane v obou).
- Mění se jen `DeckTerm.deck`, věta, datum přidání i stav opakování zůstanou. Když slovíčko v cíli už je, nezdvojí se: v cíli se jen doplní chybějící věta a ze zdroje se odebere.

### 5.2 Vlastní slovník aplikace: návrhy překladu, další významy, IPA, příklady (hotovo)

**Hotovo:** aplikace má **vlastní anglicko-český slovník** (asi 10 000 hesel; obsah vytvořila AI, nic se nepřebírá z Wiktionary ani jiných slovníků, takže se zdroj neuvádí). Originál je soubor JSONL `dictionary/data/lexicon_en_cs.jsonl` + `lexicon_tags.json` (není v gitu, na server se kopíruje ručně), do databáze ho nahraje příkaz `import_lexicon` (další import data nahradí). Tabulky: `LexiconEntry` (slovo + slovní druh, jazykový pár, pásmo častosti 1–15 v mluvené řeči, úroveň CEFR, IPA), `LexiconForm` (texty, podle kterých se heslo hledá: heslo a jiné zápisy, malými písmeny, s indexem), `LexiconSense` (pořadí, překlad s variantami `;`, poznámka, věta a její překlad se `{…}`, tagy) a `LexiconTag` (pevný seznam, dvě úrovně). Použití: **návrhy** při psaní cizího slova, při přidání i úpravě (významy seřazené podle pásma a pořadí, se zkratkou slovního druhu a poznámkou v titulku; věta doplněná z návrhu se po změně cizího slova zase smaže, pokud ji uživatel neupravil), **další významy** na kartičce a v detailu slovíčka, **IPA** (když si ji uživatel zapne) a **příklad věty** na konci testu (věta významu, jehož překlad sedí na překlad slovíčka). Zvuk dělá jen hlas prohlížeče. Zatím jen angličtina → čeština. Wiktionary (výtah kaikki.org, tabulka `DictionaryEntry`, příkaz `import_wiktionary`, nahrávky z Wikimedia Commons) bylo odstraněno.

**Další možný krok:** tematické slovníky podle tagů (např. *Zvířata, 30 nejčastějších*), *další nejčastější slova, která ještě nemáš* podle pásem, další jazyky přes stejné rozhraní (`dictionary/providers.py`).

Původní návrh výběru významu:
Cíl: zadání slovíčka na pár písmen a jedno klepnutí.

```
EN: palm                                   [Enter]
───────────────────────────────────────────────
Vyber význam:
 1  dlaň     ruka    „She read my palm.“
 2  palma    strom   „That's a really tall palm.“
 ✓  (už máš: dlaň · HIMYM S01E01)
───────────────────────────────────────────────
 + zadat ručně
```

- Klepnutím na význam se uloží překlad i `example_sentence`.
- Jde vybrat víc významů najednou. Ovládání jde i z klávesnice (Enter, číslo významu).
- Varianta: uživatel vloží celou větu ze seriálu a klepne na slovo. Správný význam se předvybere a věta se uloží jako kontext.
- Ruční zadání zůstává vždy jako záloha.

**Zdroj dat:**
1. **Předgenerovaný slovník:** pro nejčastějších 10–20 tisíc slov daného jazyka (frekvenční seznamy z titulků: SUBTLEX, `wordfreq`) se významy, překlady a věty vygenerují předem přes LLM (Batch API). Odpověď je pak okamžitá z DB.
2. **Živý dotaz na LLM** jen u slov, která ve slovníku nejsou. Spouští se už během psaní, výsledek se uloží do sdílené cache pro všechny uživatele.
3. **Našeptávání** z předgenerovaného slovníku během psaní (`pa` → palm, paper…).

Volání LLM je schované za jednotným rozhraním, aby šel poskytovatel vyměnit.

**Orientační náklady** (odhad, ověřit pilotem na ~100 slovech):
- předgenerování 10 000 slov přes Claude Sonnet 5 v Batch API: řádově ~$20 za jazykový pár, jednorázově,
- živé dotazy přes Claude Haiku 4.5: řádově desetiny centu za slovo,
- na API klíči nastavit měsíční limit útraty.

Návrh **jen nabízí**, uložení vždy potvrzuje uživatel výběrem.

### 5.3 Hromadně (fáze 2)
Vložení řádků ve tvaru `hello; hi - ahoj` a náhled před uložením (duplicity vyznačené).

### 5.4 Z titulků (fáze 3)
Nahrání `.srt` souboru, vypíšou se slova, která uživatel ještě nemá, i s větou, kde zazněla. Uživatel odklikne vybraná slova, překlad se navrhne a kontext se uloží automaticky.

### 5.5 Z audia (fáze 4)
Mikrofon (seriál nahlas) nebo nahraný audio soubor, přepis (Whisper), věty, dál stejně jako 5.4.

---

## 6. Testování

### 6.1 Nastavení testu
1. Výběr slovníků (víc najednou, podslovníky se zahrnou automaticky)
2. Směr: `F→N`, `N→F`, zamíchat
3. Režim: volný (MVP); striktní a výběr z 6 přibudou ve fázi 2
4. Rozsah: jen k opakování (+ nová) / všechna
5. Volitelně max. počet karet

### 6.2 Výběr další karty
1. Posbírat slovíčka ze všech `DeckTerm` vybraných slovníků a jejich podslovníků, **distinct podle Term**. Tím se duplicity mezi slovníky odfiltrují automaticky.
2. Vzít jejich `ReviewState` pro zvolené směry.
3. Pořadí:
   - Rozsah `due`: nejdřív karty s `due_at <= now`, pak nové (`due_at = null`). **Uvnitř obou skupin náhodně**: dřív šla nová slovíčka v pořadí přidání a oba směry stejného slova byly jen jednu kartu od sebe, takže druhý směr šel poznat z krátkodobé paměti. Náhoda je jen uvnitř skupin, aby při omezení „Nejvýš karet“ šla dřív slovíčka po termínu.
   - Rozsah `all`: každá karta jednou za sezení, nejdřív ty, které už byly v testu, pak nové; uvnitř skupin náhodně.
   - Náhodné pořadí je pro celý test stejné (i po obnovení stránky nebo na jiném zařízení): sezení má náhodné číslo `shuffle_seed` a karty se řadí podle `md5(seed-id karty)` přímo v databázi. Každý test má jiné číslo, tedy jiné pořadí. Kartička „vůbec nevím“ se po 10 minutách zařadí zpět na náhodné místo. Karta zodpovězená v tomto sezení se vrátí, jen když je mezitím znovu na řadě (např. „vůbec nevím“ za 10 minut).
4. Karty odložené na později (`due_at > now`) se v rozsahu `due` nevrátí, dokud nebude jejich čas.
5. Když nic nezbývá, test skončí a zobrazí se souhrn.

V režimu „zamíchat“ se karta vybírá napříč oběma směry. Stejné slovíčko se nemá ukázat v obou směrech hned po sobě (jen pojistka, náhodné pořadí je většinou dá daleko od sebe; přísný rozestup není potřeba, občas blízko nevadí).

**Rozestup homonym:** dva významy stejného slova (`palm` ruka / strom) se neukážou hned po sobě, aby si nenapovídaly.

**Kontext při testu z více slovníků:** když je slovíčko ve více vybraných slovnících (např. `hello` ve 20 epizodách), ukáže se jedna věta z vybraných slovníků (pokaždé jiná). Ze kterého slovníku věta je, ani v kolika slovnících slovíčko je, se na kartě neukazuje: pro učení to není důležité, je to v detailu slovíčka.

### 6.3 Hodnocení a intervaly

Po otočení kartičky se uživatel ohodnotí jedním tlačítkem. Tlačítko určuje **výsledek** (pro statistiky, `correct_streak`, `lapses`) a **interval** do dalšího opakování. Intervaly **rostou** s každým úspěšným opakováním, stejně jako v Anki nebo SuperMemo. Pevné intervaly nepoužívá žádná známá aplikace, protože buď otravují u známých slov, nebo nechají zapomenout nová.

#### Výchozí tlačítka (MVP)
Pořadí zleva doprava **od nejlepšího po nejhorší**:

| Klávesa | Emoji | Klíč | Název (legenda, čtečky) | Výsledek | Poprvé / minimum | Další opakování | Max |
|---|---|---|---|---|---|---|---|
| `1` | 😎 | `ok` | Vím | `correct` | 7 dní | předchozí × 4 | 1 rok |
| `2` | 🤔 | `think` | Vím po zamyšlení | `correct` | 3 dny | předchozí × 2,5 | 1 rok |
| `3` | 😕 | `partial` | Vzpomínám si napůl | `partial` | 1 den | pevně 1 den | |
| `4` | 😵 | `dontknow` | Vůbec nevím | `wrong` | 10 min | pevně 10 min | |

Inspirace: Anki (Again 1–10 min, Good ×2,5, Easy víc) a SuperMemo SM-2. Je to zjednodušené, bez skrytého „faktoru obtížnosti“, takže chování je předvídatelné.

#### Výpočet
```
if button has multiplier and last_interval is not null:
    interval = last_interval × multiplier
else:
    interval = button.min_interval   (or the fixed interval)
interval = clamp(interval, button.min_interval, button.max_interval)
due_at = now + interval
```
- Interval se počítá od **okamžiku odpovědi**, ne od původního termínu.
- Intervaly od 1 dne výš se **zaokrouhlují na celé dny** (půlka nahoru), např. 3 × 2,5 = 7,5 → 8 dní. Slovíčko se pak vrací zhruba ve stejnou denní dobu a čísla pod emoji jsou čitelná. Zaokrouhluje se až po použití minima a stropu.
- Po `partial` a `wrong` se do `last_interval` uloží jejich krátký pevný interval. Další úspěšná odpověď proto začne znovu od minima: růst se vynuluje.
- Výsledky a počítadla:
  - `correct`: `correct_streak += 1`
  - `partial`: `correct_streak = 0`, `lapses` se **nemění** (vzpomněl jsem si, jen ne přesně)
  - `wrong`: `correct_streak = 0`, `lapses += 1`
- Protože stav patří slovíčku, nový termín platí automaticky **ve všech slovnících**, kde slovíčko je.

#### Příklad: `ahoj → hello`
Opakuje se vždy v den, kdy je slovíčko na řadě:

| # | Datum | Tlačítko | Výpočet | Interval | Další opakování | Série | Chyby |
|---|---|---|---|---|---|---|---|
| 1 | 8. 10. 2026 | 😎 Vím | nové → minimum | 7 dní | 15. 10. 2026 | 1 | 0 |
| 2 | 15. 10. 2026 | 😎 Vím | 7 × 4 | 28 dní | 12. 11. 2026 | 2 | 0 |
| 3 | 12. 11. 2026 | 😎 Vím | 28 × 4 | 112 dní | 4. 3. 2027 | 3 | 0 |
| 4 | 4. 3. 2027 | 🤔 Po zamyšlení | 112 × 2,5 | 280 dní | 9. 12. 2027 | 4 | 0 |
| 5 | 9. 12. 2027 | 😕 Napůl | pevně | 1 den | 10. 12. 2027 | 0 | 0 |
| 6 | 10. 12. 2027 | 😎 Vím | 1 × 4 = 4 → minimum | 7 dní | 17. 12. 2027 | 1 | 0 |

Opakované „Vím“: 7 dní → 28 → 112 → 1 rok. Opakované „Po zamyšlení“: 3 dny → 8 → 20 → 50 → 125 → 313 dní → 1 rok.

#### Zobrazení tlačítek
```
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│   😎   │ │   🤔   │ │   😕   │ │   😵   │
│ 7 dní  │ │ 3 dny  │ │ 1 den  │ │ 10 min │
└────────┘ └────────┘ └────────┘ └────────┘
```
- Na tlačítku je **emoji** (univerzální pro všechny jazyky) a pod ním **skutečný příští interval pro tuto kartičku**, ne obecné pravidlo. U kartičky s intervalem 112 dní by bylo `1 rok · 280 dní · 1 den · 10 min`.
- Čas se formátuje podle jazyka UI (`10 min`, `3 dny`, `1 rok`).
- Jen starší emoji (Unicode 6–8), aby se správně zobrazila i na starších zařízeních.
- **Barva pozadí** jako doplněk: zelená, světle zelená, oranžová, červená (jemné odstíny). Barva nikdy není jediný rozlišovací znak, takže to nevadí barvoslepým.
- Na mobilu jedna řada 4 tlačítek (případně mřížka 2×2 na úzkých displejích).
- **Legenda:** při prvním testu se nad tlačítky ukáže *„😎 vím · 🤔 vím po zamyšlení · 😕 vzpomínám si napůl · 😵 vůbec nevím“*. Dá se zavřít a pak už se neukazuje. Ikona **„?“** u tlačítek ji kdykoliv ukáže znovu.
- Na počítači i **tooltip** s názvem při najetí myší. Na mobilu tooltip nefunguje, tam slouží legenda.
- **`aria-label`** pro čtečky obrazovky, např. „Vím, opakovat za 7 dní“.

#### Ovládání z klávesnice (počítač)
- **mezerník** otočí kartičku,
- **`1`–`4`** vyberou hodnocení. Malá nápověda s číslem je na tlačítku, jen na počítači.
- **`E`** (nebo ✎ vedle **?** pod kartičkou) otevře úpravu slovíčka (`term_edit` s `?test=<id>`); tlačítka *Uložit a zpět do testu* / *Neukládat a zpět do testu* vrací do testu na stejnou kartičku (ještě nebyla ohodnocená). Během testu se ve formuláři neukazuje *Odebrat z tohoto slovníku*.

#### Návrh pro snadné budoucí úpravy
- V MVP jsou tlačítka **konstanta v kódu** (`study/ratings.py`): klíč, emoji, název, výsledek, minimum, násobek (nebo žádný = pevný interval), maximum a klávesa. V MVP se pro ně nedělá tabulka ani obrazovka nastavení.
- Celý výpočet je v **jedné funkci** servisní vrstvy (stav opakování + hodnocení → nový stav). Jakákoliv změna logiky mění jen tuhle funkci.
- Šablona vykresluje tlačítka ze seznamu, ne napevno.
- `ReviewLog` ukládá kopie (viz 4.8), takže změna tlačítek nerozbije historii.

#### Budoucí rozšíření
- **Vlastní tlačítka uživatele:** tabulka `RatingButton` (user, key, emoji, label, result, min, multiplier, max, position), naplněná výchozí sadou. Funkce pro výpočet bude číst z ní. Počet tlačítek 2–6 kvůli mobilu.
- **Pořadí tlačítek** (nejlepší vlevo nebo vpravo) v nastavení.
- **Mírnější „napůl“:** např. další „Vím“ naváže na čtvrtinu intervalu před chybou místo minima. Rozhodne se podle zkušenosti z MVP.
- **Chytrý návrh** (SM-2 / FSRS, využije i `think_ms`): jedno tlačítko se zvýrazní jako doporučené.

### 6.4 Volný režim (MVP)
Základní kartičkový test: uvidím slovíčko, zamyslím se, otočím kartičku a podle toho, jak dobře jsem ho věděl, zvolím, kdy se má znovu objevit.

1. Zobrazí se výraz (podle směru) a kontextová věta, pokud existuje. Při směru `N→F` by celá věta prozradila odpověď, proto se na přední straně ukáže **s mezerou místo slova** (cloze): *dlaň → „She can read from her ___.“*. Celá věta se zvýrazněným slovem je na zadní straně. Když slovo ve větě nejde najít (jiný tvar bez označení), věta je jen na zadní straně.
2. Tlačítko „Ukázat“ zobrazí odpověď (všechny varianty), vlastní další významy, větu, poznámku a dole významy ze slovníku (viz 6.4 Homonyma).
3. Uživatel se ohodnotí jedním z tlačítek (6.3).

**Výslovnost** (hotovo): u cizího slova (ve směru F→N hned, protože slovo je otázka a zvuk nic neprozradí; ve směru N→F po otočení karty) a v detailu slovíčka: šedé, lehce průhledné 🔊 (ve směru F→N na řádku otázky, ve směru N→F na řádku odpovědi, vždy u **pravého okraje kartičky** a svisle na středu řádku, aby ho palec našel vždy na stejném místě a slovo neposkakovalo; slovo zůstává uprostřed, po obou stranách je místo na ikonu, slova delší než 10 znaků mají menší písmo; v detailu slovíčka vedle nadpisu; při najetí, klepnutí a přehrávání ztmavne) a pod slovem menším šedým písmem IPA v hranatých závorkách (`[pɑːm]`), ale **jen když si ho uživatel zapne** (`User.show_ipa`, výchozí vypnuto: většina lidí IPA neumí číst). Závorky ze zdroje (`[…]` i `/…/`) se při čtení odstraní a šablona přidá jednotné `[…]`. IPA je ze slovníku aplikace (`LexiconEntry.ipa`). Mp3 se přehrává přímo z Wikimedia Commons až po kliknutí nebo klávese **P**, nic se neukládá. Hledá se hlavní cizí varianta, bez ohledu na velikost písmen; při víc slovních druzích se bere IPA nejčastějšího hesla. Bez dat se řádek neukáže. 🔊 je vždycky (volba „Ukazovat výslovnost“ byla zrušena). Nastavení › Test › Audio: *Přehrát automaticky* (zapnuto; F→N hned, jak se kartička ukáže, N→F po kliknutí na Ukázat) s volbou *slovo* / *celé použití ve větě* (bez věty slovo). Prohlížeče nedovolí mluvit před prvním kliknutím na stránce, takže úplně první kartička testu se sama nepřečte (načtení testu bez nové stránky by to vyřešilo, ale zatím to není potřeba). Zdroje jsou za rozhraním `get_pronunciation(word, foreign_code)` v `dictionary/providers.py` s pořadím ve `VOKIE_PRONUNCIATION_PROVIDERS`; **Zvuk dělá hlas prohlížeče** (hotovo, Web Speech API, zdarma a bez serveru; nahrávky z Wikimedia Commons byly odstraněny spolu s Wiktionary): slovo (hlavní cizí varianta) i větu na kartičce (🔊 na konci věty, klávesa **V**; ve směru N→F až po otočení) a věty v detailu slovíčka. Jazyk podle slovníku, u angličtiny přednost americkému hlasu (v seriálech nejčastější) a hlasům typu Google / Microsoft Natural; čte o něco pomaleji (0,9). Tlačítko přijde schované a JS ho ukáže, když prohlížeč umí mluvit vůbec. Hlas se vybírá až při přehrání; když prohlížeč pro jazyk hlas nenahlásí (některé je hlásí pozdě nebo s jiným kódem), předá se jen jazyk a prohlížeč vybere sám. Kvalita podle zařízení: Android, Windows, Mac a Chrome na Linuxu dobře, Firefox na Linuxu roboticky nebo bez hlasu. Hlas na serveru (Piper, cloud) jde přidat později jako další zdroj, kdyby hlasy prohlížeče nestačily.

**Zobrazení variant** (slovíčko `hello; hi` ↔ `ahoj; čau`):

| Směr | Přední strana | Zadní strana |
|---|---|---|
| EN → CS | **hello** *(také: hi)* | ahoj · čau |
| CS → EN | **ahoj** *(také: čau)* | hello · hi |

- Přední strana: hlavní varianta velkým písmem, ostatní menším. Synonyma zpřesňují význam otázky.
- Zadní strana: všechny varianty druhé strany.

Varianty jsou rovnocenné: uživatel se hodnotí sám, takže když si řekne „hi“ a na zadní straně je `hello · hi`, ví to.

**Homonyma ve směru F→N** (`palm` má dva významy, otázka by byla nejednoznačná):
1. **Věta jako nápověda:** na přední straně se ukáže kontextová věta se zvýrazněným slovem: *„She read my **palm**.“* Ve směru F→N věta nic neprozradí, naopak určí význam.
2. **Bez věty:** na přední straně se ukáže počet významů: **palm** *(2 významy)*. Počítají se vlastní slovíčka se stejným cizím slovem.
3. **Zadní strana učí i ostatní významy**, seřazeno od nejdůležitějšího:
   ```
   dlaň                                   ← odpověď
   Učíš se i: palm → palma                ← vlastní slovíčka se stejným cizím slovem (zřídka)
   „She can read from her palm.“          ← věta
   pracka · lehký · světlý +3             ← slovník aplikace, menší a šedé
   ```
   Ve směru F→N je u vlastních jen překlad (*Učíš se i: palma*). Ze slovníku se ukazuje z každého významu jen **první varianta**, aby šly významy oddělit tečkou (`moment · přídavek · druhý`, ne `moment; okamžik · přídavek; nášup`). Načte se při otočení karty, nic se neukládá. Stejný seznam je v detailu slovíčka a u významu ze slovníku je tlačítko **„+ Učit se i tento význam“**, které založí nové slovíčko ve stejném slovníku. Na kartě jsou vlastní významy vždy všechny, ze slovníku **tolik, kolik se vejde na jeden řádek**, a *„+N“*, které zbytek rozbalí na místě (dlouhý seznam by na mobilu odsunul odpověď). Měří to prohlížeč po otočení karty i po otočení telefonu; tečka mezi slovy zůstává u předchozího slova, takže řádek nikdy nezačíná tečkou.; v detailu slovíčka všechny i se všemi variantami. Významy ze slovníku na kartě jde vypnout v Nastavení (`User.show_other_meanings`, výchozí zapnuto).

Ve směru N→F homonyma nevadí: `dlaň → palm` a `palma → palm` jsou dvě jednoznačné otázky.

**Kolize překladu:** když má víc slovíček stejnou variantu na straně otázky (např. dvě slovíčka s překladem `ahoj`):
- na zadní straně se ukáže upozornění: *„ahoj“ je i: hello*.

### 6.5 Striktní režim (fáze 2)
1. Zobrazí se výraz a pod ním textové pole.
2. Po odeslání se odpověď porovná se **všemi variantami** druhé strany. Kterákoliv varianta je správně a po správné odpovědi se ukážou ostatní (*„Správně! Také: hello“*). Při kolizi překladu se přijme i varianta jiného slovíčka se stejnou otázkou, s hláškou *„Správně, ale tady je myšleno: hi (neformálně)“*. Porovnání:
   - podle nastavení se ignorují velká a malá písmena a diakritika,
   - vždy se oříznou krajní mezery a sloučí vícenásobné,
   - při zapnuté toleranci překlepu: Levenshteinova vzdálenost ≤ 1, a to jen pro slova delší než 3 znaky.
3. Výsledek:
   - **correct:** zobrazí se odpověď a uživatel volí interval,
   - **typo:** zobrazí se „Skoro – správně je *hello*“ a uživatel volí interval,
   - **wrong:** zobrazí se správná odpověď a předvybere se „Vůbec nevím“. Uživatel může přepsat, např. když jen napsal synonymum, které chybí ve variantách.
4. U výsledku `wrong` je odkaz „Přidat mou odpověď jako variantu“.

### 6.6 Výběr z 6 (fáze 2)
1. Zobrazí se výraz a 6 možností (1 správná + 5 špatných).
2. Špatné možnosti se berou přednostně ze stejných slovníků, jinak z ostatních slovíček uživatele se stejným jazykovým párem. Nesmí to být varianty správné odpovědi.
3. Když nejsou dostupné aspoň 4 možnosti celkem, režim se pro danou kartu přepne na volný.
4. Správně: uživatel volí interval. Špatně: zvýrazní se správná odpověď a předvybere se „Vůbec nevím“.

### 6.7 Souhrn sezení
Počet karet, úspěšnost, seznam chybných slovíček a tlačítko „Procvičit chybné znovu“ (rozsah `all` nad chybnými).

**„Tohle slovíčko ti nejde“** (hotovo): jedno slovíčko z testu, které **dlouhodobě** padá a ještě nemá větu, s formulářem na větu. Cíl: místo dalšího seznamu jedna konkrétní akce na pár vteřin, protože ve větě se slovíčko učí líp.
- Výběr se počítá z `ReviewLog` (nic se neukládá navíc; `result` je kopie, takže to funguje i po změně tlačítek): posledních 8 odpovědí slovíčka (oba směry, `ROW_NUMBER() OVER (PARTITION BY term ORDER BY reviewed_at DESC)`), aspoň 3 odpovědi, podíl chyb aspoň 50 % (`wrong` = 1, `partial` = 0,5). Nejhorší první, při shodě to, co padlo víckrát. Slovíčka, která větu už mají (v některém slovníku testu), se přeskočí. `ReviewState.lapses` se nepoužívá: roste napořád a naučené slovo by z výběru nikdy nevypadlo. Konstanty `HARD_WORD_*` v `study/services.py`.
- Nad formulářem barevné tečky posledních odpovědí pro každý směr (`EN → CS`, `CS → EN`, kódy jazyků se vejdou na mobil), od nejstarší: posledních 8 (`DOTS_SHOWN`), starší za „+N“ s titulkem „12 starších: 8× 😵 · 4× 😎“, klik rozbalí až 30 (`DOTS_MAX`) a při víc odpovědích odkaz „celá historie“ do detailu slovíčka. Místo pro „+N“ je v obou řádcích, aby tečky začínaly pod sebou.
- Formulář: věta pod cizím slovem (s 🔊), překlad věty pod českým; na počítači vedle sebe, na mobilu pod sebou. Věta je povinná, překlad ne. Uloží se do `DeckTerm` slovníku, odkud test slovíčko vzal (při víc slovnících do nejdřív přidaného). HTMX, bez obnovení stránky; pak „✓ Uloženo“. „Teď ne“ formulář jen schová (po dalším testu se slovíčko může nabídnout znovu, jemné připomenutí).
- Příklad ze slovníku aplikace: věta (a její překlad) **významu**, jehož překlad sedí na překlad slovíčka (u `palm → dlaň` ne věta o palmě). „Použít“ vyplní obě pole i se značkami `{…}`; v textu nabídky se značky neukazují.

**Překlad věty na kartě:** N→F vpředu nad větou s mezerou (víš, co do mezery patří), F→N na zadní straně; šedě, bez kurzívy. Slovo v překladu se zvýrazní, když ho aplikace najde (stejný tvar jako překlad) nebo je ve složených závorkách.

---

## 7. Statistiky

Všechny statistiky se počítají z `ReviewLog` a `ReviewState`. Datový model se pro ně nemění, přibude jen index na `ReviewLog (user, term, reviewed_at)`. Počítají se dotazem nad historií. Kdyby to bylo pomalé, přidá se denní souhrnná tabulka.

### 7.1 Detail slovíčka (MVP: historie a počty; fáze 2: vizualizace)
Odpovídá na otázku „zlepšuju se?“. Zvlášť pro **každý směr**:
- kolikrát bylo slovíčko v testu a kolikrát s jakým hodnocením,
- **historie**: datum, směr, hodnocení, doba přemýšlení (`think_ms`),
- **barevná řada výsledků** v čase (hotovo): tečky v barvách tlačítek, od nejstarší, nejvýš 30 na směr (zalamované po 10), starší jen jako „+N“; vedle prstenec s podílem správných odpovědí v procentech (jen CSS, `conic-gradient`). Koláč místo teček ne: ztratil by pořadí, a tedy odpověď na „zlepšuju se?“. Barva nikdy není jediná informace: každá tečka má titulek (datum, hodnocení) a řada popis pro čtečky obrazovky.
- (fáze 2) **trend doby přemýšlení**, např. 6,1 s → 1,2 s. Ukáže zlepšení, i když hodnocení zůstává „OK“.

Ukazuje se i, ve kterých slovnících slovíčko je.

### 7.2 Statistiky slovníku (fáze 2)
```
HIMYM              slovíček   😎 vím   🤔 zamyšlení   😕 napůl   😵 nevím   nové
├── S01E01           42        70 %       15 %          10 %        5 %       0
├── S01E02           35        35 %       25 %          15 %       15 %      10 %
└── S01E03           28         —          —             —           —      100 %
```
- Stav slovíčka = jeho **poslední hodnocení** (pro zvolený směr, nebo horší z obou).
- Nadřazené uzly (S01, HIMYM) se sečtou z podslovníků, každé slovíčko se ale počítá jen jednou.
- Statistika slovníku říká, **jak znáš jeho slovíčka**, bez ohledu na to, z jakého testu odpověď přišla. Slovíčko je sdílené, takže `hello` zkoušené přes BBT se projeví i v HIMYM. Pokud by bylo potřeba rozlišit „výsledky testů spuštěných z tohoto slovníku“, jde to přes `StudySession.decks`.

### 7.3 Celkový přehled (hotovo: stránka Statistiky)
Stránka `/stats/` (odkaz v liště, na telefonu ikona 📊), počítá se při zobrazení z `Term` a `ReviewLog` (`study/stats.py`), nic se neukládá: dlaždice (slovíček celkem a tento týden, umíš / učíš se / nová, 🔥 dní v řadě a nejdelší série, odpovědí), čárový graf *Slovíčka v čase* (slovíček celkem po týdnech, 12 týdnů, osa Y s 5 kulatými hodnotami) tabulka *Poslední testy* (10 posledních testů s aspoň jednou odpovědí, počítáno z odpovědí, ne z počítadel testu: datum a čas, poslední 3 úrovně cesty slovníku s „…“ na začátku u delší cesty (celá cesta v titulku), směr „EN → CS“ / „CS → EN“ / „EN ↔ CS“, rozsah a limit, počet slovíček – při ↔ každé dvakrát, úspěšnost procentem a krátkým jednobarevným ukazatelem (počty 😎 🤔 😕 😵 v titulku), délka (⏹ u nedokončeného); nad ní počet testů za 14 dní a průměr slovíček; klik otevře souhrn testu; na telefonu blok) a sekce *Co ti nejde* (přepínač 7 dní · 30 dní · Vše, výchozí 7 dní; slovíčko „nejde“, když mělo v období 😵 nebo 😕 a v některém směru nemá 2 správné po sobě; až 9 otočných kartiček jako v testu: vpředu zvířátko s názvem kategorie a jedna strana slovíčka (střídavě cizí / rodná, u 🦀 ten těžký směr), po klepnutí vzadu druhá strana, drobně důvod a odkaz *Detail →*, odkaz na detail, slovíčko se neopakuje: 🦈 největší nepřítel (nejvíc „vůbec nevím“ z pokusů v období), 🦀 jen jedním směrem, 🐿️ zapomínáš (chyba po 2 správných za sebou), 🦎 pleteš si (2 těžká slovíčka se stejným překladem, kartička ukáže dvojici), 🐒 horská dráha (aspoň 3 změny vím ↔ nevím), 🐇 moc rychle (😵 pod 3 s), 🦒 nejdelší, 🐢 nejdéle přemýšlíš, 🐌 nejdéle se učíš). Na přehledu nad slovníky je sekce *Dnešní testy* (testy začaté dnes ve stejné tabulce, nad ní „Dnes 3 testy · 54 slovíček · úspěšnost 78 %“, jinak „Dnes ještě žádný test.“). Na přehledu pod slovníky je *Co ti dnes nejde*: až 3 menší kartičky v řádku jen z dnešních odpovědí – 🐢 nejdéle přemýšlíš, 🦀 jen jedním směrem, 🐘 pořád dokola (dnes těžké slovíčko s nejvíc pokusy v celé historii, aspoň 3); bez dnešních těžkých slovíček se sekce neukáže. Graf je čisté SVG bez knihovny (popisky a tečky jsou HTML, aby se na telefonu nedeformovaly); souřadnice se posílají jako text, protože česká lokalizace šablon by psala desetinnou čárku. Původní seznam:
- počet zopakování za den a týden,
- úspěšnost v čase (podíl hodnocení OK po týdnech),
- série dní v řadě,
- počet přidaných slovíček v čase,
- rozložení slovíček podle stavu (nová / učím se / umím).

### 7.4 Problémová slovíčka (fáze 2)
- **často zapomínaná:** vysoké `lapses`,
- **zhoršující se:** dřív OK, teď „vůbec nevím“,
- **pomalá:** hodnocení OK, ale dlouhé `think_ms`,
- tlačítko „Procvičit tato slovíčka“ spustí test nad výběrem.

---

## 8. Obrazovky

| Obrazovka | Obsah |
|---|---|
| Přihlášení / Odhlášení | Django auth, e-mail + heslo (registrace v MVP není) |
| **Přehled (dashboard)** | Tlačítko „Spustit test · N k opakování“, dnešní testy, strom slovníků s počty za názvem (celkem / k opakování), co ti dnes nejde |
| **Hledat** (`/search/`) | pole nahoře na přehledu, klávesa `/` (stránka `/search/` jen pro Enter bez JavaScriptu): hledá ve všech slovíčkách uživatele (varianty, věta a její překlad, poznámka) bez háčků a velikosti písmen, od 2 znaků, při psaní; nejdřív shoda ve slově/překladu, pak ve větě/poznámce; zvýrazněná shoda, slovníky (poslední 3 úrovně cesty), detail a ✎; max 50 (`vocabulary.services.search_terms`) |
| **Slovník** | Drobečková navigace, seznam slovíček (vyhledávání, řazení: podle data přidání (výchozí) / abecedně / podle termínu opakování), formulář pro přidání, výběr slovíček a jejich přesun / přidání do jiného slovníku, podslovníky (šipky ↑ ↓ pro pořadí), úprava, přesun a smazání slovníku, „Testovat tento slovník“ |
| **Slovíčko** | Úprava variant, poznámky a kontextů v jednotlivých slovnících, stav opakování obou směrů, statistiky a historie (7.1) |
| Statistiky | Celkový přehled a problémová slovíčka (7.3, 7.4, fáze 2) |
| **Nápověda** | Záložky Slovníky, Slovíčka, Test, Přehled a statistiky; každá záložka je vlastní stránka (`/help/<záložka>/`). Tabulka tlačítek se generuje z `study/ratings.py`. Při změně funkce se aktualizuje i nápověda. |
| **Nastavení testu** | viz 6.1 |
| **Test** | Jedna karta, velká tlačítka, ovladatelné palcem |
| **Souhrn testu** | viz 6.7 |
| **Nastavení** | Rodný jazyk, výchozí směr, pravidla striktního režimu |
| Vyhledávání | Napříč všemi slovníky (fáze 2) |

Všechny obrazovky jsou mobile-first. Test musí být pohodlný na telefonu (tlačítka dole, žádné drobné prvky).

---

## 9. Fáze

### Fáze 1 – MVP
- **Responzivní UI od začátku:** mobil i počítač, mobile-first
- Přihlášení e-mailem, uživatelské nastavení (účty zakládá admin ručně)
- Jazyky (admin, ISO 639-1)
- Vlastní User model od začátku
- Slovníky ve stromu (max. 5 úrovní, CRUD, přesun, pořadí šipkami ↑ ↓, přetahování na přehledu), jazykový pár v závorce u názvu, drobečková navigace
- Řazení slovíček ve slovníku (datum přidání / abecedně / termín opakování)
- Ruční přidávání slovíček: varianty na obou stranách, volitelná věta (píše ji uživatel), kontrola duplicit na obou stranách, přesun vybraných slovíček do jiného slovníku
- Homonyma v testu: věta jako nápověda, počet významů, další významy na zadní straně (vlastní i ze slovníku), rozestup
- Test: **jen volný režim** (zobrazit, zamyslet se, otočit, ohodnotit); oba směry i zamíchat
- Hodnocení 4 tlačítky s emoji (😎 🤔 😕 😵) a rostoucími intervaly (6.3), jako konstanta v kódu; legenda, klávesové zkratky
- Měření doby odpovědi (`think_ms`, `decide_ms`)
- Detail slovíčka: počty a historie odpovědí pro každý směr (7.1)
- ReviewState + ReviewLog
- Dashboard
- Běh lokálně (lokální PostgreSQL)

### Fáze 2
- Striktní režim (psaní odpovědi, nastavitelná tolerance)
- Výběr z 6
- Výběr významu přes LLM (viz 5.2): živé dotazy, sdílená cache, našeptávání; později předgenerovaný slovník častých slov
- Akce „rozdělit slovíčko“ a „sloučit slovíčka“
- Hlas na serveru (Piper) jako jednotná kvalita výslovnosti na všech zařízeních
- Hromadné přidání
- Vyhledávání (přes `unaccent`, takže `cau` najde `čau`)
- Zadávání variant jako „štítků“
- Statistiky: vizualizace u slovíčka, statistiky slovníků, celkový přehled, problémová slovíčka (sekce 7)
- PWA (manifest, ikona, instalace na plochu)
- Nasazení na vlastní server
- Registrace, reset hesla, odesílání e-mailů
- Denní limit nových slovíček

### Fáze 3
- Veřejné slovníky: zveřejnění, katalog, zkopírování (při kopii se slovíčka spojí s existujícími)
- Import titulků `.srt`
- Vlastní hodnoticí tlačítka (`RatingButton`), volba pořadí tlačítek
- Chytré návrhy intervalů (SM-2 / FSRS)
- Problémová slovíčka (vysoké `lapses`) a jejich procvičení
- Poslechový režim (slovíčko se přehraje a uživatel ho píše)
- Push notifikace „čeká tě X slovíček“

### Fáze 4
- Přidávání hlasem a z audia (mikrofon, soubor, Whisper)
- Srovnávání statistik s přáteli, žebříčky, nastavení soukromí
- Export a import (CSV, Anki)
- Případně nativní aplikace (Capacitor nebo API + nativní klient)

---

## 10. Otevřené otázky

1. **Jazyk UI:** předpoklad je jen čeština, texty se ale budou psát tak, aby šly později přeložit (Django i18n).
