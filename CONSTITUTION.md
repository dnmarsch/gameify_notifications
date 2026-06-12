# Project Constitution — gameify_notifications_overlay

This document is the **source of truth** for how implementations are made in this
repository. Every change — by a human or an AI assistant — MUST comply. When a
request conflicts with the constitution, surface the conflict and follow the
constitution unless the maintainer explicitly overrides it for that change.

The keywords **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are used in the
RFC-2119 sense.

---

## 0. Definition of Done (the checklist)

A change is not "done" until **all** of these hold:

- [ ] **Tests** added or updated for every created/modified behavior, and the
      **whole suite passes** headless: `QT_QPA_PLATFORM=offscreen pytest -q`.
- [ ] **Single Responsibility** — each new module/class/function does one thing.
- [ ] **Open–Closed** — new capability is added by *extending* a seam, not by
      editing core control flow.
- [ ] **No duplication** — shared logic is factored (mixin / helper / base),
      not copy-pasted.
- [ ] **Composition over inheritance** — see §4; production code keeps minimal
      touch points.
- [ ] **Robust to bad input** — user-supplied values are validated and fall back
      to defaults; a bad config never crashes a running overlay.
- [ ] **Cross-platform** — no hard OS dependency leaks into the core; platform
      specifics live behind a seam (§5).
- [ ] **Docs updated** — README + `DEFAULT_RULES` for user-facing knobs; `docs/`
      for any new OS/technology/capability and its limitations (§6).

---

## 1. Testing is mandatory

- Any implementation that is **created or modified MUST ship with new or updated
  unit tests** in the same change. "It's a small change" is not an exception.
- Tests live in `tests/`, run under `pytest` (+ `pytest-qt` for widgets), and
  MUST pass headless (`QT_QPA_PLATFORM=offscreen`, already forced in
  `tests/conftest.py`).
- **Test the seams, not the toolkit.** Pure logic (damage model, geometry,
  rules, param validation) is tested directly; Qt widgets are tested via
  `qtbot` and offscreen `render_to_image(...)` pixel assertions.
- **Validation gets explicit valid AND invalid tests.** Every user-tunable input
  MUST have tests for: present-and-valid, absent → default, and
  invalid/out-of-range/wrong-type → default. (See `tests/test_params.py`.)
- Genuinely-unreachable-in-CI paths (e.g. Windows-only probes, the live Qt event
  loop) are marked `# pragma: no cover` — never left silently untested.
- When behavior changes, **update the existing tests** to match the new contract
  rather than deleting coverage.

## 2. Single Responsibility (SRP)

- The core (`config`, `geometry`, `rules`, `state`, `app`, `huds/*`) is
  **GUI-free and import-light**; it MUST NOT import Qt or platform toolkits.
- One module = one concern. If a function fuses transport + formatting + policy,
  split it. (See how `run_qt` is decomposed into `_build_windows`,
  `_wire_repaint`, `_wire_capture`, `_wire_config_watch`, … in
  `backends/qt/backend.py`.)

## 3. Open–Closed Principle (OCP)

- Add features by **implementing an existing seam and registering it**, not by
  editing core branching. The seams:
  | Concern | Contract | Add one by… |
  |---|---|---|
  | Notification capture | `NotificationSource` (ABC) | subclass + `select_source()` / drop-in `sources/*.py` |
  | Windowing | `OverlayBackend` (ABC) | subclass + `select_backend()` |
  | HUD rendering | `Hud` (base) + `ParamSpec` | subclass + `_builtin_huds()` / drop-in `huds/*.py` |
  | Tray purge | `TrayCleaner` (ABC) | subclass + `select_tray_cleaner()` |
  | On-screen probe | `FocusProbe` (ABC, callable) | subclass + `select_focus_probe()` |
- A new HUD/source/backend MUST NOT require edits to unrelated overlays or to the
  damage core.

## 4. Patterns (use the right one; don't reinvent)

These patterns are already established — extend them, don't fork them:

- **Strategy + Dependency Injection** — `NotificationSource`, `OverlayBackend`,
  `TrayCleaner`, `FocusProbe`. Concrete impls are chosen by `select_*` factories
  and injected; nothing hard-codes a platform.
- **Factory** — `select_source` / `select_backend` / `select_tray_cleaner` /
  `select_focus_probe` / `load_huds`. Platform/feature selection lives here.
- **Observer** — `DamageState.subscribe()/_notify()` is the single source of
  truth for damage; the HUD and the dismiss panel are observers. New consumers of
  damage state **subscribe**; they MUST NOT poll or hold a private copy.
- **ADT / validated value objects** — user config is parsed into validated data
  via `huds/params.py` (`Param` / `ParamSpec`). New tunables MUST be declared as
  `Param`s (type + range + optional predicate) so invalid input degrades to a
  default with a logged, deduped warning. Never read raw `ctx.params[...]`.
- **Single builder for shared context** — windows and the panel build their
  `HudContext` through `backends/qt/_context.py::make_context` so displayed
  damage can't drift. Don't hand-roll a second context builder.

## 5. DRY, and composition over inheritance

- **DRY** — when two implementations share logic, extract it: a **mixin**
  (e.g. `ShieldHealthModel`, shared by Halo + GoldenEye), a helper, or a base.
  Copy-paste of behavior is a defect, not a style choice.
- **Prefer composition over inheritance.** Favor small, mixable units and
  injected collaborators over deep class hierarchies. Inheritance is acceptable
  for a genuine *is-a* with a stable base (e.g. `Hud` subclasses); cross-cutting
  behavior is a **mixin or injected strategy**, not a new base class.
- Minimize **touch points in production code**: a change should be local. If a
  feature forces edits across many unrelated files, the seam is wrong — fix the
  seam first.

## 6. Cross-platform & documentation

- New functionality **MUST be OS-agnostic** at the core and reach the OS only
  through a seam (§3). No `if platform == ...` scattered in business logic; put
  it in the relevant `select_*` factory or a concrete strategy.
- Drawing stays toolkit-portable (QPainter, no cairo); transport stays behind
  `NotificationSource`; windowing behind `OverlayBackend`.
- When a change adds **a new OS, a new technology/dependency, or a new capture
  path**, you MUST update `docs/` with: how it works, how to enable it, and its
  **limitations** (confinement, latency, what it can't see, version constraints).
  User-facing knobs are additionally documented in `README.md` and the
  `DEFAULT_RULES` comments.
- New third-party dependencies MUST be cross-platform or isolated behind a seam
  so unsupported platforms degrade gracefully (no-op), never crash.

## 7. Robustness

- Treat all external input (rules.toml, notification payloads, monitor geometry,
  D-Bus messages) as hostile: validate, clamp, and fall back to safe defaults.
- A malformed config or a transient OS quirk MUST NOT crash the overlay — log and
  continue with last-known-good / defaults (see `RuleSet.reload`, `ParamSpec`,
  the zero-size-workarea guard in `geometry.rect_to_fractions`).

## 8. License & open source

This project is open source under the **MIT License** (see `LICENSE`).
Contributions are accepted under the same license. Keep third-party assets and
dependencies license-compatible with MIT, and record their provenance.

---

*Amendments to this constitution are themselves changes: propose, justify, and
update this file in the same commit.*
