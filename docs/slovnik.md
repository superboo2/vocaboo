# Vocaboo – slovník aplikace a balíčky nových slov

Slovník aplikace (návrhy překladu, další významy, IPA, věty, slovíčka z tématu) je **v souborech**,
databáze je jen kopie pro rychlé hledání:

```
dictionary/data/
  concepts.jsonl               pojmy (významy) s texty v jednotlivých jazycích (zdroj "base")
  words_en.jsonl               anglická slova, každé odkazuje na své pojmy
  lexicon_tags.json            značky pojmů (témata)
  lexicon_en_cs.old.jsonl      starý formát (jen záloha, aplikace ho nečte)
  extensions/
    2026-11-02/                balíček nových slov (zdroj "2026-11-02")
      concepts.jsonl
      words_en.jsonl
      report.txt               zpráva: co se se slovy ze seznamu udělalo
```

- Složka `dictionary/data/` není v gitu. Soubory leží u autora a na serveru, balíčky tam vždycky
  zůstávají (jsou to zálohy).
- U každého pojmu a slova je v databázi `source` (`base` / `2026-11-02`), v adminu jde podle něj
  filtrovat (*Slovník › Pojmy*, *Slovník › Slova slovníku*).

## Jak je slovník postavený

**Pojem** je jeden význam, stejný ve všech jazycích. Má **stálé ID** `slovo.slovní_druh.číslo`
(`palm.noun.1` = dlaň, `palm.noun.2` = palma), značky a **text v každém jazyce**: slova (varianty
oddělené `; `), poznámku pro čtenáře toho jazyka a ukázkovou větu. Co pojem znamená, určuje jeho
**anglická věta**; popisky pojmy nemají.

Představa: **velká tabulka**, kde řádek je pojem (anglický význam) a každý jazyk má „sloupec“
s překladem, poznámkou a větou (to jsou texty pojmu, oddělené: `words`, `note`, `sentence`).

**Nápověda pro jakýkoli pár X → Y:** napsané slovo se najde ve sloupci jazyka X (každá varianta
textu zvlášť: „kočka; kocour“ → *kočka*, *kocour*) a vezme se sloupec jazyka Y. Dva jazyky se
potkávají v pojmu, ne v anglickém slově:

```
CS → EN:  „kočka“ ve sloupci cs → cat.noun.1 → sloupec en → cat
ES → CS:  „gato“  ve sloupci es → cat.noun.1 → sloupec cs → kočka; kocour
EN → ES:  „cat“   ve sloupci en → cat.noun.1 → sloupec es → gato
```

Pořadí návrhů, slovní druh a úroveň (u slovíček z tématu) se berou z anglického slova pojmu.

**Slovo** (`words_<jazyk>.jsonl`) jsou **doplňky** k jednomu jazyku: slovo s jedním slovním
druhem, jeho tvary (*palms*, *clung*, *gatos*), výslovnost (IPA), četnost, úroveň, rod a seznam
pojmů, které znamená (od nejčastějšího). Výslovnost patří ke slovu, ne k pojmu (*palm* zní
stejně, ať je to dlaň, nebo palma). Dnes má slova jen angličtina.

**Jazyky:** dnes en (texty + slova) a cs (texty). Další jazyk se doplňuje **postupně**:

- **texty pojmů v novém jazyce** (třeba `es`: překlad, poznámka, věta) → hned funguje nápověda a
  slovíčka z tématu pro **všechny páry** s tím jazykem (EN → ES, ES → CS, CS → ES …); pojmy bez
  textu v tom jazyce se zatím neukazují,
- **slova nového jazyka** (`words_es.jsonl`) → výslovnost (IPA) a nápověda i podle tvarů
  (*gatos*, *hablo*), ne jen podle základního tvaru.

Při přidání nového jazyka do slovníku doplnit i ukázku pro prázdné pole slovíčka
(`VARIANT_SAMPLES` ve `vocabulary/forms.py`, dvě varianty slova v tom jazyce, třeba
`"es": "hola; buenas"`); ukázky jsou jen pro jazyky, které slovník má.

Pravidla ID: ID se **nikdy nemění** (věta se smí opravit, ID ne); nový pojem dostane další volné
číslo u svého slova a druhu (`palm.noun.3`); pořadí významů je v seznamu `senses` slova, ne
v čísle ID.

## Postup: jednou za čas nová slova

1. **Na serveru** vypsat anglická slova, ke kterým aplikace neměla nápovědu:
   ```bash
   sudo -u vocaboo -H ~vocaboo/.local/bin/uv run python manage.py missing_words
   ```
2. **Lokálně** seznam vložit Claudovi s větou:
   > Rozšiř slovník podle `docs/slovnik.md`, tady jsou chybějící slova: …
3. Claude podle pravidel níže napíše balíček, složku `dictionary/data/extensions/RRRR-MM-DD/`
   (datum dne, kdy vzniká; druhý balíček ve stejný den `RRRR-MM-DD-2`) se soubory
   `concepts.jsonl`, `words_en.jsonl` a `report.txt`, a zkontroluje ho
   (`extend_lexicon … --check`).
4. **Na server** zkopírovat celou složku balíčku do `dictionary/data/extensions/` a spustit:
   ```bash
   sudo -u vocaboo -H ~vocaboo/.local/bin/uv run python manage.py extend_lexicon \
       dictionary/data/extensions/2026-11-02
   changed  pros → pro (plural, form added to "pro")
   fixed    urin → urine (typo)
   skipped  wep (unclear word)
   Package 2026-11-02: concepts added 21, changed 0; words added 21, changed 2.
   ```
   Nejdřív se všechno zkontroluje, při chybě se nezapíše nic (vypíše soubor, řádek a důvod).
   Pak se vypíše zpráva k balíčku a souhrn; *changed* = pojmy a slova, která už ve slovníku
   byla a balíček je upravil. Totéž bez zápisu ukáže `--check`. Aplikace nepotřebuje restart.
5. Kontrola: `missing_words` na serveru už ta slova nevypíše.

**Nový server / přesun databáze:** zkopírovat celou složku `dictionary/data/` a spustit
`import_lexicon` (nahraje základ a všechny balíčky podle data; `import_lexicon --check` jen
zkontroluje soubory).

## Postup: překlad do dalšího jazyka (postupně)

Nový jazyk se přidává **balíčky jen s texty toho jazyka** ke stávajícím pojmům, po 500–1 000
pojmech, **nejčastější první** (podle `band` anglického slova, v pořadí souboru a významů).
Další balíček vezme dalších N nejčastějších pojmů, které ještě **nemají text v tom jazyce**
(ani v `concepts.jsonl`, ani v žádném balíčku v `extensions/`); vstup pro překlad je u každého
pojmu jeho anglické slovo a věta a české slovo a poznámka.
Po každém balíčku funguje nápověda a slovíčka z tématu pro přeložené pojmy ve všech párech
s tím jazykem; nepřeložené se zatím neukazují.

- Balíček: `extensions/RRRR-MM-DD/concepts.jsonl` s řádky
  `{"id": "cat.noun.1", "texts": {"es": {"words": "gato; gata", "sentence": "El {gato} duerme en el sofá."}}}`
  a `report.txt` s jedním řádkem, třeba `added    es: 1000 concepts (the most common, band 1)`.
- Spuštění stejně jako u nových slov: `extend_lexicon dictionary/data/extensions/RRRR-MM-DD`.
- Slova jazyka (`words_es.jsonl`: IPA, tvary, rod, četnost) později zvlášť.
- K jazyku patří ukázka pro prázdné pole (`VARIANT_SAMPLES`, viz výše).

**Pravidla překladu (prompt pro AI):**

- Překládá se **význam**, ne anglické slovo: význam určuje anglická věta pojmu, české slovo a
  poznámka pomůžou poznat, o který jde (*palm.noun.1* dlaň → *palma*, *palm.noun.2* strom →
  *palmera*).
- **Španělština evropská** (Španělsko: *coche*, *ordenador*, *móvil*, *vosotros*); běžné
  latinskoamerické slovo smí být další varianta (*coche; carro*).
- `words`: slova pro ten význam, nejběžnější první, nejvýš 3 varianty oddělené `; `;
  podstatná jména bez členu (*gato*), u lidí a zvířat obě podoby (*gato; gata*, *profesor;
  profesora*), slovesa v infinitivu, fráze přirozeně.
- `sentence`: přirozený překlad anglické věty (stejný význam, ne slovo od slova), slovo pojmu
  ve `{}` v tvaru, jaký má ve větě; poznámka (`note`) zatím ne.
- Vlastní slova, nic nekopírovat; běžný, přirozený jazyk.

**Hotové balíčky:**

| Balíček | Jazyk | Pojmy |
|---|---|---|
| 2026-10-20 | es | 999 z 1 000 nejčastějších (band 1; *would* vynecháno, ve španělštině je to jen koncovka) |
| 2026-10-20-2 | es | dalších 500 (zbytek band 1 = 314, začátek band 2 = 186) |
| 2026-10-20-3 | es | dalších 200 (band 2) |
| 2026-10-20-4 | es | dalších 200 (band 2) |
| 2026-10-20-5 | es | dalších 200 (band 2) |

## Pravidla pro balíček (prompt pro AI)

Tuto část čte AI, která balíček píše.

### Co se slovy ze seznamu udělat

Každé slovo ze seznamu `missing_words` patří do jedné skupiny:

- **Nové slovo:** opravdové anglické slovo nebo ustálená fráze (*ogre*, *suit up*, *fella*).
  Napsat pojmy jeho významů (`concepts.jsonl`) a slovo (`words_en.jsonl`). Hovorová slova ano
  (se značkou `hovorove` a poznámkou „hovorově“), vulgární jen se značkou `vulgarni` a
  poznámkou „vulgárně“.
- **Tvar existujícího slova:** množné číslo, minulý čas, jiný zápis (*kids* → *kid*, *ran* →
  *run*, *colour* → *color*). Najít slovo v `dictionary/data/words_en.jsonl` (nebo v posledním
  balíčku, který ho obsahuje), zkopírovat jeho řádek **celý beze změny** do `words_en.jsonl`
  balíčku a jen přidat tvar do `forms` (malými písmeny). Pojmy se nemění.
- **Nový význam existujícího slova:** nový pojem s dalším volným číslem (`get.verb.7`) a řádek
  slova celý znovu s novým ID v `senses` (na místě podle četnosti).
- **Vynechat:** překlepy (*recieve*), nesmysly, jména osob a značek, česká nebo jiná než anglická
  slova, zkratky bez obecného významu.

Slovo, které už ve slovníku je (třeba jen jiným slovním druhem), zkontrolovat: chybí-li slovní
druh, který uživatelé zjevně myslí, přidat slovo s tímto druhem.

### Pojem (`concepts.jsonl`)

Jeden řádek = jeden pojem jako JSON (UTF-8, bez zalamování):

```json
{"id": "ogre.noun.1", "tags": ["film"],
 "texts": {"en": {"words": "ogre", "sentence": "{Ogres} are like onions."},
           "cs": {"words": "zlobr", "note": "", "sentence": "{Zlobři} jsou jako cibule."}}}
```

- `id`: `slovo.slovní_druh.číslo` podle anglického slova, číslo od 1 (další volné u toho slova
  a druhu).
- `tags`: 0–2 značky **jen** ze `lexicon_tags.json` (pole `slug`).
- `texts`: text pojmu pro každý jazyk slovníku (**dnes `en` a `cs`**):
  - `words`: slova toho jazyka pro pojem, varianty oddělené `; ` (*představit; představovat*);
    u `en` to anglické slovo,
  - `note`: krátká nápověda pro čtenáře toho jazyka, která významy odliší (*o místě*,
    *hovorově*), jinak `""` nebo vynechat; jen u slov s víc významy, hovorových a vulgárních,
  - `sentence`: krátká přirozená věta (do 10 slov), slovo v ní ve `{složených závorkách}`
    (i v jiném tvaru: `{ran}`); **anglická věta je povinná** (určuje význam pojmu), věta
    v dalším jazyce je její překlad (odpovídající slovo ve `{}`, když jde označit).
- Doplnění jazyka k existujícímu pojmu (postupné překlady): řádek jen s `id` a texty nových
  jazyků, `{"id": "palm.noun.1", "texts": {"es": {"words": "palma", "sentence": "…"}}}`;
  ostatní jazyky a značky zůstanou.

### Slovo (`words_en.jsonl`)

```json
{"word": "ogre", "pos": "noun", "band": 12, "level": "B2", "ipa": "ˈəʊɡə", "forms": ["ogres"],
 "senses": ["ogre.noun.1"]}
```

- `word`: základní tvar, malými písmeny (kromě slov, která se píšou velkým písmenem).
- `pos`: `noun`, `verb`, `adjective`, `adverb`, `pronoun`, `determiner`, `preposition`,
  `conjunction`, `interjection`, `numeral`, `phrasal_verb`, `phrase`.
- `band`: četnost v **mluvené** angličtině (seriály, běžná řeč): 1 = 1 000 nejčastějších slov,
  2 = dalších 1 000 … Odhadnout skutečnou četnost jako u základu, ne podle toho, že slovo je
  nové. Vzácnější než cokoli v základu smí mít i 15 a víc.
- `level`: CEFR `A1`–`C2`.
- `ipa`: britská výslovnost v IPA **bez** lomítek a závorek.
- `forms`: jiné tvary a zápisy, podle kterých se má slovo najít (malými písmeny: *ogres*,
  *clung*, *mum*), jinak `[]`.
- `senses`: ID pojmů **od nejčastějšího** významu.
- `gender`: jen u jazyků s rodem (pozdější slova jiných jazyků), jinak vynechat.

### Obsah

- Vše psát vlastními slovy, nic nekopírovat ze slovníků (Wiktionary, Cambridge) ani korpusů
  (Tatoeba). Četnost ze znalostí jen jako vodítko.
- Věty běžné, ze života, bez jmen skutečných lidí; čeština přirozená, ne doslovná.
- Česky genderově neutrálně, kde to jde.

### Zpráva k balíčku (`report.txt`)

Anglicky, **jedno slovo na řádek** (nejdřív všechna `changed`, pak `fixed`, pak `skipped`), druh
zarovnaný na 9 znaků a za slovem krátký důvod v závorce:

```
changed  pros → pro (plural, form added to "pro")
changed  ran → run (past tense, form added)
fixed    urin → urine (typo)
skipped  ridicilous (typo, "ridiculous" is already in the dictionary)
skipped  wep (unclear word)
```

- `changed`: slovo převedené na základní tvar (množné číslo, čas, jiný zápis).
- `fixed`: překlep, za který je v balíčku správné slovo.
- `skipped`: vynechané slovo a proč.

Nová slova ze seznamu se do zprávy nepíšou.

### Kontrola před předáním

```bash
uv run python manage.py extend_lexicon dictionary/data/extensions/RRRR-MM-DD --check
```

Kontroluje platný JSON, tvar ID pojmu, texty (slova v každém jazyce, anglická věta nového
pojmu se `{slovem}`), známé značky, povinná pole slova, slovní druh, `band`, `level`, že každé
ID v `senses` existuje (v balíčku nebo ve slovníku) a slovo dvakrát v jednom souboru. Lokálně
jde balíček i rovnou vyzkoušet: `extend_lexicon …` bez `--check` a pak `missing_words`.
