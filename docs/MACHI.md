# Machi, indha ARC-oda brain epdi velai seiyudhu

*(In English at the bottom: the four honesty rules. This page is for reading in Tanglish.)*

Naan unakku solla poradhu ellam **code-la irukkurathu** dhaan — `arcdesk/coach.py`,
`arcdesk/planner.py`, `arcdesk/library.py`, `arcdesk/player.py`. Edhuvum promise illa,
ellam measured.

---

## 1. Naan unakku friend, guide, mentor, analyst — ellame, aana oru order-la

Neenga enkitta pesumbodhu, naan **munnadi kekkuven, appuram dhaan advice**. Adhu
"wellwisher" nu sollradhu idhu dhaan — advice kudukkuradhu easy, kekkuradhu kashtam.

| Neenga sonna | Naan enna panren | Yaaru |
|---|---|---|
| "machi i feel low da, business varala" | Oru varthaikku kooda advice illa. Naan unga feelings-a value panren, **oru kelvi** mattum kekkuven | wellwisher |
| "mentor me on direct bookings" | Oru framework + **indha today oru action**. Constraints enna nu naan kekkuven, guess panna maaten | mentor |
| "analyse our occupancy 70.8 68.0 65.1" | Neenga kudutha numbers mattum. Trend, spread, and enna theriyala nu thelivaaga | analyst |
| "should i take the loan or wait" | Answer solla maaten — **decision frame** kuduppen: reversible-ah? enna optimise panren? wait pannina cost enna? | guide |
| "give me a plan for next 7 days" | 7 naal, ovvonnum oru chinna action. Market pathi naan guess panna maaten | mentor |
| "scan my disk and play kabira" | Plan poduven, steps kaattuven, appuram **really** run pannuven | worker |

Neenga Tanglish-la pesina, naan Tanglish-la answer pannuven. "Machi, neenga solradhu
puriyudhu" — adhu template, aana adhu unmai dhaan.

---

## 1b. "Idhu enna error da" — naan error-a padikkiren

Idhu dhaan neram 11 mani-kku oru manushanukku ARC kitta irundhu venum — kavithai illa,
*"indha screen-la enna solludhu?"*

Naan 24 error families-a munnadiye padichirukken: Windows start-up codes (`0xc000007b`,
`0x80070005`), blue screen stop codes, SmartScreen, Python traceback, git, DNS /
connection-refused / 404 / certificate / offline, ffmpeg, file lock, corrupt document,
sound device, USB disk.

**Epdi nadakkum:**

1. Neenga type pannalaam, illa copy pannalaam (clipboard), illa `"what is this error on my
   screen"` nu sonna naan screenshot eduthu OCR pannuven.
2. Naan **mudhalla quote pannuven** — naan enna padichen-nu unakku kaatuven. OCR thapp-a
   padichirundha, unakku theriyum.
3. Appuram: enna artham → yen varudhu (most likely first) → enna panradhu (ordered steps) →
   ARC enna panna mudiyum / mudiyadhu → **certain** illa **likely**.

**Mukkiyam:** oru error enakku theriyala na, naan **guess panna maaten**. Andha line-a
thirumba quote pannuven, "I do not recognise this one" nu solluven, search phrase kuduppen.
Idhu dhaan un rule — *"assume pana koodathu"*. Thappaana fix, 11 mani-kku, un file-a
azhichudum. Adhu naalum ketta dhaan.

Example — neenga paste pandradhu:

> The application was unable to start correctly (0xc000007b).

Naan sollradhu:

> **Windows could not start the program (0xc000007b)** — Windows found the program, but a
> library it needs is the wrong bit-width or version. The program did not run at all.
>
> Why, most likely first: 32-bit program loading a 64-bit DLL · missing/broken Visual C++
> Redistributable · half-finished install.
>
> Do this, in order: reinstall from its own installer · install the matching VC++
> Redistributable (x86 and x64) · if it worked before, roll back the newest Windows Update.
>
> ARC: say 'system report' — it shows whether the disk has room for a reinstall.

---

## 1c. "Which file-la idhu irukku?" — file-oda **ullae** theduven

Munnaadi naan file **peru** mattum thedinen. `budget.xlsx` enga irukku — adhu sari.
Aana neenga real-a kekkuradhu: *"Hampi advance pathi naan enga ezhudhirukken?"* Adhukku peru
search udhavadhu. Ippo naan **ullae** padikkiren: Word, Excel, PowerPoint, PDF, CSV, text.

Ovvoru answer-lum **aadhaaram** irukku:

> 2 match(es) for "hampi advance" — 2 file(s) contain those words:
>   1. budget.xlsx  [xlsx, 5 KB, line 3]
>      "Hampi advance 45000"
>      /home/you/Documents/budget.xlsx
>   2. hampi_notes.txt  [text, 99 B, line 2]
>      "Advance paid to the Hampi resort was 45000 rupees on 3 March."

File, **line number**, andha sentence, full path — neenga onnu paathu confirm pannalaam.
Score-a nambanum-nu naan solla maaten.

**Speed:** 4 documents = 14 ms. Rendadaavadhu = **0 files re-read, 0.3 ms** — size +
mtime remember pannirukken. Scan panna PDF (text layer illa)-vum remember pannirukken, so
adha ovvoru thadavam thirumba padikka maaten.

**Un file-a naan thoda maaten.** Read-only. Index oru JSON file, ARC-oda sontha folder-la.
`forget` sonna andha index matum poidum, un document pohaadhu. Test-la ovvoru file-oda
mtime-a snapshot eduthu proof pannirukken.

Scan panna PDF-a naan "no text layer" nu solluven — empty file nu nenachukka maaten.
`"index my documents with ocr"` nu sonna apparam image-um scan-um padikkum (ovvonnum ~1
second), adhu start pannradhukku munnadiye naan solluven.

---

## 1d. "Yen slow da?" — number-a cause-a maathi solluven

`system_report` number-a kaattum. Number-a paathu yaarukkum udhavi aagadhu. Ippo naan
number-a **kaaranam**-a maathi solluven — aana aadhaaram illama onnume solla maaten.

**Epdi:** **rendu sample, onnu-second gap.** Oru single `cpu_percent()` reading noise —
adhu peak pannina process ippo mudinjirukkalaam. So ellam **delta**, andha interval-la.

Example — real output shape:

> **Found 2 thing(s) actually slowing this PC.**
>
> Measured over 1.0 s just now: CPU 94% of 8 threads · RAM 7.7/8.0 GB (96%) · free disk 6.1 GB on C:>
> 1. **Memory is nearly full — that is the slow** (high)
>    measured: 7.7 of 8.0 GB used (96%), 0.3 GB left — biggest single app: chrome.exe at 3.0 GB
>    why: when Windows runs out of RAM it shuffles memory to disk…
>    do this: close chrome.exe (it alone holds 3.0 GB) · check the tray · reboot
>    ARC: say 'system report' for the live view of the same numbers.

**11 rules:** RAM pressure · pagefile thrash · oru CPU-hog process · whole-CPU load ·
drive full · disk throughput · startup bloat (registry, read-only) · process count ·
battery + load · thermal throttling · long uptime (heuristic — naan adha heuristic nu solluven).

**Grading:** **high** = idhu dhaan un slow · **medium** = tidy pannalam · **note** =
information, fault illa (300 processes = normal, adhu oru problem illa).

**Honest edges:**

- Temperature sensor illa na → *"I did not measure heat at all (not 'it is cool' — 'I cannot see it')"*.
- psutil illa na → **number-e kudukka maaten**, install command solluven.
- **Oru app-um naan kill panna maaten.** "chrome 3 GB hold pannirukku, naan adha kill panna
  maaten — 'close chrome' nu sonna naan mudhalla kekkuven" nu solluven. Setting, service,
  registry — onnume thoda maaten.
- Speed venum? `"pc_health quick"` → `CPU 1% · RAM 45% · disk 80% free · fine`

---

## 1e. Backup — copy panna mattum illa, **prove** pannuven

Idhu dhaan un #1 rule: *files never damaged*. Munnaadi naan file-a padikka mudiyum,
search panna mudiyum — aana **protect** panna mudiyala. Ippo mudiyum.

| Kelvi | Answer |
|---|---|
| Verify pannuma? | Ovvoru file-um copy aagum bodhu hash (SHA-256) edukkuven — source-a thirumba padikka thevai illa. Appuram destination-a thirumba hash panni compare pannuven. `verified: all N files matched` nu solluven — illa, match aagala-na andha file-oda **peru** solluven. |
| Overwrite aaguma? | Illa. Ovvoru run-um `ArcBackup-<timestamp>` nu **puthu folder**. Rendu run — rendu folder. Test adha prove pannudhu. |
| Un original-a thoduma? | Illa. Read-only open. Test-la ovvoru file-oda mtime + size-a snapshot eduthu compare pannirukken. |
| Enga refuse pannum? | Folder-a adhe folder-la copy (muttai muttai aagum), drive root, source illa, and **oru byte-um ezhudhaamale** "not enough room: 12 GB to copy, 4 GB free". |
| Pazhaya backup-a check pannalama? | `"verify the backup"` — manifest-oda compare pannuven. Oru file maarirundha, peru-oda solluven. |

## 1f. Autostart — neenga sonna mattum

Oru `HKCU` Run value (`ArcDesk`). No admin, no service, SYSTEM task illa. Ezhudhina
appuram **thirumba padichu** solluven — "enabled" nu sonna adhu registry-la irukkuradhu,
naan nenachadhu illa. Install move aana, `stale` nu solluven (velai seiyudhu nu poi
solla maaten). Task Manager-la maattu, inga off panna value poidum. **Neenga tick
pannalae illa na — off.**

## 1g. First run — anju kelvi, ovvonnum cost-oda

1. **Should I speak?** — OS voice, extra download illa.
2. **Should I listen?** — 60–150 MB daemon + live mic. Ctrl+Alt+Q eppovum quit.
3. **Should I start with you?** — ovvoru login-lum odum, neenga no sollum varaikkum.
4. **May I read your documents?** — Documents/Desktop/Downloads, read-only, oru thadavam.
5. **What thinks?** — local engine irundha adhu, illa na ARC Lite (offline, free).

Ellam `arcdesk/firstrun.py`-la apply aagum — adhe code-a voice command "start with
windows"-um use pannudhu. So checkbox-um vaai-um onnu dhaan.

## 1j. Vault — un work ellam enga pogum

Nee kettadhu: *"naan jarvis la work panra files, progress ellam enga save aagum? venum na
desktop-la save panikira mathiri irukanum."*

Ippo idhu oru folder dhaan — database illa, lock-in illa:

```
%APPDATA%\ArcDesk\vault\
    projects\belagavi-cafe-site\
        project.json      peru, dates, count
        notes.md          un notes (Notepad-la padikka mudiyum)
        progress.jsonl    ovvoru answer-um, time-oda
        files\            nee add panna files (copy — original anga dhaan irukkum)
```

| Nee kekkura kelvi | Naan enna seiven |
|---|---|
| "start a project called Cafe site" | project folder create panni, adhu dhaan current |
| "save this: homepage copy done" | `%APPDATA%\ArcDesk\vault\...\notes.md`-la ezhudhuven |
| "where do my files save?" | exact path solluven |
| "export this project to my desktop" | **puthu folder** `ArcVault-cafe-site-20261023-...`, file-by-file size check. Rendu thadava export panna rendu folder — merge aagadhu |
| "what was i doing?" | last 3 checkpoint + last note |
| "add C:\...\brief.docx to this project" | **copy** pannuven. Un original antha edathula dhaan, byte same |

Oru vishayam mukkiyam: **ovvoru answer-um automatic-a save aagum** (0.45 ms — andha alavukku
cheap). So "save pannalaye" nu oru naal-um aagadhu. Vault-a Settings-la vera drive-ku maathi
vidalam (pen drive, synced folder) — veetula irundhu office-ku kondu poga.

## 1k. Speed — ennoda answer evlo seekiram

Nee sonna: *"respond panra time seekiram irukanum, ans panrathuku romba time yeduka koodathu."*
So naan measure pannen, `python tools\speedcheck.py`:

| Enna | p50 | |
|---|---|---|
| Lite brain (offline, typed) | **0.28 ms** | 80 runs |
| Routing (88 tools-la irundhu sariyaana 3-a theruradhu) | **1.01 ms** | munnadi **75 ms** |
| Tool call (kanakku) | 0.01 ms | |
| Vault save (ovvoru answer-kum) | 0.45 ms | |

75 ms → 1 ms aana kaaranam: `select.py` ovvoru tool-kum tool description-a thirumba
tokenize pannidhu, synonym table-a 87 thadava scan pannidhu. Ippo oru thadava mattum. App
behaviour maara la — routing tests ellame same-a pass aagudhu.

**Naan solla koodadha unmai:** local LLM (0.5B) 2 CPU core-la *seconds* edukkum. Adhu
`tools\live.py`-la theriyum, inga illa. "Instant" nu solla maaten — Lite instant, model illa.

## 1l. One file, double click, ellame install aagum

Nee kettadhu: *"python, ffmpeg, nodejs ellam athuve download aagi install aagura mathiri
simple file ah kodu... double click pana direct ah successfully installed nu irukanum."*

```bat
packaging\build_all.bat        :: oru command, oru output file
-> dist\ArcDeskSetup.exe      :: adha double-click panna podhum
```

Adhu enna pannum: per-user install (**admin prompt illa**), Start Menu + shortcut, uninstaller,
"start with Windows" (nee tick panna mattum). Last screen: **"Arc Desk is installed
successfully."**

- **Python** thaniya venam — PyInstaller adha `ArcDesk.exe`-kulla already pottudhu.
- **ffmpeg** (195 MB, lzma2-la 58 MB) installer-la irukkum — video/audio ellam udane velai.
- **Node** optional component (MCP servers-ku mattum, default off) — size-a kammi-a vekka.
- PATH set panna thevai illa, registry-la edhuvum ezhudhadhu.

**Unmai:** andha `.exe`-a naan inga build panna mudiyaadhu (Linux, PyInstaller cross-compile
pannaadhu). Neenga Windows-la `packaging\build_all.bat` odina adhu varum. Adhu varaikkum naan
"exe ready" nu solla maaten — `tools\packaging.py` adha `UNVERIFIED` nu dhaan kaattum.

## 1o2. Build: naan ippo unmaiyaa build pannen — rendu real bug pidichadhu

Nee sonnadhu **"build the package"**. Intha sandbox Linux, PyInstaller Windows ku
cross-compile panna mudiyaadhu — so `ArcDeskSetup.exe` **inga build aagala**. Adhu unmai,
adha "mudinjadhu" nu sollamatten. Aana naan **adhe spec-a, adhe pre-flight-a** Linux-la
odi, bundle-a unmaiyaa build panni **odi paathen** — adhula rendu bug pidichadhu, adhu
Windows-la kooda build-a udachirukkum:

**Bug 1 — build-e nadakkaadhu.** `arcdesk.spec`-la `ROOT = Path(SPECPATH).parent` nu
**rendu thadava** parent eduthirundhadhu, so repo root-a vida onnu mela poi
`run.py`-a thedudhu:

```
ERROR: script '/home/user/run.py' not found
```

`build_all.bat` step 5-la Windows-lum **adhe** error dhaan vandhirukkum — "build works"
nu naan munnadi sonnadhu verify pannadhu dhaan. Ippo fix, mela `SystemExit`-la
"cannot find run.py next to packaging/" nu **puriyura message**-um irukku.

**Bug 2 — `--doctor` frozen app-la odadhu.** `ModuleNotFoundError: No module named
'doctor'` — `tools/doctor.py` bundle-la illa, `run.py` adha `__file__` pakkathula
thedudhu. README/INSTALL-la `--doctor` promise pannirukkom, Settings-la button-um irukku.
Ippo spec adha data-a bundle pannudhu, `run.py` `_MEIPASS`-la thedudhu.

**Bug 3 (silent-a irundhirukkum) — voice-a kill pannirukkum build.** `requirements-voice.txt`-la
`sherpa-onnx` **illa**. Adhu illama build pannina, "Teach ARC my voice" **ellaa machine-layum**
"engine missing" nu sollum — nee kettadhu angae theerndhu poidum. Ippo adhu requirements-la
irukku, `build_all.bat` rendu requirements file-um install pannudhu, `packaging.py`
**FAIL** pannum (build nikkum) library illa-na: *frozen EXE-la appuram pip install panna
mudiyaadhu*.

Adhoda oru **poi check**-um pidichadhu: packaging-la `if "startup" in iss: OK` nu oru
green line irundhadhu — edhuvum check pannala. Ippo `[Tasks]`-a unmaiyaa padikkudhu.

### Build numbers (measure pannadhu, guess illa)

| | |
|---|---|
| PyInstaller, rendu exe | **51 s** |
| Full build (`packaging/build_all.sh`), cold | **1 min 58 s** |
| Folder `dist/ArcDesk` | **298.5 MB** |
| LZMA2 compress panna | **86.4 MB (29 %)** |
| `ArcDesk --version` / `--doctor` / `--screenshot` | odinadhu, real UI render aachu |

### Windows Setup.exe eppadi vaangunadhu — rendu vazhi

1. **Windows machine-la:** `packaging\build_all.bat` → `dist\ArcDeskSetup.exe`
2. **Windows machine illa-na:** GitHub-la push → *Actions → "build windows installer" →
   Run workflow* → `ArcDeskSetup` artifact download pannunga. Anga Python, voice
   libraries, ffmpeg/node, PyInstaller, Inno Setup — **ellaam runner-la** install aagum,
   un laptop-la onnum illa.

## 1o4. `.exe`-a eppadi vaangardhu — intha machine-la mudiyadhu, aana vazhi ready

Nee kettadhu: *"complete windows la install panra .exe file ah kodu machi"*.

Unmai, appadiye: **intha sandbox Linux.** PyInstaller Windows EXE-a Linux-la irundhu
build panna **mudiyaadhu** — adhu oru setting illa, adhu PyInstaller-la illatha oru
vaaippu. Wine-um illa, Windows machine-um illa. So naan `.exe`-a create panni
"idhu vela seiyum" nu kuduthaa adhu **poi** aagum — adhu unakku venam.

Naan enna pannen: **adhe spec-a, adhe build script-a** Linux-la odi, bundle-a unmaiyaa
build panni, odi paathen. Adhula **moonu build bug** pidichadhu (spec-in ROOT, doctor
bundle, sherpa-onnx requirement) — avai Windows-la build pannumbodhu unna kill pannirukkum.
Ippo avai fix aagi, build clean-a odudhu.

### `.exe` vaanga — rendu vazhi, rendum ready

**Solli vachirukken:** naan GitHub-la push panna mudiyaadhu — intha chat-la GitHub
connector illa (`unsupported`). So antha rendu click nee dhaan pannaNum. Adhukku naan
ellathaiyum ready-a vachirukken: `arcdesk-src.zip`, `.github/workflows/build-windows.yml`,
`push_to_github.bat`, and `SETUP_GITHUB.md` (click-by-click, screenshot thevai illa).

**Vazhi 1 — GitHub Actions (Windows machine thevai illa, 5 nimisham):**

1. `arcdesk-src.zip` (17.6 MB) download pannu — nethi file, workspace-la irukku
2. GitHub-la pudhu repo create pannu (private-a irundhaalum sari)
3. zip-a unzip panni, andha files-a repo-la upload pannu (**`.github/workflows/` folder-um
   sethu** — adhu dhaan build-a odum)
4. Repo → **Actions** tab → *"build windows installer"* → **Run workflow**
5. ~10 nimisham kazhichu → artifact **`ArcDeskSetup`** download pannu
6. Adhu **`ArcDeskSetup.exe`** — double-click, no admin, no Python, no PATH

Anga GitHub-in Windows machine-la: 61 tests odum → rendu exe build aagum → frozen
`ArcDesk.exe --doctor` smoke test aagum → appuram dhaan artifact upload aagum. So
**odina build dhaan** un kaiyila varum, summa "build aachu" nu ila.

**Vazhi 2 — edhavadhu Windows laptop (5 nimisham):**

```bat
packaging\build_all.bat
```

Python 3.13 + internet irundhaal podhum; script dhaan PySide6, voice libraries,
ffmpeg, node, PyInstaller, Inno Setup-a pathukkum. Output: `dist\ArcDeskSetup.exe`.

### Naan kuduthirukkira files

| file | enna |
|---|---|
| `arcdesk-src.zip` (17.6 MB) | full source + workflow — unzip panni GitHub-la upload pannunga. Naan unzip panni odi paathen: `run.py --version` odudhu, `test_docs` PASS, `test_audit` ALL PASS |
| `.github/workflows/build-windows.yml` | Windows runner-la Setup.exe build pannum (zip-la ullae irukku) |
| `packaging/build_all.bat` | Windows-la oru command |
| `SETUP_GITHUB.md` | **click-by-click**: empty repo → upload → green tick → artifact download |
| `push_to_github.bat` | git irundha: `push_to_github.bat https://github.com/you/arcdesk.git` — push panni Actions link-a kattum |
| `BUILD_REPORT.md` | enna build aachu, enna udaindhadhu, enna unverified |

## 1o3. Cross-check: nee kettadhu ellam irukka? — ellathaiyum odi paathen

Nee sonnadhu: *"nan kettathu yellamay irukutha, settings correct ah irukutha, metaphor
correct ah irukutha, applications lan irukutha, all things enable ah iruka, files lan
iruka"*. Adhu oru vaartha kelvi illa — **60 measurement**. Adhaan `tests/test_audit.py`.
Summa "irukku" nu sollala; ovvonnukkum oru number.

### A. Settings — 28 control, ondrum dead illa

Code-a (AST) padichu, ovvoru control-um **rendu pakkam** vela seiyudha nu paathen:
load-la padikkudha (`_load`), melum **config-a ezhudura** method-la padikkudha. 28 value
control, 28-um sari. 13 checkbox-a onnaa toggle panni save pannen — onnum udaiyala.

**Bug pidichadhu:** `"effects"` nu oru setting `settings.json`-la irundhadhu — **aana adha
padikkira code onnum illa**. Neenga 0.0 nu vachaalum edhuvum nadakkaadhu. Ippo adhu
unmaiyaana feature: **Settings → System → Visual effects** (Follow the mode / Full /
Reduced / **Off — fastest**). Measure pannen: chill mode 1.00-la draw aagum, "Off" 0.00 —
appuram charms-um hide aagum (frame cost angae dhaan irundhadhu). Pazhaya laptop-la
speed venum-na idhu.

### B. Applications — 88 tool, ellam unmai

88 tool-um: description irukku, JSON schema sari, handler callable, registry key peru
match, platform restriction sari, **handler module import aagudhu**. Adhoda `TOOLS.md`-lum
in-app page-lum 88-um irukku. 0 duplicate.

### C. Enabled — enna on, enna off, rendum **kaaranam-oda**

On (18): shadow overlay, tray, hotkeys, magic mode, charms, vault, AI, voice, voice clone,
free-only guard, MCP, converse, barge-in, daemon autostart, battery saver, tray-on-close.

Off (5) — **verum onnu pannaadhu, kaaranam irukku**: wake word (mic-a nee kekkama
thirapadhu illa), voice lock (nee enrol pannanum), weather (network call nee kekkama illa),
nudges (interrupt nee kekkama illa), autostart (startup entry nee kekkama illa).

Ithula **rendu on panna oru click dhaan** — Settings → Voice → wake word, Settings →
Charms & weather → weather. Sollunga, default-a on aakiduven.

### D. Metaphor — ARC world-a appadiyae irukka

Naalu mode (`focus / chill / gaming / night`) — naalu **veru veru accent colour**
(#38bdf8 / #22d3ee / #f97316 / #f59e0b). HUD-la `CLICK CORE`, `ASK ARC`, `WAKE OFF`,
`READY` — ellam ippovum irukku. `hey jarvis` → ulagam thiramidhu; `bye jarvis` →
moodudhu; app odiye irundhu window-a maraikkalaam (stealth). Adhu dhaan metaphor — adhu
udaiyala.

### E. Files — 98 module, ellam import aagudhu, oru stub-um illa

`run.py`, `arc_daemon.py`, spec, iss, build_all.bat, moonu in-app page, requirements
rendum, check.bat — ellam irukku, onnum empty illa.

### Adhoda innoru real bug — backup

`crosscheck` pidichadhu: **400 KB backup-a "not enough room: 0.0 GB to copy, 0.2 GB free"
nu refuse pannudhu** — 200 MB free irundhaalum. Space guard 200 MB-a flat-a reserve
pannirundhadhu. Ippo copy-a vachikka mudiyaadha pothu mattum refuse pannum, MB-a MB nu
sollum ("0.0 GB" illa). Ithu un feature-a nambi vechirukkum idam — adhaan fix.

### Ippo ellam:

| | |
|---|---|
| `tests/run_all.py` | **72/72 pass** (88 s) |
| `tools/crosscheck.py` | **54 proven · 0 failed** · 4 need Windows hardware |
| `tools/packaging.py` | 72 checks · 0 failed |
| `gen_tools_doc --check` | 88 tools · 0 mismatch |

## 1p. First time-la "voice-a open panaNumaa, illa icon-a?" — kekkum, appuram maathikkalam

Nee kettadhu: *"first time set panum pothu voice la open pananuma illa desktop icon
double click panra mathiri venuma nu kekanum... future la maathanum na settings
application kulayum irukanum."*

**Adhu ippo nadakkudhu.** Oru kelvi, rendu badhil — rendumae unmaiyaana option:

| Option | Enna nadakkum | Enna cost |
|---|---|---|
| **Desktop icon** | Double-click pannina open aagum. Background-la onnum odadhu, mic open illa, startup entry illa | "hey jarvis" work aagaadhu (app open aana pirage mattum) |
| **Voice — "hey jarvis"** | ARC Windows-la start aagum, silent-a, mic open-a irukkum | Oru per-user startup entry + mic open (Ctrl+Alt+Q eppovum quit) |

Adhu **rendu switch illa, oru kelvi** — so "voice" select pannina mic **um** startup
entry **um** sethu set aagum; "icon" select pannina rendum off. (Andha logic
`firstrun.set_mode()`-la, test pannirukken.)

**Ippo edhuvum maathanum-na:** Settings → Voice → **"How ARC opens"** — adhe rendu
radio button. Maathi Save pannina, wake word udane stop/start aagum (restart vendaam).

**Machine ku kekka mudiyaadhu-na** (mic library / Vosk model illa): app "voice" select
pannina **icon ku downgrade** pannum, poi sollaadhu — "hey jarvis" work aagaadha oru
setup-a vida, unmai solla dhaan nalladhu.

**Installer-lum adhe kelvi** irukku (`How should it open?:`):

```text
[x] Put a shortcut on the Desktop (double-click to open)
[x] Start with Windows, silently, so "hey jarvis" always works
    (microphone stays off until you enable the wake word)
```

Appuram post-install-la oru checkbox: **"Download the speech models now (70 MB)"** —
Vosk 40 MB + speaker model 30 MB. Idhu illama puthu laptop-la "hey jarvis" work aagaadhu,
adhaan visible-a oru step-a vachirukken (silent download illa).

## 1q. En voice-a **eppo, eppadi** submit pannanum? Direct-a app-layae!

Nee kettadhu: *"enoda voice ah yepo submit pananum? yeppadi pananum? direct ah
application layae panalama?"* — **Aam, direct-a app-layae.** Terminal thevai illa:

**Settings → Voice → "Teach ARC my voice…"**

1. "Record take 1" → **4 second** edhavadhu vaarthai pesunga (vaarthai mukkiyam illa,
   kural dhaan)
2. Level bar odum — mic work aagudha nu **udane** theriyum
3. Adhe maadhiri take 2, take 3 (total ~12 second)
4. Moonu take-um onnaa poruntha "the three takes agree" nu sollum
5. **"Only my voice may command ARC on this computer"** checkbox → tick → Done

**Eppo?** Thaniyaa irukkumbodhu, quiet room-la, **oru thadava** mattum. Appuram
Settings-la eppo venum-na **off** pannalam (adhe checkbox) — un voice-a mattum illa,
yaaraiyum illa.

**Mic illa-na** (sounddevice install aagala): "Use a WAV file…" button irukku — mundhina
recording-a select pannunga. Onnum illa-na app **sollum**, summa "ready" nu nadikkaadhu.

**Unmai (oru thadava sollitten):** idhu **convenience filter**, security illa. Family, TV,
YouTube — thadukkum. Un voice-a phone-la record panni play pannina thadukkaadhu.

**Naan unmaiyaa odi paathen** (real model, real audio, intha sandbox-la):

```
SELF-TEST with 7.8 s of this voice
  three takes enrolled      : yes (3)
  they agree                : 0.55
  held-out take (same voice): PASS  score 0.70 (needs 0.62)
  another voice (other16.wav): correctly REJECTED  score 0.16
```

Adhu `python tools\voice_setup.py selftest --against other.wav` — unga machine-la
neengalum odalam.

## 1o. Vera laptop-la install pannalaama? Anga vera voice-la?

**Rendum aam.** Rendu vaeru vaeru vishayam, so rendu vaeru vaeru step.

```bat
:: 1. oru Windows machine-la build pannunga (inda Linux-la mudiyadhu)
packaging\build_all.bat   ->   dist\ArcDeskSetup.exe

:: 2. un data-a kondu ponga
python tools\move.py pack D:\arcdesk-carry.zip      :: inga
python tools\move.py unpack D:\arcdesk-carry.zip    :: anga install pannadhum
```

| Enna pōgum | Enna pōgaadhu (vēraa irukkum) |
|---|---|
| `vault/` — projects, notes, progress | `voiceid/` — **voice lock machine-ku machine** |
| `voice/` — clone reference + transcript | `models/` — 1.5–2 GB, anga download aagum |
| `settings.json` — **API key strip aagum** (`--with-keys` venum-na) | `logs/`, caches, file index |

**Anga vera voice-la:**
```bat
:: laptop B-la, avanga voice-la mattum
python tools\voice_setup.py lock-enroll \<peru\> r1.wav r2.wav r3.wav
```
`voiceid/` package-la **illai** — adhu vēraa. So laptop A-va B thadukkaadhu, B-va A
thadukkaadhu. Clone voice venum-na B-la antha aalu clip-a `import` pannunga.

**Unmai (maraikkala):** `ArcDeskSetup.exe`-a naan inga irundhu build panna mudiyadhu —
PyInstaller cross-compile pannaadhu. Adhu Windows step; `tools\packaging.py` adha
`UNVERIFIED` nu dhaan kaattum. Vera ellam (data, voice, models) inga test pannirukken.

## 1n. Un kural-la pesanum, un kural-la mattum kēkkanum

Rendu vēru vēru vishayam, rendu vēru vēru theervu:

| Nee kēttadhu | Ippo enna aagum | Enga |
|---|---|---|
| "reply en voice-la varanum" | **voice clone** — un 10 s clip-la irundhu tone-a copy pannum local model | `arcdesk/clone.py` |
| "naan enna language-la pesunalum antha language-la reply" | ithu already irukku — `lang.py` un vaarthaiya paathu language mudivu pannum | `arcdesk/lang.py` |
| "intha laptop-la en voice-la mattum work aaganum" | **voice lock** — un kural-in fingerprint, intha machine-la mattum enroll | `arcdesk/voiceid.py` |
| "vera laptop-la vera person voice" | profile machine-ku machine, so laptop B kālīya start aagum | `arcdesk/voiceid.py` |

```bat
python tools\voice_setup.py import "C:\path\clip.mp4"   :: reference clip ready
python tools\voice_setup.py try "vanakkam macha"          :: try panni paarunga
python tools\voice_setup.py lock-enroll me r1.wav r2.wav r3.wav
python tools\voice_setup.py lock-test r4.wav
python tools\voice_setup.py lock-on
```

**Scope (nee sonnadhu): Tamil, Hindi, English — adhu dhaan contract.**

```python
PROMISED = {"ta": "indicf5", "hi": "indicf5", "en": "xtts"}
```

Adhu code-la irukku (`tests/test_clean.py` adha check pannum). Matra 9 Indic + 16 XTTS
languages **bonus** — work aagum, aana naan claim panna maaten.

**Clip nalladha nu ippo number-la theriyum** (`clone.analyse()`):

| grade | artham | enna panna |
|---|---|---|
| `good` | SNR ≥ 25 dB, 8–20 s, clipping illa | clone pannunga |
| `short` | clean, aana 8 s-ku kammi | **un 4.55 s + 5.88 s clip rendum idhu** — innum konjam venum |
| `workable` | SNR 15–25 dB | `clean_voice.py` odunga |
| `poor` | noisy / clipped | marupadiyum record pannunga |

```bat
python tools\clean_voice.py "clip.mp3" --import --transcript "antha clip-la pesinadhu"
```

Adhu 50 Hz hum + fan noise + hiss-a kammi pannum, appuram **marupadiyum measure** pannum.
Naan 50 Hz hum test clip-la odi paathen: **SNR 12.2 → 20.6 dB, grade poor → workable**.

**Unmai, oru thadava sollitten:**

1. **Tamil + un cloned voice = IndicF5** venum. XTTS Tamil pesaadhu (Chatterbox-um
   illa). IndicF5 install illa-na, ARC Tamil-a Piper voice-la pesum — **vēru voice,
   aana unmaiyaana Tamil**. Un English clone voice-a vachu Tamil kēvalama pesaadhu.
2. **IndicF5-ku GPU venum** — CPU-la work aagum, aana slow. Adha naan maraikkala.
3. **Un clip-la music irundha, clone-la music-um varum.** Adhaan `import` clip-a
   VAD-la trim pannum, loudness normalise pannum, cuts irundha thaiyal (stitch) pannum.
4. **Voice lock = convenience, security illa.** Family, TV, YouTube video — ivai
   thadukkum. Aana un voice-a phone-la record panni play panna, adhu thadukkaadhu.
   Edhuvum illa-na app **sollum** — "lock irukku" nu poi sollaadhu.
5. **Licence:** XTTS-v2 CPML = personal/non-commercial mattum. IndicF5 code MIT, aana
   *"clone only voices you have permission to use"*. Un voice, illa sammatham kudutha
   aalu — not a film star.

## 1m. "Ithu real elephant madhiri illa" — unmaiyaana photo

Nee sonnadhu: *"nethu elephant draw pannuchu, real elephant picture-oda evlo different iruku...
apadiyae irukanum, realistic ah."* Correct-a sonna — **adhu drawing, photo illa**. Naan
`draw`-la innum nalla varainja kooda adhu padam aagadhu. Adhaan unmai.

Ippo moonu vaasal, ovvondrum unmaiyaa enna kudukkudhu nu theriyum:

| Nee kekkuradhu | Enna varum | Enna venum |
|---|---|---|
| **"real photo of an elephant"** | **unmaiyaana photo** — oru manushan eduthadhu, free licence | internet, ~1 second, GPU illa |
| "make an image of an elephant" | generate aana image | local diffusion (ComfyUI/A1111) + 4–8 GB VRAM |
| "draw an elephant" | vector sketch (cartoon) | onnum illa, offline, instant |

`photo` tool (`arcdesk/photo.py`) Wikimedia Commons-a kekkum — **key illa, account illa,
kaasu illa, upload illa**. Ovvoru answer-um **yaaru eduthadhu + enna licence + source link**
sollum:

```
real photograph of african elephant: C:\Users\you\Pictures\ArcPhotos\african_elephant_….jpg
(1600×1067, 1132 KB) — Desert elephant (Loxodonta africana) spraying sand.jpg
by Charles J. Sharp, CC BY-SA 4.0. Source: https://commons.wikimedia.org/wiki/File:…
```

Naan unmaiyaa oru real elephant photo download panni paarthen — Charles J. Sharp-oda
"Desert elephant spraying sand", CC BY-SA 4.0. Adhu un sketch-oda compare panna unmaiyaana
photo. Ippo "real photo of an elephant" nu sonna adhu dhaan varum.

Edhuvum ozhunga illaadha pothu:
- **net illa** → "no internet for photo search" nu oru sentence, traceback illa.
- **onnum kidaikala** → "try other words" nu sollum, summa edhuvum kaattadhu.
- **download photo illa** (`<html>` error page) → refuse pannum, `elephant.jpg` nu poi save pannaadhu.
- **pazhaya file** mela ezhudhadhu — `…_v2.jpg` nu puthu file.
- **CC0 / public domain** preference — appuram nee adha use panna easy.

Chinna vishayam: `aane photo`, `haathi photo` nu sonnalum work aagum — drawing engine-oda
Tamil/Hindi peru table-a reuse pannuven, Commons-la "aane" nu thedamaaten.

## 1i. "BYE JARVIS" — app close aaguma? Ippo aam

Nee sonna vaarthai: *"antha application voice command la open and close aaganum"*. Naan
cross-check pannen — **open** sari, aana **close** half-true-a irundhuchu:

| Munnadi | Ippo |
|---|---|
| "bye jarvis" → magic mode poidum, aana **app odikondirukkum** (default `hide`) | default `exit` — process unmaiyaa **mudiyum** (`taskkill` illa, normal-a quit aagum) |
| magic mode off-a irundha "bye jarvis" → "*magic mode active illa*" nu oru note mattum. Onnum close aagala | ippo eppovum maayum — magic on-a irundhalum illa |
| Close panna pinnaadi edhuvum kekala (sounddevice illa, engine illa) → tirumba "hey jarvis" solli open panna mudiyaadhu | close panna munnadi **launcher 1.5 second uyiroda irukkaa** nu paakkuven. Illa na **app-a close panna maaten** — open-a vechu, "yen" nu solluven |

Settings → **On "BYE JARVIS"** la moonu choice:
1. **Close the app — launcher keeps listening** (default) — "hey jarvis" solli tirumba vara mudiyum
2. **Close the app — nothing stays behind** — complete-a close, shortcut-la tirumba open pannu
3. **Hide to background** — window maayum, tray-la irukkum

Naan eppovum **silence-la vidamaaten**: oru process-um un kural-a kekka mudiyaadha nilaiyil naan
unna moonu padi-yila niruthi "close aagala, ithu kaaranam" nu solluven.

Proof (real app, real protocol, no mic needed):

```
python tools\voice_roundtrip.py     ->  BYE JARVIS closes it: process exit 0
python tools\crosscheck.py          ->  15 present · 42 proven · 0 failed · 4 unprovable
```

## 1h. "Build panna mudiyuma?" — aamaa, ippo unmaiyaa

Munnadi README-la `packaging\build.bat` nu ezhudhi irundhuchu. Aana antha file **illave
illai**. Adhu oru poi — naan seidha thappu. Ippo:

| Munnadi | Ippo |
|---|---|
| spec file illa | `packaging/arcdesk.spec` — `collect_submodules("arcdesk")`, so pudhu module-a marakka mudiyaadhu |
| build script illa | `packaging/build.bat` — five steps, first problem-la nikkum |
| installer illa | `packaging/arcdesk.iss` — per-user, **admin prompt illa**, service illa, notes-a delete panna munnadi kekkum |
| icon illa | `shots/arc_icon.ico` — naan draw pannen (`tools/make_icon.py`), 7 sizes |
| 88 tools-a patthi oru list-um illa | `TOOLS.md` + `arcdesk/TOOLS_PAGE.html` — registry-la irundhu generate aagum, search panna mudiyum, offline velai seiyum |
| `run.py --shadow`-a yaarum run pannadhillai | `tools/smoke_firstrun.py` — unmaiyaa boot panni, settings ezhudhina-a paathu, stop signal anuppi, clean exit 0 nu confirm pannudhu |

**Ippo naan solla koodiya unmai:** `tools\packaging.py` → `checked 35 · needs windows 3 ·
failed 0`. Antha 3 row `UNVERIFIED` — PyInstaller Linux-la Windows exe-a build panna
mudiyaadhu. So "exe sariyaa odudhu" nu naan solla maaten. Neenga Windows-la
`packaging\build.bat` odina adhu theriyum, adhu varaikkum adhu **build aagala**.

Oru vishayam ithula kandupidichadhu: uninstall.bat-la `taskkill /IM pythonw.exe /F` irundhuchu
— adhu un machine-la irukkura **ellaa** Python app-um kollum (Jupyter, un scripts). Adhu
ippo illa. Idhu dhaan "your machine is never damaged" nu sonna vaarthai-oda artham.

---

## 2. Naan "I don't know" nu sollum bodhu, adhu failure illa — adhu feature

Idhu dhaan un main rule: **"assume pana koodathu. correct ah sollanum."** Adhu code-la
indha maadhiri irukku:

| Rung | Enna nadakkum | Example |
|---|---|---|
| 1. En kitta local source irukku | Number + **source + year** | "Everest 8,848.86 m (Nepal + China, 2020)" |
| 2. Number maarikitte irukku | Year illama solla maaten | "India population ~1.45 billion (2024 estimate) — indha number maarum" |
| 3. Naan compute panren | Arithmetic-ah solluven, prophecy-ah illa | "Straight-line fit 1,168.87 — idhu arithmetic, forecast illa" |
| 4. Theriyala | **"I do not know"** + enna panna mudiyum | live event → Wikipedia link, or "scan pannu" |

Adhu wave-5-layum irukku:

- **Time estimates** — measured, illa "rough" nu label. "started in 6 ms" nu sonna, adhu
  stopwatch-la irundhu vandhadhu.
- **Coach** — ovvoru answer-lum `(framework, not a prophecy)` illa
  `confidence: high on frame, unknown on your situation`.
- **Journal** — "3 of 7 days heavy" nu sonna, adhu unga real entries-la irundhu count
  pannadhu. Oru entry-um illa na: "nothing to count yet" — pattern invent panna maaten.

---

## 3. Naan **panna maaten** nu solla vendiyadhu

Idhu ellam code-la refuse aagum, manasu maara maaten:

- Diagnosis — "nee depression-la irukka" nu naan solla maaten. Naaru doctor illa.
- "Guaranteed return" / "idhu 100% work aagum" — naan solla maaten, yaarum solla koodadhu.
- Forgotten password crack, neighbour wifi, "access anything anywhere" — illa. `REFUSED.md`-la
  ellam irukku, lawful substitute-oda.
- Un file-a overwrite panna maaten. Edit panna **pudhu file** dhaan, pazhaya file-oda
  mtime kooda thoda maaten.
- Un disk-la irukkurathu unakku. Index read-only, media_index.json file naan en data folder-la
  dhaan ezhudhuven.

---

## 4. Crisis-na, advice illa — number dhaan

Neenga "I want to die" / "self harm" nu sonna, naan oru productivity tip kudukka maaten.
Udane idhu varum:

- **Tele-MANAS 14416**
- **KIRAN 1800-599-0019**
- **112** (emergency) · **988** (US) · **116 123** (UK)

Plus oru line: *"I am software, not a clinician."* Adhu oru legal disclaimer illa —
adhu unakku unmai.

---

## 5. Idhu real-a epdi irukkum (verbatim, code-la irundhu)

**Neenga:** "machi i feel low da, business varala, romba tension"

**ARC:**
> That sounds like a lot of pressure to carry, and anxiety is a normal response to
> uncertainty — not a character flaw.
>
> One question, not five: what would make tomorrow feel 10% lighter — not perfect, just lighter?
>
> If you cannot answer that, the honest next step is not advice: it is water, food, or sleep. Any order.
>
> Machi, neenga solradhu puriyudhu — dheiriyama irunga.

**Neenga:** "shall i take a loan for the new kitchen or wait"

**ARC** (short version — full answer-la scoring table-um pre-mortem-um irukku):
> **1. Is it reversible?** … One-way doors deserve the slow treatment.
> **2. What are you actually optimising for?** Pick the top two. Six is how decisions die.
> **3. What is the cost of not deciding?** Doing nothing is also a choice, and it is usually
> the most expensive one.
>
> *(My confidence in this frame: high. My confidence about your specific situation: unknown —
> I have only what you told me.)*

**Neenga:** "scan my external disk and play kabira"

**ARC:**
> Plan (2 steps):
>   1. scanning the external disk, read-only  [library roots=E:\]
>   2. finding and playing "kabira"  [play query=kabira]
>
> ✓ 1. Scanned 4,612 folders in 6.4 s — indexed 1,908 media files…
> ✓ 2. ▶ Kabira — playing in mpv · started in 41 ms

---

## 6. Epdi pesanum

Naan kekkuradhu easy dhaan — Tanglish, English, Tamil, mix — ellam.

- `"song podu"` · `"paatu podu anirudh"` · `"play ilaya nila"` · `"video hampi trip podu"`
- `"stop the music"` · `"next song"` · `"what is playing now"`
- `"scan my external disk"` · `"scan e drive"` · `"what songs do i have"` · `"do i have a song called nee"`
- `"help me decide whether to raise prices"` · `"mentor me on direct bookings"`
- `"i feel low today"` · `"romba stress da"` · `"journal this: today was heavy"`
- `"give me a plan for the next 7 days"` · `"check in with me"`
- `"back up my documents"` · `"back up my pictures to D:\Backups"` · `"verify the backup"` · `"which disks can i back up to"`
- `"start with windows"` · `"stop starting with windows"`
- `"why is my laptop slow"` · `"yen slow da"` · `"my laptop is heating up"` · `"startup items"` · `"pc health quick"`
- `"index my documents"` · `"which file mentions the hampi advance"` · `"where did i write about the rooftop cafe"` · `"forget my document index"`
- `"idhu enna error da"` · `"what is this error on my screen"` · `"explain this error"` · `"why did it crash"`

---

## The four honesty rules (English)

1. **A number that moves carries its year.** No year, no number.
2. **Measured is not estimated.** Timing, counts and sizes come from the run, or they are
   labelled `rough`.
3. **A guess is called a guess**, every time it is a guess.
4. **"I do not know"** is a complete answer, and it comes with the next step.

Everything on this page is enforced by `tests/test_coach.py`, `tests/test_screenhelp.py`,
`tests/test_world.py`, `tests/test_playback.py`, `tests/test_inside.py`, `tests/test_pchealth.py`,
`tests/test_cinematic.py`, `tests/test_quiet.py`, `tests/test_windows_build.py`, `tests/test_spec_exec.py` and `tests/test_docs.py` — 72 tests, one command:
`python tests/run_all.py`.
