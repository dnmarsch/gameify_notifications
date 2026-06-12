# Test plan

Two layers, matching the architecture:

- **Pure-logic unit tests** (no Qt): `test_geometry`, `test_rules`, `test_state`,
  `test_app`. Fast, deterministic, the bulk of correctness lives here because the
  business logic is Qt-free.
- **Qt tests** (`pytest-qt`, headless `QT_QPA_PLATFORM=offscreen`): `test_huds`
  (render-to-image), `test_persistence`, `test_panel_window`, `test_widget_window`.
  These verify *wiring and rendering*, not business logic.

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest` (the env var is also set in
`conftest.py`).

## How we test the tricky parts

### Display metric scales 0% → 100% (`test_huds.py`)
Instead of counting paint calls, we render the HUD to an offscreen `QImage` at
several damage levels via `render_to_image(hud, w, h, ctx)` and assert the
pixels deterministically:
- **CoD**: edge-pixel alpha is `0` at 0% damage and increases monotonically to a
  clearly-red value at 100%; the centre stays transparent (vignette shape).
- **Halo**: more cyan pixels when shielded, more red pixels when depleted.

### HUD is scalable (`test_hud_scales_with_size`)
Render the same HUD at two surface sizes; assert the drawn content scales
(proportional rendering => more bar pixels on the larger surface). This is how we
verify "resizable/scalable" without depending on a live window manager.

### Window resizing & screen/resolution changes (`test_persistence.py`)
Real resize/monitor events can't be faithfully driven under the `offscreen`
platform (it presents one synthetic screen). So `QtPersistent` takes an
**injectable `monitors_provider`**, and tests:
- store a 50%×50% rect, swap the provider to a smaller "monitor", call
  `on_monitors_changed()`, and assert the geometry is **re-applied at the same
  fraction** (640×360 on a 1280×720 screen) — this is the resolution/orientation
  rescale.
- a saved off-screen rect **snaps back** onto a visible monitor on restore.
- while collapsed, the saved **size is frozen** (position still updates).

The pure fractional math (`rect_to_fractions`/`fractions_to_rect`/`clamp_rect`)
is additionally covered directly in `test_geometry.py`.

## Widget behavior matrix

| Widget | Behavior | Test |
|--------|----------|------|
| HUD overlay (CoD) | redness 0%→100% scales | `test_huds::test_cod_redness_scales_0_to_100` |
| HUD overlay (CoD) | vignette centre stays clear | `test_huds::test_cod_center_stays_clear_at_max` |
| HUD widget (Halo) | shield cyan→red as damage rises | `test_huds::test_halo_shield_full_is_cyan_empty_is_red` |
| HUD widget (Halo) | scalable (renders proportionally) | `test_huds::test_hud_scales_with_size` |
| HUD widget | paints to a surface | `test_widget_window::test_widget_paints_non_empty` |
| HUD widget | movable (drag handlers wired) | `test_widget_window::test_widget_has_move_and_resize_affordances` |
| HUD widget | resizable (size grip present) | same |
| HUD widget | center button re-centers + persists fraction | `test_widget_window::test_center_button_recenters_and_persists_fraction` |
| Dismiss panel | movable / resizable (handlers + grip) | implicit in construction; geometry via persistence tests |
| Dismiss panel | collapsible to toolbar | `test_panel_window::test_collapse_to_toolbar_and_expand` |
| Dismiss panel | toolbar expands back | same |
| Dismiss panel | collapsed state persists | `test_panel_window::test_collapsed_state_persists_across_instances` |
| Dismiss panel | dismiss removes row + heals damage | `test_panel_window::test_dismiss_removes_row_and_heals` |
| Dismiss panel | clear-all | `test_panel_window::test_clear_all` |
| Dismiss panel | new notification appears live | `test_panel_window::test_new_notification_appears_live` |
| Damage state | accumulate / dismiss / clear / observers | `test_state.py` |
| Rules | app-aware classify (app+text), first-match, app-scoping, unmatched→`None` | `test_rules.py` |
| App | notify → classify → state; Outlook mild (0.5); unmatched app ignored | `test_app.py` |
| Geometry | clamp / fractions / max-frac / off-screen | `test_geometry.py` |
| Sources | parsers, composite fan-in, registry/selection, plugins, capture prefilter (empty=forward all) | `test_sources.py` |
| Factories | `select_backend`, `make_hud_window` scope routing | `test_factories.py` |
| Logging | async queue handler, context (thread/func/line), below-level suppression, env override, idempotent | `test_logsetup.py` |
| Closer / clear | source builds closer, id-correlation, forwarder dedup, best-effort `_close`, dismiss/clear fire it | `test_sources.py`, `test_state.py`, `test_app.py` |
| Focus suppress | drop-when-focused, allow-elsewhere, disabled/none-probe, rule-without-`focus_class`, X11 `WM_CLASS` parse | `test_app.py`, `test_focus.py`, `test_rules.py` |
| Panel scrolling | N notifications listed (no cap), scrollbar engages | `test_panel_window.py` |

## Not covered by automated tests (manual / future)
- True click-through of the all-monitor overlay (`WindowTransparentForInput`) —
  can't assert input pass-through under `offscreen`; verify manually on X11.
- Real multi-monitor spanning and live monitor hotplug — verify on hardware.
- The Windows WinRT source (`windows_source.py`) — needs a Windows host with the
  `winrt` packages and granted notification access.
- D-Bus capture against a live Teams — verify with `gameify_notifications --inspect`.
