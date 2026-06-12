"""Windows notification capture via the WinRT UserNotificationListener, which
lets an app read the Action Center (with user permission). Polls for new
toasts and forwards them. Runs on a background thread with its own asyncio loop,
so it satisfies the same NotificationSource contract as the Linux source.

This requires the `winrt`/`winsdk` packages and runs only on Windows; it's
guarded so the module imports cleanly elsewhere."""

import logging
import threading

from . import NotificationSource

log = logging.getLogger(__name__)


class WindowsNotificationSource(NotificationSource):
    name = "windows"

    def __init__(self, match_substr):
        self.match = match_substr
        self._stop = False
        self._thread = None

    def start(self, callback):
        self._thread = threading.Thread(target=self._run, args=(callback,),
                                        name="winrt-notify", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True

    def describe(self):
        return f"Windows UserNotificationListener (matches '{self.match}')"

    def _run(self, callback):
        try:
            import asyncio
            from winrt.windows.ui.notifications.management import (
                UserNotificationListener, UserNotificationListenerAccessStatus)
            from winrt.windows.ui.notifications import NotificationKinds
        except Exception as exc:  # pragma: no cover (Windows-only)
            log.error("WinRT notifications unavailable: %s. Install e.g. "
                      "`pip install winrt-Windows.UI.Notifications "
                      "winrt-Windows.UI.Notifications.Management`.", exc)
            return

        needle = self.match.lower()

        async def main():  # pragma: no cover (Windows-only)
            listener = UserNotificationListener.current
            status = await listener.request_access_async()
            if status != UserNotificationListenerAccessStatus.ALLOWED:
                log.warning("Windows notification access not granted by the user.")
                return
            seen = set()
            while not self._stop:
                notes = await listener.get_notifications_async(NotificationKinds.TOAST)
                current = set()
                for un in notes:
                    nid = un.id
                    current.add(nid)
                    if nid in seen:
                        continue
                    seen.add(nid)
                    app_name = ""
                    try:
                        app_name = un.app_info.display_info.display_name or ""
                    except Exception:
                        pass
                    summary, body = "", ""
                    try:
                        binding = un.notification.visual.bindings[0]
                        texts = [t.text for t in binding.get_text_elements()]
                        summary = texts[0] if texts else ""
                        body = " ".join(texts[1:])
                    except Exception:
                        pass
                    if (not needle) or needle in app_name.lower() \
                            or needle in f"{summary} {body}".lower():
                        log.debug("[windows] captured app=%r summary=%r", app_name, summary)
                        callback(app_name, summary, body, None)   # no close handle (yet)
                seen &= current  # forget dismissed notifications
                await asyncio.sleep(2)

        try:
            import asyncio
            asyncio.run(main())
        except Exception:
            log.exception("WinRT notification poller crashed")
