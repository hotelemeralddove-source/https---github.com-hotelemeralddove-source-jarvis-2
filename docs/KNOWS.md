# "Jarvis knows everything" — actually enna panrom machi

Neenga sonnadhu: *"jarvis have everything, jarvis knows everything nu irukanum."*

Correct ah purinjirukken. Aana oru vishayam straight ah sollanum: **ellathayum therinja
madiri nadikkura assistant, ellathayum theriyara assistant-a vida mosam.** Adhaan reason
— "kalpa" pannama, unmaiyana "enakku theriyadhu" sollura oru library build pannen.

Idhu eppadi velai seyyudhu:

---

## 1. Nalu source — adhu mattum

| Source | Enna irukku | Enna panna maatan |
|---|---|---|
| **Shelf** (`arcdesk/world.py`) | **75 facts**, 8 domain: india · world · science · tech · money · health · food · myths. Ovvoru entry-kum **source + year** irukku | year illama oru number solla maatan (population, CO₂, repo rate, GST slab) |
| **Ungaloda files** | `facts{ingest}` kudutha folder-a padikkum — txt, md, csv, json, **pdf, docx, xlsx, pptx** | ungaloda file-a "interpret" panni puthu claim kattamattan — **quote** pannuvan, file name-oda |
| **Live lookup** | `fetch` → Wikipedia, URL + padicha date-oda, 7 naal cache | net illama irundha memory-la irundhu answer panna maatan — "source reach aagala" nu solluvan |
| **Machine itself** | clock, CPU, RAM, disk, reminders, calendar, focus minutes | measure pannadha number-a print panna maatan |

Indha nalum thavira vera enna kekkuravanga — **inniki news, gold price, yaaru ippo
CM-a irukkara** — idhukku answer:

> *"I do not know that one, and I will not improvise it."* + oru real search link.

Adhu weakness illa machi. Adhu dhaan strength.

---

## 2. Try pannunga — veetla irundhu

```bat
:: shelf-la enna irukku
"what do you know"

:: specific answers, source-oda
"how tall is everest"          -> 8,848.86 m (Nepal + China, 2020)
"how many states in india"     -> 28 states + 8 UTs (2019 reorganisation)
"what is cpr"                  -> 30:2, with the source
"what is a qubit"              -> shelf answer, source-oda
"tell me a fact"               -> random entry, cite pannirukku

:: ungaloda sonna files
"index my notes folder"        -> <n> files, <m> searchable chunks
"what is the rooftop cafe called"  -> ungaloda file-la irundhu adhe sentence quote

:: live lookup
"fetch Vikram Sarabhai"        -> Wikipedia summary + URL + date

:: honest no
"who won the 2024 election"    -> "I do not know" + search link
"gold price today"             -> same (live quote tool irundha adhu use pannum)
```

---

## 3. Year eppovum varum — idhu dhaan rule

Drift aagura number-a "today" nu solla koodadhu. Adhaan `moves=True` flag:

| Kekkurvanga | ARC enna solum |
|---|---|
| "what is india's population" | 1.4 billion **— as of 2024, and this number changes** |
| "what is the repo rate" | 6.50% **— as of 2024** (rate change aagirukkalaam, verify pannunga) |
| "what is china's population" | about 1.43 billion **— as of 2024** |

`tests/test_world.py` idha check pannum: oru moving entry-la year illama poana, **build fail**.

---

## 4. Neenga file add pannuradhu eppadi

```bat
:: 1. edhavadhu folder-la notes/docs vechiko, illa default library folder use pannunga
::    %APPDATA%\ArcDesk\library

:: 2. ARC-kitta sollunga
"index my notes folder"
"add this folder to your library"

:: 3. appuram normal ah kelunga — ARC ungaloda file-la irundhu quote pannum,
::    file name-oda. "Quoted, not paraphrased" nu kooda sollum.
```

Enna nadakkum, enna aagadhu:

- **Nadakkum:** text extract, chunk, local index file in your ArcDesk data folder, search.
- **Aagadhu:** file modify, copy, upload. Ellame ungaloda disk-la dhaan.

---

## 5. Enna innum theriyadhu (straight answer)

Idhu 75 facts library. Adhu **encyclopedia illa**. Ippo theriyadhu:

- inniki nadandha edhuvum (news, election result, match score)
- live price (gold, stock, crypto) — adhukku `market` tool, network venum
- yaaru ippo endha post-la irukkaranga
- ungaloda personal data, neenga index pannadhu thavira
- 75-la illadha edhuvum — adhukku `fetch` use pannunga, illa text paste pannunga

Adhu 75 → 150 aaga easy. Aana **sourced + dated** ah mattum dhaan aagum. Illama
number-a kooda add panna maatan.

---

## 6. Short version (English)

> ARC has a **sourced, dated library** (75 facts), **your own indexed files**, a **live
> lookup that cites its date**, and **its own measurements**. Outside those four it says
> *"I do not know"* and gives you a link. That is what "knows everything" honestly means
> for an offline desktop assistant — and `tests/test_world.py` enforces it.
