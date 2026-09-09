# Mantella + xVASynth on Linux (Debian) — Debugging Notes

Living notes on the non-obvious fixes needed to get Mantella (running natively
on Linux) talking to xVASynth (ported from an officially Windows-only app) for
Skyrim SE, running via Steam Proton + Mod Organizer 2. Read this before
re-debugging something that's already been solved once.

## Architecture

- **Skyrim SE**: real Steam install (appid 489830), downgraded to **1.6.1170**
  (see "SKSE address-library break" below). Actual gameplay always launches
  through the MO2 Proton prefix (`compatdata/4199706055`), NOT 489830's own
  prefix — 489830 itself is left running an untouched vanilla copy.
- **MO2**: portable instance at
  `compatdata/4199706055/pfx/drive_c/Modding/MO2`. Two Steam library
  shortcuts point at the same `ModOrganizer.exe`: "Mod Organizer" (normal GUI)
  and "Skyrim SE (modded)" (silent `moshortcut://SKSE` launch). Both use
  `/home/allan/Games/Mantella/game-wrapper.sh` as their Launch Options target
  (see "Steam Launch Options" below).
- **Mantella backend**: runs from source at `~/Games/Mantella`, NOT the
  bundled Windows exe in the MO2 mod folder. Python 3.11 venv
  (`MantellaEnv`), managed via `uv`. Started/stopped by `game-wrapper.sh`.
  Web UI: `http://localhost:4999/ui` (auto-launch disabled, see config).
- **xVASynth backend**: the actual voice synthesis server. We do **not** run
  the Steam-installed Windows exe. Instead we run the plain Python
  `server.py` that ships alongside it (`.../xVASynth/resources/app/server.py`)
  using a separately-built Linux venv at `~/Games/xVASynth/src/xVAEnv`
  (Python 3.9 — forced by torch 1.9.0's wheel availability). Listens on
  `127.0.0.1:8008`. Voice models live in the Steam install's own
  `resources/app/models/skyrim/` (downloaded via the real xVASynth GUI app's
  "Get More Voices" feature, running via Proton — that part works fine
  as-is, only the *serving* backend was switched to native Linux).
- Config file: `~/Documents/My Games/Mantella/config.ini` (Mantella's
  "custom user folder" default — this is on the **host**, not inside any
  Proton prefix, since Mantella runs natively).

## Recurring gotchas (seen more than once — check these FIRST)

1. **Config values silently reset to defaults.** Multiple settings
   (`game`, `xvasynth_folder`, possibly others) have independently reverted
   to their Windows defaults at different points, with no edit from us.
   Root cause pattern found so far: broken validators that do Windows-style
   path checks (see #2) — when a validator throws/fails, Mantella seems to
   silently fall back to defaults for that value (and possibly others in the
   same category). **Always grep the relevant `*_definitions.py` file for
   hardcoded `\\` backslash path checks before trusting a "some setting
   reset itself" report.**

2. **Hardcoded Windows path checks in config validators.** Found and fixed
   one in `src/config/definitions/tts_definitions.py`
   (`ResourceFolderExistsChecker.apply_constraint`): it did
   `os.path.exists(f"{path}\\resources\\")` — a literal backslash, which
   never matches on Linux regardless of how correct the path is. Patched to
   `os.path.join(path, "resources")`. **If another config category
   mysteriously resets, search `src/config/definitions/*.py` for `\\` and
   apply the same fix.**

3. **CRLF line endings in config.ini break exact string matches.**
   Mantella's own config-writing code emits Windows line endings. At least
   once, a value like `game = Skyrim` was actually stored as `Skyrim\r`
   (trailing carriage return), which fails an exact-match comparison
   against the literal string `"Skyrim"` and silently falls through to a
   default. Fix applied: `sed -i 's/\r$//' config.ini` to strip all CRLF. If
   Mantella rewrites the file (e.g. via its own save-on-exit or UI), this
   can come back — re-check with `cat -A config.ini | grep '\^M'` if a
   setting seems to be "not sticking."

4. **`pgrep -f` self-matching false positives.** Any script that does
   `pgrep -f "<pattern>"` to check "is X already running" can match *its own
   command line* if that same pattern text appears elsewhere in the
   invocation (e.g., a later `pkill -f "<same pattern>"` in the same Launch
   Options string). This caused real bugs: `start-mantella.sh`'s "already
   running" check kept matching the launcher's own `pkill` argument text and
   skipping the actual start. **Fixed by switching to a PID-file based
   check** (write PID on start, `kill -0 $(cat pidfile)` to check) instead
   of text matching. If you add new "is it running" logic anywhere in this
   setup, use a PID file, not `pgrep -f`.

5. **The `mantella.pid` file goes stale easily.** Because of the above
   fragility and because processes sometimes get killed by things other
   than our own scripts (or `kill` targets a PID that's already gone), the
   PID file often doesn't match the actual running process. When in doubt:
   `ps aux | grep "MantellaEnv/bin/python main.py" | grep -v grep` and
   `ss -ltnp | grep 4999` are the ground truth, not the pid file.

6. **A leading `pkill ... ; true` (or `|| true`) at the start of a
   multi-line Bash tool call sometimes aborts the whole block with exit
   code 1 and zero output**, even with `|| true` appended, if pkill finds
   nothing to kill. Symptom: the tool reports "Exit code 1" with no output
   at all, and none of the subsequent commands ran. Workaround: run the
   `pkill` as its own separate tool call, then run the actual
   start/verification commands in a follow-up call.

## Steam / Flatpak specific issues

7. **Steam (Flatpak) sandboxes filesystem access.** Scripts/binaries living
   outside Steam's own `~/.var/app/com.valvesoftware.Steam/...` tree (e.g.
   our `~/Games/Mantella/game-wrapper.sh`) are **not visible to processes
   Steam launches** unless explicitly granted. This caused Launch-Options
   scripts to silently fail to even start (not even the first line of the
   script ran — confirmed by adding a canary `echo >> /tmp/...` as the very
   first line and seeing it never appear). Fixed with:
   ```
   flatpak override --user --filesystem=/home/allan/Games com.valvesoftware.Steam
   flatpak override --user --filesystem=/home/allan/.local/share/uv com.valvesoftware.Steam
   ```
   (the second one is needed because `uv`-managed Python installs are
   symlinks pointing into `~/.local/share/uv/python/...`, which also needs
   to be visible). **Requires a full Steam restart to take effect** — a
   granted override doesn't apply to an already-running Steam process.

8. **Non-Steam shortcut `exe`/`icon` paths added via Steam's own file-picker
   dialog get a Flatpak portal path** like
   `/run/user/1000/doc/<hash>/filename`, not a real filesystem path. These
   can become stale/unreliable. We fixed this by directly editing
   `~/.var/app/com.valvesoftware.Steam/.local/share/Steam/userdata/<id>/config/shortcuts.vdf`
   with the `vdf` Python library (`uv run --with vdf python3 -c "..."`) to
   set `exe`/`StartDir`/`icon` to real absolute paths. **This edit does not
   reliably survive** — Steam has re-reverted the "Mod Organizer" shortcut's
   `exe` back to the stale portal/installer path at least twice with no
   action from us, seemingly from its own periodic in-memory-to-disk
   flush. If a shortcut "points at the installer again" or similar, just
   re-run the same vdf-editing fix; there's no known permanent fix, only
   reapply as needed. Any `shortcuts.vdf` edit needs a full Steam restart to
   load.

9. **Steam's non-Steam-shortcut `appid` can get reset.** Directly
   round-tripping `shortcuts.vdf` through the `vdf` Python library once
   corrupted the `appid` field to `0` for one shortcut, which Steam then
   "sanitized" by assigning a brand new appid on next launch — which means a
   **brand new, empty Proton prefix** gets used instead of the one you
   configured, silently losing all prior Proton-side setup (winetricks
   fixes, MO2 install, etc.) for that shortcut. The `appid` field is stored
   as a **signed 32-bit int**; convert with `unsigned = signed % 2**32` to
   compare against a compatdata folder name. Mitigation in place: entry 2's
   Launch Options explicitly `export STEAM_COMPAT_DATA_PATH=<real prefix>`
   before `%command%` so it doesn't matter which prefix Steam thinks it
   owns — **but this only works if the env var is actually exported for the
   whole shell, not prefixed onto a single command before `&`** (see #10).

10. **Steam Launch Options: don't cram everything into one shell one-liner.**
    An earlier attempt used a single Launch Options string like
    `VAR=val cmd1 & %command% args; cleanup` — this has two bugs: (a)
    `VAR=val cmd1` only exports `VAR` for `cmd1`, NOT for anything after
    `&`/`;` in the same line (basic POSIX shell scoping, easy to forget), so
    `%command%` never saw the override; and (b) it's unclear/unreliable
    exactly how Steam's Launch Options parsing handles complex multi-statement
    strings — a version of this that looked syntactically fine simply never
    executed past the first segment when Steam ran it, even though manually
    running the identical string worked fine. **Fixed by moving all of this
    into a real script file** (`game-wrapper.sh`), with Launch Options
    reduced to just `/path/to/game-wrapper.sh %command% [extra args]`. This
    pattern (`wrapper.sh %command% args`) is the standard, well-documented
    Linux Steam customization idiom — trust it over a hand-rolled one-liner.

11. **MO2's `moshortcut://` URI format is stricter than it looks.** For a
    **portable** MO2 instance (ours is portable), the correct syntax is
    `moshortcut://<executable_title>` — **no colon, no instance name at
    all**. Including any instance-name-like prefix (we tried
    `moshortcut://Default:SKSE`, using the *profile* name "Default" by
    mistake) makes MO2 look for a **named global instance** called that,
    which doesn't exist for a portable setup, producing "Instance ... not
    found". Also, the executable's exact **title string** must match what's
    configured in MO2's own `ModOrganizer.ini` under `[customExecutables]`
    (`N\title=...`) — the dropdown UI can render this with different
    spacing/casing than the stored value. Check that ini file directly
    rather than trusting the dropdown label.

## Skyrim/SKSE version-compatibility break (unrelated to Linux)

12. SKSE 2.3.0+ changed its internal address-library format; any SKSE
    plugin DLL (including Mantella's own `MantellaDialogue.dll`,
    `MantellaLauncher.dll`, `MantellaSubtitles.dll`, `SKSE_HTTP.dll`)
    compiled before that change fails to load with "must be recompiled for
    new address library". This is a **real upstream break affecting Windows
    users too**, not Linux-specific. Fix applied: downgraded the whole game
    to build **1.6.1170** (the last version before the break) via Steam
    console `download_depot` (manifests documented publicly, see
    conversation history for exact IDs), and correspondingly downgraded
    SKSE to **2.2.6** (`skse.silverlock.org/download/archive/skse64_2_02_06.7z`
    — the archive page has every historical version, unlike the front page
    which only shows "current"). Address Library's "All in One" package
    already ships every version's `.bin`, no separate action needed there.
    **If Mantella's SKSE plugins ever show this error again, check whether
    Steam silently updated Skyrim past 1.6.1170** (Automatic Updates should
    be set to "only update when launched", and we don't launch the real
    489830 entry anymore, but double check).

## xVASynth-on-Linux porting notes

Running `server.py` from source (not the Windows exe) required fixing, in
order encountered:

- `import python.pyinstaller_imports` at the very top of a `try:` block
  that also contains the *actually needed* imports — when this
  PyInstaller-only import fails (as it always will outside a frozen build),
  it aborts the whole block, silently preventing `logging`, `json`,
  `ffmpeg`, etc. from ever being imported too. **Wrap just that one import
  in its own inner `try/except: pass`.** Same bug exists in two separate
  copies of `server.py` (our git clone at `~/Games/xVASynth/src/server.py`,
  and the Steam install's `.../resources/app/server.py`) — **both are
  patched**, don't forget one if you re-copy from upstream.
- `torch_directml` import failure's `except` handler called
  `logger.exception(...)` before `logger` was successfully created (because
  of the above cascade) — raises `NameError` instead of a caught,
  logged warning. Wrapped in `try/except NameError: pass`. (Only needed in
  our git-clone copy; the Steam-install copy's equivalent block doesn't
  reference `logger`.)
- `torch==1.9.0` (pinned by upstream `requirements_cpu.txt`) only ships
  wheels up to **Python 3.9** — the venv must be 3.9, not newer.
- `numpy` must be **`<2`** — torch 1.9.0's compiled extensions are ABI-bound
  to numpy 1.x; numpy 2.x breaks `torch.nn` import with an unhelpful
  `_ARRAY_API not found` warning cascading into unrelated `ValueError`s in
  sklearn.
- `pywin32`/`pywin32-ctypes`/`pyinstaller`: strip from requirements
  entirely (Windows-only or build-tool-only, not needed at runtime).
- `pkuseg` (pulled in by `g2pC`, both Chinese-language-specific): its C
  extension doesn't compile against modern Python 3.9 headers. Not needed
  for English — stripped `g2pC`, `jaconv`, `pykakasi` (Chinese/Japanese g2p)
  from requirements entirely.
- `fairseq==0.10.0`: **not actually imported anywhere** in the runtime
  Python code (`grep -rl fairseq src/python` finds nothing) — just
  unnecessary cruft in requirements.txt that fails to build against modern
  numpy's Cython ABI. Dropped entirely, no functional loss.
- `llvmlite`/`numba` pinned versions fail to build against modern
  setuptools/distutils (`spawn() got an unexpected keyword argument
  'dry_run'` and similar). Un-pinned to let `uv` pick modern prebuilt
  wheels — the actual runtime API surface (used internally by librosa for
  resampling) is stable across the version gap.
- `ffmpeg-python` (the `import ffmpeg` package) is missing from
  `requirements_cpu.txt` entirely — a real omission upstream. Install
  separately.
- The venv's own `MantellaEnv`-style `bin/python` symlinks (`uv`-managed)
  point outside the project directory into `~/.local/share/uv/python/...`
  — same Flatpak-visibility issue as #7 applies to `xVAEnv` too, already
  covered by the same override.
- **Running from a bare git clone hits import-path errors that don't occur
  running from the Steam install's copy of the same source**, because the
  code (`python/xvapitch/model.py` etc.) tries several import fallbacks
  assuming a PyInstaller-frozen `resources/app/...` folder layout. The git
  clone doesn't have that nesting; the Steam install's own
  `resources/app/` folder *does* (it's the unpacked source next to the
  compiled exe). **Simplest fix: don't fight the import paths — just run
  `server.py` from *inside* the Steam install's own `resources/app`
  directory**, using our separately-built Linux venv's `python` binary:
  ```
  cd ".../xVASynth/resources/app"
  /home/allan/Games/xVASynth/src/xVAEnv/bin/python server.py
  ```
  (Our own git-clone copy of the source at `~/Games/xVASynth/src` is now
  effectively unused for *running* the server — it was useful for figuring
  out the dependency list and is patched too, but the Steam copy is what
  actually runs.)
- `h2p_parser` (needed by `xvapitch/text/text_preprocessing.py` for English
  pronunciation/heteronym handling): **not the same as the PyPI package
  named `H2p`** (that's an unrelated HTML-to-PDF tool — same name,
  completely different project, do not `pip install H2p`). The real project
  is `github.com/ionite34/h2p-parser`, but `pip install
  git+https://github.com/ionite34/h2p-parser.git` installs it under a
  mismatched top-level module name (something to do with its own
  packaging), which then also collides with the wrong `H2p` install if
  you'd tried that first. **Fixed by copying the repo's `h2p_parser/`
  source folder directly into `site-packages/` **, bypassing pip's build
  entirely:
  ```
  git clone --depth 1 https://github.com/ionite34/h2p-parser.git /tmp/h2p-src
  cp -r /tmp/h2p-src/h2p_parser <venv>/lib/python3.9/site-packages/
  ```
- `epitran` needed too (another `text_preprocessing.py` dependency) — plain
  `pip install epitran` works fine, no special handling needed.
- `epitran` pulls in `panphon`, whose **current** version (0.22.x) uses
  `str | None` union-type syntax that requires Python 3.10+ — breaks
  immediately on our Python 3.9 venv with `TypeError: unsupported operand
  type(s) for |: 'type' and 'NoneType'`. Pin `panphon==0.20.0` (last
  version before this syntax appeared) instead of latest.
- `nltk` needs `averaged_perceptron_tagger_eng` downloaded (not just the
  older `averaged_perceptron_tagger`, both got requested at different
  points): `python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng')"`.
- After all of the above, `/loadModel` successfully loads an actual
  xVAPitch `.pt` checkpoint (confirmed via `server.log`, not via the HTTP
  response — **a successful `/loadModel` or `/synthesize` call returns an
  empty HTTP body on success**; check `server.log`, not curl's stdout, to
  tell success from failure).
- `silero_vad_lite` (used by Mantella's own STT, unrelated to xVASynth):
  its bundled `.so` has an **executable-stack ELF flag** that modern
  hardened Linux kernels refuse to `dlopen`, with error `cannot enable
  executable stack as shared object requires: Invalid argument`. Fixed with
  `patchelf --clear-execstack <path-to>/silero_vad_lite.so` (installed
  `patchelf` via `uv pip install patchelf` into `MantellaEnv`, binary lands
  at `MantellaEnv/bin/patchelf`, not in `site-packages/patchelf/`).

## IPv6/IPv4 "localhost" mismatch (likely root cause of "NPCs not responding")

13. **This system's `getent hosts localhost` resolves to `::1` (IPv6) before
    `127.0.0.1`** (standard glibc/RFC 3484 behavior when both are present in
    `/etc/hosts`). `SKSE_HTTP.dll` contains both the literal strings
    `"localhost"` and `"127.0.0.1"` (confirmed via `strings` on the DLL) —
    it appears to use both depending on the request/code path. Mantella's
    own server (`src/http/http_server.py`) called `uvicorn.run(self.__app,
    port=port)` with **no explicit host**, which defaults to IPv4-only
    `127.0.0.1`. Any game-side request that resolved `"localhost"` to
    `::1` would silently fail to connect (connection refused — no IPv6
    listener existed at all), while requests using the literal
    `"127.0.0.1"` string worked fine. This produced exactly the confusing
    "intermittent" symptom we chased for a long time: sometimes a
    conversation attempt would partially reach the backend (whichever
    code path used `127.0.0.1`), sometimes nothing would arrive at all
    (whichever path used `"localhost"`), depending on which specific HTTP
    call the plugin happened to make.

    **Just setting `host="::"` is not enough** — on this Python/uvicorn
    setup that enables `IPV6_V6ONLY` and makes the socket IPv6-*only*,
    breaking the `127.0.0.1` path instead (traded one failure mode for
    the other, confirmed via `curl -v http://127.0.0.1:4999/` returning
    "Connection refused" after that change). **Fix**: build the listening
    socket manually and explicitly clear `IPV6_V6ONLY`, then hand its file
    descriptor to uvicorn via `fd=`:
    ```python
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::", port))
    uvicorn.run(self.__app, fd=sock.fileno())
    ```
    Confirmed working: `ss -ltnp` shows the listener as `*:4999` (true
    dual-stack) afterward, and `curl` succeeds against `127.0.0.1`,
    `[::1]`, and `localhost` all three. **If NPCs stop responding again
    after a Mantella source update that touches `http_server.py`, check
    this patch survived the update** — it's easy to accidentally revert
    if the file gets replaced wholesale.

## config.ini is only read ONCE at backend startup — editing the file does NOT hot-reload

15. `ConfigLoader` (`src/config/config_loader.py`) reads `config.ini` exactly
    once, when `main.py` starts. There is **no file-watching/mtime check** —
    `has_any_config_value_changed` is only flipped by the in-game MCM
    pushing a live value change through `__on_config_value_change`, not by
    anything touching the file on disk. **Directly editing `config.ini`
    (e.g. changing `model =`) has zero effect on an already-running backend
    — you must restart `main.py`** (see "Known-good process management"
    below) for the new value to actually be used. This cost a lot of
    confused debugging time: a `model` swap looked like it "didn't work"
    (LLM kept returning empty responses) when actually the fix was correct
    but the live process was still running the old value from its original
    startup. **Rule of thumb: after any `config.ini` edit made from outside
    the game/MCM, restart the Mantella backend before testing.**

## OpenRouter free-tier models are unreliable (shared rate-limit pool)

16. Both `openrouter/free` (the auto-router) and specific `:free`-suffixed
    models (e.g. `google/gemma-4-26b-a4b-it:free`, Mantella's own shipped
    default) intermittently return **empty (0-token) completions** with no
    error surfaced to Mantella — confirmed via direct `curl` that the
    underlying cause is a `429 Provider returned error` from the upstream
    provider's **shared free-tier quota pool** (`limit_source:
    upstream_provider_shared_pool`), which OpenRouter's free routing appears
    to swallow/retry into a blank response rather than surfacing the error.
    This is NOT a bug in our setup and is not reliably fixed by picking a
    different free model — it's structural to OpenRouter's free tier being
    shared across all users. **Fix**: added real credit to the OpenRouter
    account and switched `model`/`profile_selected_model` to a paid model,
    `anthropic/claude-3-haiku` (cheapest Claude on OpenRouter, $0.25/M
    prompt + $1.25/M completion — trivially cheap for short NPC lines).
    Check current OpenRouter model pricing/availability with:
    ```
    curl -s https://openrouter.ai/api/v1/models | python3 -c "import json,sys; [print(m['id']) for m in json.load(sys.stdin)['data'] if m['id'].startswith('anthropic/')]"
    ```
    and check remaining account credit with:
    ```
    curl -s https://openrouter.ai/api/v1/credits -H "Authorization: Bearer $(cat GPT_SECRET_KEY.txt)"
    ```
    Remember rule #15 above — changing `model` in `config.ini` requires a
    Mantella backend restart to take effect.

## xVASynth eSpeak-NG fallback tries to run a Windows .exe (silent TTS failures)

17. xVASynth's phonemizer falls back to eSpeak-NG (`ipa_to_xvaarpabet.py`,
    `_espeak_exe()`/`phonemize_espeak()`) for any word not in its built-in
    pronunciation dictionary — **any proper noun, contraction, or unusual
    word** (confirmed trigger: `"Skyrim's"`). The bundled fallback
    unconditionally invokes `./eSpeak_NG/espeak-ng.exe` (a **Windows**
    binary that doesn't exist on Linux) via
    `subprocess.Popen(" ".join(cmd), ...)` — a single joined string with no
    `shell=True`, which only works as "the whole command line" on Windows'
    native `CreateProcess`. On POSIX this instead tries to `exec` the
    **entire joined string** (quotes and all) as one literal file path,
    raising `FileNotFoundError`. The exception is unhandled inside the HTTP
    handler, so the xVASynth server **drops the connection with no
    response** — on the Mantella side this surfaces as a generic
    `requests.exceptions.ConnectionError: Remote end closed connection`,
    which looks like a networking problem, not a phonemizer bug. **This was
    a real, silent, intermittent source of "no audio" reports** — any NPC
    line containing a word needing G2P fallback would fail synthesis
    entirely (while lines using only dictionary words worked fine, making
    it look random).

    Fix (both parts needed):
    1. Install the actual Linux CLI binary: `sudo apt-get install -y
       espeak-ng` (the `espeak-ng-data`/`libespeak-ng1` packages being
       already present is NOT enough — that's the shared library, not the
       command-line tool `dpkg -l | grep espeak-ng` / `which espeak-ng`).
    2. Patch `_espeak_exe()` in
       `.../xVASynth/resources/app/python/xvapitch/text/ipa_to_xvaarpabet.py`
       to branch on `platform.system()`: keep the existing Windows string-join
       behavior unchanged, but on Linux use `shutil.which("espeak-ng")`,
       build a real argv **list** (no embedded `"` quote characters — those
       were only needed for the Windows shell-string form,
       `a.strip('"')` each arg), and call
       `subprocess.Popen(cmd_list, ...)` (no `" ".join`, no `shell=True`).
    3. **Restart the xVASynth server process** after patching — same
       "no hot reload" rule as Mantella itself.
    Verify the fix with a line that forces the fallback path, e.g. via
    `~/Games/Mantella/test_pipeline.py --espeak-test` (see below), or watch
    `server.log` for a `POST /synthesize` that used to crash now completing
    normally.

## Standalone pipeline test (no Skyrim required)

18. `~/Games/Mantella/test_pipeline.py` exercises LLM → TTS directly, without
    the game, MO2, or Proton in the loop at all — useful for isolating
    "is the backend actually broken" from "is delivery/playback to the game
    broken". Run with `./MantellaEnv/bin/python test_pipeline.py` (add
    `--espeak-test` to force a line that requires the eSpeak G2P fallback,
    see #17). It prints the LLM's raw reply, then synthesizes it and prints
    the resulting `.wav` path — play it directly with `paplay <path>` to
    confirm audio is genuinely audible on the host, independent of whether
    it's reaching Skyrim.

## Skyrim voice-file delivery path (MantellaVoice00 is NOT directly under the mod folder)

19. `config.mod_path` (`config_loader.py`) is **not** the Mantella mod
    folder itself — it's `{skyrim_mod_folder}/Sound/Voice/Mantella.esp`,
    following vanilla Skyrim's own voice-file convention
    (`Data/Sound/Voice/<Plugin.esp>/<VoiceType>/*.wav`). The actual
    game-visible delivery folder `prepare_sentence_for_game()`
    (`src/games/skyrim.py`) writes into is therefore:
    ```
    {skyrim_mod_folder}/Sound/Voice/Mantella.esp/MantellaVoice00/
    ```
    **not** `{skyrim_mod_folder}/MantellaVoice00/` — checking the wrong one
    of these looks exactly like "delivery is broken" (folder appears to not
    exist) when the pipeline is actually working fine. Confirmed-working
    delivery looks like a `.wav`+`.lip` pair landing in the real path above
    with a timestamp matching the `Synthesizing voiceline:` log line to the
    second.

    Two other logs worth checking when diagnosing "no audio despite
    successful synthesis", both under the MO2 profile's redirected
    Documents (`.../pfx/drive_c/users/steamuser/Documents/My Games/`):
    - `Skyrim.INI/SKSE/MantellaSubtitles.log` — shows the SKSE plugin's own
      subtitle-injection hook firing (`Injecting subtitle for speaker ...`).
      **This is a custom text overlay, independent of the engine's actual
      voice-type audio lookup** — subtitle success does NOT prove audio
      played, since it's a separate code path. Don't treat it as proof of
      working audio.
    - `Skyrim.INI/SKSE/MantellaDialogue.log` — conversation start/end
      events only, not per-line detail.

    Papyrus script logging is **off by default**
    (`bEnableLogging=0`/`bEnableTrace=0`/`bLoadDebugInformation=0` under
    `[Papyrus]`). We turned it on for further audio-delivery debugging.
    **Important**: the game reads the real
    `.../Documents/My Games/Skyrim Special Edition/Skyrim.INI`, NOT
    `.../MO2/profiles/Default/skyrim.ini` — this MO2 instance does not have
    "profile-specific INI files" enabled, so edit the real Documents copy,
    not the MO2 profile one (confirmed by editing the profile copy first,
    seeing zero effect after a full restart, then finding the real
    Documents copy still had the old values). Once enabled, logs land at
    `.../Documents/My Games/Skyrim Special Edition/Logs/Script/Papyrus.0.log`
    (and `.1.log`, `.2.log` for prior sessions) only after a **fresh game
    launch** (Papyrus settings are read at startup, not hot-reloaded).

    Observed but **not yet root-caused**: `Papyrus.0.log` showed
    `MantellaConversation.CleanupConversation()` throwing `Cannot cast from
    None to String[]` / `Cannot cast from None to Actor[]` / `Cannot call
    RemoveFromFaction() on a None object`, interleaved with otherwise
    apparently-successful conversations. Suspected but unconfirmed: leftover
    state from an earlier conversation that failed mid-flight (e.g. during
    the empty-LLM-response period, or the stale-config period from #15)
    never got cleanly torn down, corrupting a shared/static piece of script
    state for the next conversation. If audio delivery seems to work for
    the *first* conversation after a restart but not subsequent ones, this
    is the lead to chase next — check whether errors correlate with
    conversations that ended abnormally.

## Voice Activity Detection (VAD) threshold tuning

14. `audio_threshold` (config.ini, `[STT]` section, range 0-1, default
    0.4) controls how much of the mic signal the VAD treats as "speech."
    This needs to be re-tuned any time the mic's OS-level input volume
    changes (see #`mic volume` below) — the two settings interact.
    Symptoms of **too low** a threshold: rapid "Speech detected" / "Speech
    ended" cycles in `mantella-run.log` every 1-5 seconds with sub-second
    transcribe times, but nothing ever reaches the LLM — because each
    noise-triggered "speech" segment transcribes to an empty string, and
    `_finalize_transcription` only proceeds if the text is non-empty after
    `.strip()`. Symptoms of **too high**: no "Speech detected" line
    appears in the log at all even when actually talking. We ended up at
    **0.45** after the mic's OS input volume was corrected from 100%
    (clipping) down to 28% (its natural base-volume level, see next note)
    — the working threshold value is specific to that volume level and
    would need retuning again if the mic volume changes.

    Mic volume note: this system's USB mic
    (`alsa_input.usb-GeneralPlus_USB_Audio_Device-00.mono-fallback`) had
    its PulseAudio volume stuck at 100%, causing hard clipping (samples
    pinned at the max 16-bit value) whenever actually spoken into, despite
    sounding fine for faint background noise. Fixed with:
    ```
    pactl set-source-volume alsa_input.usb-GeneralPlus_USB_Audio_Device-00.mono-fallback 28%
    ```
    (28% matches this device's own reported "Base Volume" — its natural
    0dB reference level). Verify with a raw recording + amplitude check
    (`parecord` + inspect the `.wav` samples in Python) rather than trusting
    `pactl`'s percentage alone — the actual clipping is only obvious by
    looking at sample values directly.

## Known-good process management commands

Check both backends are actually up (ground truth, not pid files):
```
ps aux | grep "MantellaEnv/bin/python main.py" | grep -v grep
ps aux | grep "xVAEnv/bin/python server.py" | grep -v grep
ss -ltnp | grep -E "4999|8008"
```

Restart Mantella backend (from `~/Games/Mantella`):
```
pkill -9 -f "MantellaEnv/bin/python main.py"   # run as its OWN tool call, see gotcha #6
# then, separately:
cd ~/Games/Mantella && nohup ./MantellaEnv/bin/python main.py > mantella-run.log 2>&1 &
disown
```

Restart xVASynth backend:
```
pkill -9 -f "xVAEnv/bin/python server.py"   # own tool call
# then, separately:
cd "/home/allan/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/xVASynth/resources/app"
nohup /home/allan/Games/xVASynth/src/xVAEnv/bin/python server.py > /home/allan/Games/xVASynth/src/xvasynth-run.log 2>&1 &
disown
```

Neither restart requires restarting Skyrim itself — both are standalone
background services the game/SKSE talks to over localhost HTTP. Only
restart Skyrim if a *Proton/Steam-level* config changed (shortcuts.vdf,
Flatpak overrides, Proton compat tool) **or** a Skyrim.INI setting changed
(e.g. Papyrus logging, see #19) — those only take effect on a fresh launch.

**Always restart the Mantella backend after editing `config.ini` directly**
(see #15) — it is not hot-reloaded. **Always restart the xVASynth backend
after patching its source** (see #17) — same reason.

## Parked feature ideas

- **Low-OpenRouter-credit in-game warning**: user wants a crow to
  approach the player and deliver an immersive warning when API credit
  runs low — explicitly modeled on the Dark Brotherhood messenger mechanic
  (a scripted actor that spawns/paths to the player and delivers a
  one-off line). This needs real Papyrus/Creation-Kit-level scripting
  (spawning + pathing an actor), which nothing built so far touches —
  everything to date only responds within conversations the game already
  initiates. Confirmed feasible to check remaining balance
  programmatically via `GET https://openrouter.ai/api/v1/credits`. Revisit
  after the core pipeline is fully stable. Simpler fallback discussed: add
  "Crow" to the talking-animals CSV (same pattern as "Chicken") and weave
  a low-credit omen into the next conversation with a nearby crow instead
  of true proactive approach — much less work, but not what was asked for.
