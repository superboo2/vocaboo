# Vocaboo – slovník aplikace a balíčky nových slov

Slovník aplikace (návrhy překladu, další významy, IPA, věty) je **v souborech**, databáze je jen
kopie pro rychlé hledání:

```
dictionary/data/
  lexicon_en_cs.jsonl          základ (zdroj "base")
  lexicon_tags.json            značky významů
  extensions/
    2026-10-19.jsonl           balíček nových slov (zdroj "2026-10-19")
    2026-10-19.report.txt      jeho zpráva: co se se slovy ze seznamu udělalo
    2026-11-16.jsonl           …
```

- Složka `dictionary/data/` není v gitu. Soubory leží u autora a na serveru, balíčky tam vždycky
  zůstávají (jsou to zálohy).
- **Heslo** = jedno anglické slovo s jedním slovním druhem. Angličtina je osa slovníku, překlady
  a věty jsou ve všech jazycích slovníku (dnes jen `cs`).
- Pozdější soubor **nahradí** heslo se stejným slovem a slovním druhem. Balíček tak může i
  upravit existující heslo (nový tvar, nový význam), a stejný balíček spuštěný dvakrát nic
  nezdvojí.
- U každého hesla je v databázi `source` (`base` / `2026-10-19`), v adminu jde podle něj
  filtrovat (*Slovník › Hesla slovníku*).

## Postup: jednou za čas nová slova

1. **Na serveru** vypsat anglická slova, ke kterým aplikace neměla nápovědu:
   ```bash
   sudo -u vocaboo -H ~vocaboo/.local/bin/uv run python manage.py missing_words
   ```
2. **Lokálně** seznam vložit Claudovi s větou:
   > Rozšiř slovník podle `docs/slovnik.md`, tady jsou chybějící slova: …
3. Claude podle pravidel níže napíše balíček `dictionary/data/extensions/RRRR-MM-DD.jsonl`
   (datum dne, kdy vzniká; druhý balíček ve stejný den `RRRR-MM-DD-2.jsonl`) a vedle něj
   zprávu `RRRR-MM-DD.report.txt` (viz *Zpráva k balíčku*), a zkontroluje ho
   (`extend_lexicon … --check`).
4. **Na server** zkopírovat balíček i zprávu do `dictionary/data/extensions/` a spustit:
   ```bash
   sudo -u vocaboo -H ~vocaboo/.local/bin/uv run python manage.py extend_lexicon \
       dictionary/data/extensions/2026-10-19.jsonl
   changed  pros → pro (plural, form added to "pro")
   changed  cons → con (plural, form added to "con")
   fixed    disingenuou → disingenuous (typo)
   fixed    urin → urine (typo)
   skipped  ridicilous (typo, "ridiculous" is already in the dictionary)
   skipped  wep (unclear word)
   Package 2026-10-19: added 21 entries, changed 2, 31 senses.
   ```
   Nejdřív se soubor zkontroluje, při chybě se nezapíše nic (vypíše řádek a důvod). Pak se
   vypíše zpráva k balíčku a souhrn; *changed* v souhrnu = hesla, která už ve slovníku byla a
   balíček je přepsal. Totéž bez zápisu ukáže `--check`. Aplikace nepotřebuje restart.
5. Kontrola: `missing_words` na serveru už ta slova nevypíše.

**Nový server / přesun databáze:** zkopírovat celou složku `dictionary/data/` a spustit
`import_lexicon` bez cesty. Nahraje základ a všechny balíčky podle data
(`import_lexicon --check` jen zkontroluje soubory).

## Pravidla pro balíček (prompt pro AI)

Tuto část čte AI, která balíček píše.

### Co se slovy ze seznamu udělat

Každé slovo ze seznamu `missing_words` patří do jedné skupiny:

- **Nové heslo:** opravdové anglické slovo nebo ustálená fráze (*ogre*, *suit up*, *fella*).
  Napsat celé heslo podle formátu níže. Hovorová slova ano (se značkou `hovorove` a poznámkou
  „hovorově“), vulgární jen se značkou `vulgarni` a poznámkou „vulgárně“.
- **Tvar existujícího hesla:** množné číslo, minulý čas, jiný zápis (*kids* → *kid*, *ran* →
  *run*, *colour* → *color*). Najít heslo v základu nebo v posledním balíčku, který ho obsahuje,
  zkopírovat jeho řádek **celý beze změny** a jen přidat tvar do `forms` (malými písmeny). Tím
  se k tvaru začne nabízet nápověda.
- **Vynechat:** překlepy (*recieve*), nesmysly, jména osob a značek, česká nebo jiná než anglická
  slova, zkratky bez obecného významu. V souhrnu je vypsat s důvodem.

Slovo, které už ve slovníku je (třeba jen jiným slovním druhem), zkontrolovat: chybí-li slovní
druh, který uživatelé zjevně myslí, přidat nové heslo s tímto druhem.

### Formát řádku

Jeden řádek = jedno heslo jako JSON (UTF-8, bez zalamování), stejně jako v základu:

```json
{"word": "ogre", "pos": "noun", "band": 12, "level": "B2", "ipa": "ˈəʊɡə", "forms": ["ogres"],
 "senses": [{"cs": "zlobr", "note": "", "sentence": "{Ogres} are like onions.",
             "sentence_cs": "{Zlobři} jsou jako cibule.", "tags": ["film"]}]}
```

- `word`: heslo v základním tvaru, malými písmeny (kromě slov, která se píšou velkým písmenem).
- `pos`: `noun`, `verb`, `adjective`, `adverb`, `pronoun`, `determiner`, `preposition`,
  `conjunction`, `interjection`, `numeral`, `phrasal_verb`, `phrase`.
- `band`: četnost v **mluvené** angličtině (seriály, běžná řeč): 1 = 1 000 nejčastějších slov,
  2 = dalších 1 000 … Odhadnout skutečnou četnost jako u základu, ne podle toho, že slovo je
  nové. Vzácnější než cokoli v základu smí mít i 15 a víc.
- `level`: CEFR `A1`–`C2`.
- `ipa`: britská výslovnost v IPA **bez** lomítek a závorek.
- `forms`: jiné zápisy a tvary, podle kterých se má heslo najít (malými písmeny), jinak `[]`.
- `senses`: významy **od nejčastějšího**, každý:
  - `cs`: český překlad, varianty oddělené `; ` (*představit; představovat*),
  - `note`: krátká nápověda, která významy odliší (*o místě*, *hovorově*), jinak `""`,
  - `sentence`: krátká přirozená anglická věta (do 10 slov), slovo v ní ve `{složených
    závorkách}` (i v jiném tvaru: `{ran}`),
  - `sentence_cs`: český překlad věty, odpovídající slovo ve `{}` (když jde označit),
  - `tags`: 0–2 značky **jen** ze `lexicon_tags.json` (pole `slug`).
- Další jazyky slovníku (až budou): u každého významu pole `es`, `sentence_es` atd. stejně jako
  `cs`. **Jazyky slovníku dnes: `cs`.**

### Obsah

- Vše psát vlastními slovy, nic nekopírovat ze slovníků (Wiktionary, Cambridge) ani korpusů
  (Tatoeba). Četnost ze znalostí jen jako vodítko.
- Věty běžné, ze života, bez jmen skutečných lidí; čeština přirozená, ne doslovná.
- Česky genderově neutrálně, kde to jde.

### Zpráva k balíčku

Soubor `RRRR-MM-DD.report.txt` vedle balíčku, anglicky, **jedno slovo na řádek** (nejdřív
všechna `changed`, pak `fixed`, pak `skipped`), druh zarovnaný na 9 znaků a za slovem krátký
důvod v závorce:

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

Nová hesla ze seznamu se do zprávy nepíšou.

### Kontrola před předáním

```bash
uv run python manage.py extend_lexicon dictionary/data/extensions/RRRR-MM-DD.jsonl --check
```

Kontroluje platný JSON, povinná pole, slovní druh, `band`, `level`, `{slovo}` ve větě, známé
značky a heslo dvakrát v jednom souboru. Lokálně jde balíček i rovnou vyzkoušet:
`extend_lexicon …` bez `--check` a pak `missing_words`.
