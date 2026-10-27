# One JARVIS, one folder

The complaint this file answers: *"multiple files lan ilama ... orey folder ah irukanum
... vera vera files, places la irukurathu nala confuse aaguthu"* — and the honest reason it
happened: every fix pack was unzipped as its **own** folder, next to the app instead of on
top of it. Six downloads, six folders, and no way to tell which one opens.

## The shape of the folder

Only three things must be at the **top**:

```
JARVIS\
  run.py                 <- the app
  requirements.txt
  JARVIS.bat             <- the only thing you double-click
  arcdesk\               <- the code (folders inside folders, that is fine)
  tools\
  packaging\
  tests\
  *.md                   <- the docs
  .venv\                 <- your Python environment (created on first run)
```

A folder is a working copy of JARVIS when `run.py` **and** `requirements.txt` are in the
same place. That is the check `tools/one_place.py` and the launcher both use, so they never
disagree.

## What must NOT be inside it

* an unzipped fix pack folder (`arcdesk-fix42-.../`) — it is not the app, it is a few files
  that belong *on top of* the app;
* `Downloads\JARVIS-OLD\` copies you forgot about;
* `.venv` copied from another machine.

## How to know which files are the correct ones

Three checks, in this order. The first two you can do by eye; the third is the one that
settles it, and the tool does it for you.

**1. The top of the folder must look like this** — `run.py`, `requirements.txt`,
`JARVIS.bat`, and the folders `arcdesk`, `tools`, `packaging`, `tests`. If a folder has
`FIXPACK.txt` or `arcdesk-fixNN-` in its name, it is **not** the app: it is a few changed
files that belong on top of the app.

**2. It must have a `.venv` that was actually built there** — `.venv\Scripts\python.exe`.
A copy without one has never run on this machine; its first start would take 2–4 minutes.

**3. Ask the app that is running right now.** This is not a guess: JARVIS knows its own
path, and the tool reads it.

```bat
.venv\Scripts\python.exe tools\jarvis_state.py --where
:: C:\Users\emera\Downloads\JARVIS\arcdesk-src
.venv\Scripts\python.exe tools\one_place.py --report "%USERPROFILE%\Desktop\JARVIS-SCAN.txt"
```

`--where` prints the folder whose `run.py` the running process is executing. That folder is
the correct one — every other copy is history.

The version tells you how old a copy is, without opening it:

```bat
.venv\Scripts\python.exe tools\one_place.py
::   ...\arcdesk-src            <-- keep this one
::      RUNNING NOW · version 0.1.0 · environment: yes
::   ...\arcdesk-fix38-copy
::      version 0.1.0 · environment: none yet
```

And to prove the keeper really runs, rather than trusting the folder listing:

```bat
.venv\Scripts\python.exe tools\one_place.py --apply --verify
::   verify C:\Users\emera\JARVIS
::     run.py + requirements.txt : yes
::     the arcdesk package      : yes
::     its own environment      : yes
::     import arcdesk           : 0.1.0
```

## The shortest route for you

1. Start JARVIS once (double-click `JARVIS.bat` wherever it is now) — so there is a running
   copy to point at.
2. Double-click **`ONE-PLACE.bat`** (in the same folder).
3. Read the list it prints — it marks `RUNNING NOW` and `<-- keep this one`.
4. Answer **Y**.

That is it. It parks the other copies in `%USERPROFILE%\JARVIS-OLD`, copies the keeper to
`%USERPROFILE%\JARVIS` (or moves it, when it is not the folder you are running from),
proves the result runs, and prints the one file to double-click from then on:

```
C:\Users\emera\JARVIS\JARVIS.bat
```

If the keeper was the copy you were running from, it is **copied**, not moved — a folder
being yanked from under a running process is exactly how "it stopped opening" happens. The
new folder builds its own `.venv` on first start (2–4 minutes, once); the old one can be
deleted by hand when you are happy, or parked by running `ONE-PLACE.bat` again from the new
place.

## Switching to a clean copy without losing anything

A user asked the obvious question: *"existing files and folders delete pannitu itha matum
keep pannikalama?"* — yes, in this order:

1. Unzip the new copy somewhere permanent (`%USERPROFILE%\JARVIS`), run **`JARVIS.bat`**
   once, and let it finish. Do not touch the old folder yet.
2. When the window opens and the voice works, drop the old folder onto
   **`CHECK-BEFORE-DELETE.bat`** (or double-click it and type the path).
3. It prints what survives the folder (`%APPDATA%\ArcDesk`: settings, voice clip, vault),
   what is really inside the old folder (the voice engines hidden in its `.venv`, any file
   that is not part of JARVIS), and asks one question.
4. Type **R**. It **renames** the old folder to `JARVIS-OLD` next to itself. Nothing is
   deleted, ever — you delete that folder later, or never.

`tests/test_check_before_delete.py` keeps the rules: it never deletes, it refuses the
folder this file lives in, a folder that contains it, a drive root, and anything that is
not JARVIS — and only a typed **R** reaches the rename.

Why rename and not delete: a rename is reversible in one click, and it is the only honest
way to answer "did I need anything in there?" *after* the new copy has proved itself.

Why the order matters: the `.venv` inside the old folder is the only thing a delete really
costs. Voice **weights** are in `%APPDATA%\ArcDesk\voices`, so they are never re-downloaded
— only the packages are re-installed (one click in Settings → Voice, first start installs
the rest).

## Tidy it up in one command

```bat
.venv\Scripts\python.exe tools\one_place.py            :: look, change nothing
.venv\Scripts\python.exe tools\one_place.py --apply    :: keep ONE at %USERPROFILE%\JARVIS
.venv\Scripts\python.exe tools\one_place.py --undo     :: put them back
```

`--apply`:

1. finds every folder that really is the app (deep: `Downloads\JARVIS\arcdesk-src` is
   found, a fix-pack folder is not);
2. picks the one to keep — a copy already at `C:\Users\<you>\JARVIS` wins, otherwise the
   one with a working `.venv`, then the newest;
3. moves that one to `C:\Users\<you>\JARVIS`;
4. moves every other copy to `C:\Users\<you>\JARVIS-OLD\<name>` and writes a manifest, so
   `--undo` restores the exact paths;
5. prints the one file to double-click from then on.

It **never deletes**, and it refuses to move the copy it is running from (that would be a
disappearance, not a tidy-up) unless you pass `--force`.

## From then on

```
C:\Users\<you>\JARVIS\JARVIS.bat        <- the one you double-click
```

Nothing else needs clicking: updates are `UPDATE-JARVIS.bat` in the same folder, and the
launcher looks in `C:\Users\<you>\JARVIS` first, so it still works if the folder is moved
again.

## Putting it on GitHub (the files that "do not upload")

GitHub Desktop uploads a **folder**, not single files, and it skips anything in
`.gitignore` on purpose — for this project that means `.venv\`, `__pycache__\`, `dist\`,
`runtime\` and `.failures\`. Those are not missing, they are meant to stay on your machine.

So the correct upload is: point GitHub Desktop at `C:\Users\<you>\JARVIS` (the folder with
`run.py` in it) and let it take everything. Then, on github.com, the root of the repo shows
`run.py`, `requirements.txt`, `JARVIS.bat`, `arcdesk/`, `tools/` — the same picture as the
tree above. `arcdesk/*.py` showing up but nothing else usually means the repository was
initialised *inside* a subfolder, or the other files were never committed:

```bat
cd C:\Users\<you>\JARVIS
git status                 :: what is untracked
git add -A
git commit -m "the whole app"
git push
```
