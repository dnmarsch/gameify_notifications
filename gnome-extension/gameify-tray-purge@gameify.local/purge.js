// Pure notification-matching logic for gameify-tray-purge.
//
// No Shell/Gio dependencies, so it can be unit-tested with plain `gjs`
// (see ../../gnome-extension tests, run via tests/test_gnome_extension.py).
// A notification matches when its title equals `summary` and its body equals
// `body`; an empty `summary`/`body` is a wildcard.

export function matchesNotification(notification, summary, body) {
    const title = (notification && notification.title) || '';
    const nbody = (notification && notification.body) || '';
    return (!summary || title === summary) && (!body || nbody === body);
}

export function selectMatching(notifications, summary, body) {
    return notifications.filter(n => matchesNotification(n, summary, body));
}
