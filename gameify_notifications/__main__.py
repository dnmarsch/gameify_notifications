"""Command-line entry point. `python -m gameify_notifications` (or the `gameify_notifications`
console script). Keeps GUI imports lazy so --inspect / --list-huds work without
a display or Qt installed."""

import argparse
import sys
import threading

from . import config


def choose_hud(arg_hud, persisted, available, default="cod"):
    """Resolve which HUD to render at startup (pure; no I/O).

    Priority: an explicit --hud (`arg_hud`) wins, else the last session's
    `persisted` choice, else `default`. A name not in `available` falls back to
    `default` (which is assumed present)."""
    name = arg_hud or persisted or default
    return name if name in available else default


def run_inspect(source):
    print(f"Inspecting via {source.describe()}.")
    print("Trigger DMs / channel posts / meetings / calls in Teams; Ctrl-C to stop.\n")

    def on_notification(app_name, summary, body, close=None):
        print("-" * 60)
        print(f"app_name : {app_name}")
        print(f"summary  : {summary!r}")
        print(f"body     : {body!r}")
        print(f"closable : {bool(close)}")
        sys.stdout.flush()

    try:
        source.start(on_notification)
    except Exception as exc:  # noqa: BLE001
        print(f"failed to start capture: {exc}", file=sys.stderr)
        return 1
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    source.stop()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gameify_notifications",
                                     description="Teams notifications as a game HUD.")
    parser.add_argument("--match", default="",
                        help="optional capture prefilter (substring of app name/text); "
                             "empty (default) forwards all notifications and lets "
                             "rules.toml decide which apps matter")
    parser.add_argument("--hud", default=None,
                        help="HUD to render (cod, halo, mario, pokemon, goldeneye). "
                             "An explicit choice is remembered for next launch; with no "
                             "--hud the last-selected HUD is used (or cod on first run).")
    parser.add_argument("--source", default="auto",
                        help="capture strategy: 'auto' (platform default; Linux "
                             "composes freedesktop+portal), or comma-separated "
                             "names (freedesktop, portal, windows, or a plugin)")
    parser.add_argument("--list-sources", action="store_true",
                        help="list available notification sources and exit")
    parser.add_argument("--inspect", action="store_true",
                        help="print raw captured notifications and exit (no GUI)")
    parser.add_argument("--test", action="store_true",
                        help="inject fake notifications to demo the HUD")
    parser.add_argument("--list-huds", action="store_true",
                        help="list available HUDs and exit")
    parser.add_argument("--install-autostart", action="store_true",
                        help="install a desktop autostart entry and exit")
    parser.add_argument("--uninstall-autostart", action="store_true",
                        help="remove the autostart entry and exit")
    parser.add_argument("--log-level", default="INFO",
                        help="DEBUG, INFO, WARNING, ERROR (default INFO)")
    parser.add_argument("--debug", action="store_true", help="shortcut for --log-level DEBUG")
    parser.add_argument("--log-file", default=None,
                        help="override the log file path (default: <config>/logs/gameify_notifications.log)")
    parser.add_argument("--no-focus-suppress", action="store_true",
                        help="disable rule `focus_class` suppression (always add damage)")
    args = parser.parse_args(argv)

    import logging
    from .logsetup import setup_logging
    level = "DEBUG" if args.debug else args.log_level
    setup_logging(level=level, logfile=args.log_file)
    logging.getLogger("gameify_notifications.cli").info("starting: %s", vars(args))

    if args.install_autostart:
        config.ensure_config()
        config.install_autostart()
        return 0
    if args.uninstall_autostart:
        config.uninstall_autostart()
        return 0

    config.ensure_config()

    if args.list_sources:
        from .sources import available_sources
        names = available_sources(args.match)
        print("Available sources (use with --source):")
        for n in names:
            print(f"  {n}")
        print("  auto   (platform default" +
              (": freedesktop + portal" if sys.platform.startswith("linux") else "") + ")")
        return 0

    if args.inspect:
        from .sources import select_source
        return run_inspect(select_source(args.match, args.source))

    # GUI path -- import Qt layers lazily
    from .app import App
    from .huds import load_huds
    from .backends import select_backend
    from .sources import select_source
    from .focus import select_focus_probe

    huds = load_huds()
    if args.list_huds:
        for name, hud in sorted(huds.items()):
            print(f"  {name:10s} {hud.label}  [scope={getattr(hud, 'scope', 'all')}]")
        return 0

    # --hud wins for this run AND is remembered; with no --hud, use the HUD the
    # user last selected (persisted in rules.toml under `active_hud`).
    persisted = config.get_config_value(["active_hud"])
    if args.hud is not None and args.hud not in huds:
        print(f"Unknown HUD '{args.hud}'. Available: {', '.join(sorted(huds))}",
              file=sys.stderr)
    chosen = choose_hud(args.hud, persisted, huds)
    hud = huds[chosen]
    if args.hud is not None:                 # remember an explicit choice for next launch
        config.set_config_value(["active_hud"], chosen)
    probe = None if args.no_focus_suppress else select_focus_probe()
    app = App(hud, args.match, test_mode=args.test, focus_probe=probe)
    source = None if args.test else select_source(args.match, args.source)
    return select_backend().run(app, source)


if __name__ == "__main__":
    sys.exit(main())
