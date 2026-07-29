# CLAUDE.md — Fork Maintenance Guide

This is a **personal fork** of [tuanchris/dune-weaver](https://github.com/tuanchris/dune-weaver).
Upstream is tracked as the `upstream` remote. The last merged upstream release is **v4.1.4**
(merge commit `2d112c2`, from upstream `7ddb7f6`).

## How to Merge a New Upstream Release

1. Add remote if not present: `git remote add upstream https://github.com/tuanchris/dune-weaver.git`
2. Fetch: `git fetch upstream`
3. Merge: `git merge upstream/main` (resolve conflicts, see *Conflict-Prone Files* below)
4. Run through every item in *Downstream Patches* and verify nothing was reverted or broken.
5. Rebuild frontend dist if any `.tsx` files changed: `cd frontend && npm run build`
6. Update the "last merged upstream release" line above.
7. Update this document if patches needed adjusting.

### Conflict-Prone Files

These files are heavily modified in this fork and almost always need manual attention during merges:

| File | Why |
|---|---|
| `modules/led/dw_led_controller.py` | Full RGBCCT dual-WS2811 extension |
| `modules/led/dw_leds/effects/white_effects.py` | Fork-only file — upstream may not have it |
| `modules/mqtt/handler.py` | RGBCCT topics, Home button, Clear button, restore logic |
| `modules/connection/connection_manager.py` | Restore-on-startup LED logic |
| `modules/core/state.py` | RGBCCT state fields |
| `main.py` | RGBCCT endpoints, startup LED init |
| `frontend/src/pages/LEDPage.tsx` | RGBCCT white-channel UI |
| `frontend/src/pages/SettingsPage.tsx` | RGBCCT / restore-on-startup toggles |
| `dw` / `setup-pi.sh` | sudo-user detection, Docker-to-native migration |
| `static/dist/` | **Always rebuild after merging** — upstream ships pre-built dist; our fork's RGBCCT UI must be rebuilt to produce a combined bundle. See *Frontend Dist Rebuild* note below. |

### Frontend Dist Rebuild Note

Both this fork and upstream commit pre-built `static/dist/` files. On every upstream merge that
touches any `.tsx`/`.ts` file, `static/dist/` conflicts are expected and **always resolved by
rebuilding**, not by picking one side:

1. For each `static/dist/` conflict: `git checkout --theirs <file>` (take upstream's version)
2. Complete the merge commit.
3. `cd frontend && npm run build` — this produces a new `index-<hash>.js` that contains both upstream UI changes and the fork's RGBCCT UI.
4. Stage the new dist files: `git add static/dist/`; remove old hash-named bundles: `git rm --cached static/dist/assets/index-<old-hash>.js`
5. Commit with message `build: rebuild frontend dist …`

`sw.js` and `workbox-*.js` may appear as untracked after a merge — this is normal; `git add` them after the rebuild.

---

## Downstream Patches

All changes made in this fork relative to upstream. Listed oldest-to-newest.
**Always verify these after an upstream merge.**

---

### 1. RGBCCT Dual WS2811 Support
**Commits:** `9a95b50`, `cd4a6bf`, `0b72deb`, `a34c3d8`, `11c0a26`
**Theme:** Core feature — new hardware support

Adds full support for RGBCCT LED strips wired as dual WS2811 (each logical pixel uses
two physical WS2811 chips: one RGB, one warm-white/cool-white).

**What changed:**

- `modules/led/dw_led_controller.py` — `_DualWS2811RGBCCTProxy` class wraps the physical
  NeoPixel object, intercepts `__setitem__`/`show` to apply separate RGB and white-channel
  brightness scaling. `DWLEDController` extended with `set_white_brightness_level()`,
  `set_color_temperature()`, `set_white_effect()`, `set_white_brightness_and_temperature()`,
  and a white-effect background thread (`_white_effect_thread`).

- `modules/led/dw_leds/effects/white_effects.py` — **Fork-only file** (does not exist
  upstream). Defines 6 animated white-channel effects: `BrightnessFade`, `Chase`,
  `Colorloop`, `DualChannel`, `TemperaturePulse`, `TemperatureSweep`, plus
  `get_white_effect()` / `get_all_white_effects()` registry.

- `modules/led/led_interface.py` — passes `dual_ws2811_rgbcct` to `DWLEDController`;
  adds `white_effect_settings` passthrough on `effect_idle()` / `effect_playing()`.

- `modules/core/state.py` — adds RGBCCT fields: `dw_led_dual_ws2811_rgbcct`,
  `dw_led_color_temperature`, `dw_led_white_brightness`, `dw_led_restore_on_startup`,
  `dw_led_white_speed`, `dw_led_white_intensity`, `dw_led_white_base_temperature`,
  `dw_led_idle_white_effect`, `dw_led_playing_white_effect`. All persisted in
  `settings.json` via `to_settings_dict` / `from_settings_dict`.

- `modules/core/pattern_manager.py` — passes `dw_led_idle_white_effect` /
  `dw_led_playing_white_effect` to `effect_idle_async()` / `effect_playing_async()`.

- `main.py` — `DwLedSettingsUpdate` and `LEDConfigRequest` models include RGBCCT fields;
  `GET /api/settings` and `PATCH /api/settings` handle RGBCCT; RGBCCT-aware startup LED
  init block (lines ~188–238); 9 new endpoints under `/api/dw_leds/white_*` and
  `/api/dw_leds/color_temperature`.

- `frontend/src/pages/LEDPage.tsx` — full RGBCCT white-channel control card with
  brightness, color temperature, effect picker, and white-effect automation.

- `frontend/src/pages/SettingsPage.tsx` — "RGBCCT Dual WS2811 Mode" and
  "Restore LED State on Startup" toggles in DW LED settings.

**Upstream merge risk:** HIGH. This is the largest patch. If upstream refactors
`DWLEDController`, `LEDInterface`, or `LEDPage.tsx`, expect conflicts.

---

### 2. Dead Code Removal
**Commit:** `a1effdd`
**Theme:** Cleanup

Removed `set_white_mode` endpoint and related state fields (`dw_led_white_mode`,
`dw_led_white_level`) that were never called from the frontend.

**What changed:**
- `main.py` — removed `/api/dw_leds/set_white_mode` endpoint
- `modules/led/dw_led_controller.py` — removed `set_white_mode()` method
- `modules/core/state.py` — removed `dw_led_white_mode`, `dw_led_white_level` fields
- `frontend/src/pages/LEDPage.tsx` — removed those fields from fetch

**Upstream merge risk:** LOW. If upstream adds back fields with these names, skip the
removal or reconcile carefully.

---

### 3. Homing Popup Auto-Dismiss
**Commit:** `7736e7d`
**Theme:** UX tweak

Changed the homing-completion popup countdown from 5 seconds to 0 so the overlay
clears immediately when homing finishes.

**What changed:**
- `frontend/src/components/layout/Layout.tsx` — countdown constant changed from `5` to `0`
- `static/dist/` — rebuilt frontend dist

**Upstream merge risk:** LOW. If upstream changes `Layout.tsx`, re-apply: find the
countdown constant (typically named something like `HOMING_DISMISS_SECONDS` or similar)
and set it to `0`.

---

### 4. MQTT Home Button for HA Auto-Discovery
**Commit:** `c5ef054`
**Theme:** Home Assistant integration

Exposes a "Home machine" button via MQTT discovery so Home Assistant picks it up
automatically alongside the existing stop/pause/play/skip controls.

**What changed:**
- `modules/mqtt/handler.py`:
  - Added `self.led_power_topic` → `{device_id}/command/home` subscription in `on_connect()`
  - Added `home_config` discovery payload in `setup_ha_discovery()`
  - Added handler branch in `on_message()`: calls `callback_registry['home']()`, guarded
    by `state.conn.is_connected()` and `not state.is_homing`

**Upstream merge risk:** MEDIUM. If upstream adds its own home button, check for
duplicates.

---

### 5. MQTT Clear Button for HA Auto-Discovery
**Commits:** `075ccf8`, `b4a0742`
**Theme:** Home Assistant integration

Exposes a "Clear sand" button via MQTT discovery. Uses the user-configured
`clear_pattern` mode (falling back to `clear_from_out` if set to `"none"`).

**What changed:**
- `modules/mqtt/handler.py`:
  - Added `{device_id}/command/clear` subscription in `on_connect()`
  - Added `clear_config` discovery payload in `setup_ha_discovery()`
  - Added handler branch in `on_message()`: calls `callback_registry['clear']()`, guarded
    by connection and `is_homing` checks
- `modules/mqtt/utils.py`:
  - `get_clear_pattern_file()` helper resolves the effective clear pattern path
  - Added `state.stop_requested = False` reset before executing the clear pattern
    (fixes: `stop_requested` left `True` after homing caused immediate bail-out)

**Upstream merge risk:** MEDIUM. If upstream adds a clear button, check for duplicates.

---

### 6. LED Idle Effect Color Retention Across Power Cycles
**Commit:** `9356037`
**Theme:** Bug fix

`effect_idle()` returned early without updating the queued effect ID when brightness
was zero. After the connection green-flash (which sets Blink), the subsequent
`effect_idle()` call also bailed out, leaving Blink as the active effect. When the
user later raised brightness, Blink played instead of the configured effect.

Also fixed `set_palette()` crash when saved settings contain a `null` palette_id
(`dict.get("key", default)` returns `None`, not the default, when the key exists
with a `null` value).

**What changed:**
- `modules/led/dw_led_controller.py`:
  - `effect_idle()`: when brightness is 0, still writes correct `effect_id` and
    `palette_id` into locked controller state before returning
  - `set_palette()`: `palette_id = settings.get("palette_id") or 0` (handles null)
- `modules/connection/connection_manager.py`:
  - Post-connection `effect_idle()` call now passes `white_effect_settings`

**Upstream merge risk:** MEDIUM. If upstream refactors `DWLEDController.effect_idle()`
or `set_palette()`, re-apply this logic.

---

### 7. Home Assistant Dashboard Card and Scripts
**Commit:** `0d66f39`
**Theme:** Home Assistant integration (non-code assets)

Adds ready-to-paste HA YAML files.

**What changed:**
- `ha_dashboard/dune_weaver_card.yaml` — Lovelace vertical-stack card with playback
  controls, pattern actions, and LED controls (color + RGBCCT white)
- `ha_dashboard/dune_weaver_scripts.yaml` — HA script definitions (all-lights-on/off,
  shuffle-playlist), with inline setup instructions

**Upstream merge risk:** NONE. These files do not exist upstream.

---

### 8. Restore-on-Startup: Keep LED Off When Previously Off; Fix MQTT Unresponsiveness
**Commit:** `e731397`
**Theme:** Bug fix

When `dw_led_restore_on_startup` is enabled and the saved LED brightness was 0,
`connect_device()` was unconditionally calling `effect_loading()`, `effect_connected()`,
and `effect_idle()` — all of which force `_powered_on = True`. This had two effects:

1. LED turned on after every power restore even when it was off before power loss.
2. MQTT appeared unresponsive: HA sent its retained `OFF` state when the device
   subscribed, but `effect_idle()` ran *after* that, re-powering the LED and making
   subsequent MQTT commands appear to have no effect.

**What changed:**
- `modules/connection/connection_manager.py` (`connect_device()`):
  - Added `_restore_led_off` flag: True when `dw_led_restore_on_startup` is enabled,
    provider is `dw_leds`, and saved brightness is 0 (standard) or both RGB and white
    brightness are 0 (RGBCCT).
  - `effect_loading()` is skipped when `_restore_led_off` is True.
  - The post-connection block: when `_restore_led_off` is True, calls `set_power(0)`
    instead of `effect_connected()` + `effect_idle()` + `_start_idle_led_timeout()`.

**Upstream merge risk:** MEDIUM. If upstream changes the post-connection LED block in
`connect_device()`, re-apply this guard around the effects.

---

### 9. Home Assistant Discovery and JSON Light Alignment
**Commit:** `3126e87`
**Theme:** Home Assistant integration and MQTT compatibility

Aligns Home Assistant discovery and state payloads with the application and HA's JSON
light schema:

- Speed discovery uses the application's full 10–6000 range with a step of 10.
- The RGB light declares `supported_color_modes: ["rgb"]`.
- RGB state uses a nested `{state, color}` JSON payload.
- RGB commands accept HA JSON light power/color commands while retaining compatibility
  with the former flat RGB payload.
- `tests/unit/test_mqtt_handler.py` covers discovery, state, and command behavior.

**Upstream merge risk:** MEDIUM. Upstream's divergent `release/v4.1.4` branch contains
a similar MQTT light fix, but upstream `main` does not. Preserve this patch unless the
equivalent upstream implementation is intentionally adopted and verified.

---

### 10. Selected Pi-era v4.1.4 Release Features
**Source commit:** `c4917ac` (`upstream/release/v4.1.4`)
**Theme:** Reliability and scheduling

The divergent release commit was not merged wholesale because it was built on an
older pre-`upstream/main` snapshot and duplicates generated assets and MQTT work.
The still-useful Raspberry Pi features were ported onto the current merged code:

- FluidNC serial corruption errors `170`–`181` are retried like the existing
  corruption responses.
- Queue additions retain the full `patterns/` path required by the executor.
- Playlist timing supports a start-to-start cadence, exposed in the UI as plays
  per day.
- An optional daily host reboot can be configured in Settings. It is disabled by
  default and waits for the current pattern to finish before rebooting.
- `requirements-nonrpi.txt` explicitly includes PyYAML for FluidNC configuration
  parsing.

The release commit's MQTT light implementation was intentionally not copied:
fork commit `3126e87` is newer, has regression coverage, and supports both Home
Assistant's nested JSON light schema and the fork's legacy flat RGB commands.
The old release's `VERSION` and generated frontend assets were also not copied;
the current `upstream/main` 4.1.4 version and a fresh frontend build are used.

**What changed:**
- `main.py` — scheduled reboot API/monitor, playlist cadence forwarding, queue path
- `modules/core/pattern_manager.py` — FluidNC retries and cadence calculation
- `modules/core/playlist_manager.py` — cadence forwarding
- `modules/core/state.py` — scheduled reboot persistence
- `frontend/src/pages/PlaylistsPage.tsx` — plays-per-day control
- `frontend/src/pages/SettingsPage.tsx` — scheduled reboot settings
- `requirements-nonrpi.txt` — PyYAML dependency
- `tests/unit/` — settings, queue, cadence, and API forwarding coverage

**Upstream merge risk:** MEDIUM. Remove these downstream copies when equivalent
features land on `upstream/main`; preserve the fork's MQTT implementation until
its compatibility behavior is covered upstream.

---

## Setup Script Improvements
**Commits:** `9a95b50`, `11c0a26`
**Theme:** Installation / ops

- `setup-pi.sh`: sudo-user detection (`REAL_USER`/`REAL_HOME`), early nginx
  configuration, removed `apt full-upgrade`, `/dev/tty` fix for piped installs.
- `dw` (management script): Docker-to-native migration block (creates venv, removes
  Docker containers), stops lingering named `dune-weaver` Docker containers not managed
  by compose (prevents duplicate MQTT client IDs from Docker+systemd co-existing).

**Upstream merge risk:** MEDIUM. Upstream occasionally updates `setup-pi.sh` and `dw`.
Re-apply sudo-user detection and Docker migration blocks after merging.

---

## Automation Instructions for Claude

When the user says **"update to the latest upstream version"** or similar:

1. Run `git fetch upstream` and `git log upstream/main --oneline -10` to see what's new.
2. Summarize upstream changes to the user before merging.
3. Run `git merge upstream/main`.
4. For each conflict, consult the *Conflict-Prone Files* table and *Downstream Patches*
   above to understand which side to favour.
5. After resolving, verify every patch in this document is still intact by checking the
   key files and functions listed under each patch.
6. If a patch needed adjustment, update its entry in this document.
7. Rebuild frontend dist if needed, commit, and push.

**When adding a new feature or fix to this fork**, add an entry to *Downstream Patches*
above before closing the session. Include: what the change does, which files/functions
were modified, and the upstream merge risk level.
