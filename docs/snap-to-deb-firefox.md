# Switching Firefox from snap → .deb (for D-Bus notification capture)

## Why

`gameify_notifications_overlay` captures notifications by passively monitoring the session
D-Bus (`org.freedesktop.Notifications.Notify` + the XDG portal). **AppArmor-confined
snap apps' notifications are invisible to a D-Bus monitor** — verified: a
`notify-send` (unconfined) is captured, but snap Outlook/Firefox notifications
never appear, even to `dbus-monitor` (which sees everything a monitor is allowed
to). So to capture browser-based Teams/Outlook (web/PWA) notifications, run an
**unconfined `.deb` Firefox**. Firefox uses the system notification daemon by
default (no extra setting, unlike Chrome's "Use system notifications").

> Same idea applies to any app: the unconfined `.deb`/AppImage build is
> capturable; the snap build generally is not.

---

## Part 1 — Install the unconfined .deb Firefox (Mozilla APT repo)

Ubuntu's `firefox` package is a **transitional shim to the snap**, and it carries
an **epoch (`1:1snap1`)** that sorts *above* Mozilla's version — so a correct APT
**pin** is mandatory.

```bash
# 1. Signing key
sudo install -d -m 0755 /etc/apt/keyrings
wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O- \
  | sudo tee /etc/apt/keyrings/packages.mozilla.org.asc > /dev/null

# (optional) verify fingerprint == 35BAA0B33E9EB396F59CA838C0BA5CE6DC6315A3
gpg -n -q --import --import-options import-show /etc/apt/keyrings/packages.mozilla.org.asc \
  | awk '/pub/{getline; gsub(/^ +| +$/,""); print}'

# 2. Repo
echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" \
  | sudo tee /etc/apt/sources.list.d/mozilla.list > /dev/null
```

> ⚠️ **Pin gotcha:** APT preferences are whitespace-sensitive — any leading
> spaces and the pin is silently ignored (you'll see every version at priority
> `500`). Use `printf` so there is **zero** indentation, not an indented
> `echo`/heredoc:

```bash
# 3. Pin (priority 1000 beats the epoch-1 snap transitional)
printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' \
  | sudo tee /etc/apt/preferences.d/mozilla

# 4. Verify: Candidate must be the Mozilla build at priority 1000
sudo apt update
apt-cache policy firefox
#   Candidate: 151.0.4~build1
#       1000 https://packages.mozilla.org/apt mozilla/main amd64 Packages   <-- good
#   (NOT  1:1snap1-0ubuntu5  at 500)
```

Install (epoch makes apt see it as a "downgrade", so allow it):

```bash
sudo apt install --allow-downgrades firefox
/usr/bin/firefox --version        # -> Mozilla Firefox 151.0.4
```

The `.deb` ships its own launcher at `/usr/share/applications/firefox.desktop`,
so it shows up in Activities — right-click its dock icon → **Pin to Dash**.

---

## Part 2 — Bring your bookmarks/history/passwords across

Snap Firefox stores its profile under
`~/snap/firefox/common/.mozilla/firefox/`; the `.deb` uses the standard
`~/.mozilla/firefox/`. Same major version → copying the whole profile is safe and
restores **bookmarks, history, saved passwords, extensions, and prefs**.

### Case A — the snap is still installed (do this BEFORE removing it)

```bash
mkdir -p ~/.mozilla
cp -a ~/snap/firefox/common/.mozilla/firefox ~/.mozilla/firefox
ls ~/.mozilla/firefox          # -> <id>.default  profiles.ini  ...
/usr/bin/firefox &
```

### Case B — you ALREADY removed the snap (recover from the auto-snapshot)

`snap remove` (without `--purge`) **auto-creates a snapshot** of the snap's data.

```bash
snap saved                      # find the firefox set, e.g.  Set 3  firefox ... auto
sudo snap install firefox       # reinstall so snapd can restore into it
sudo snap restore 3             # <- the Set ID from `snap saved`

# confirm the profile came back, then copy it across
find ~/snap/firefox/common/.mozilla/firefox -name places.sqlite
mkdir -p ~/.mozilla
cp -a ~/snap/firefox/common/.mozilla/firefox ~/.mozilla/firefox
/usr/bin/firefox &
```

### If Firefox opens a blank profile

Modern Firefox keys the default profile per-install, so it may not auto-pick the
copied one:

1. Open `about:profiles`
2. Find your `<id>.default`, click **Set as default profile**
3. Restart Firefox

---

## Part 3 — Remove the snap & verify capture

```bash
# plain `firefox` now = the .deb; snapshot stays as a backup (--purge skips making a new one)
sudo snap remove --purge firefox
which -a firefox                 # should be only /usr/bin/firefox
```

Verify notifications are now capturable:

```bash
# unconfined sanity check
notify-send "test" "hello"

# then watch real traffic
python -m gameify_notifications --inspect
# open Teams/Outlook web in the .deb Firefox, trigger a notification ->
# it should print app_name / summary / body. Use that app_name in rules.toml.
```

---

## Gotchas recap

- **Pin whitespace** — leading spaces silently void the pin (`printf`, not indented `echo`).
- **Epoch** — `1:1snap1` outranks `151.x`; the `1000` pin is required, and install needs `--allow-downgrades`.
- **Snap data isn't gone** on `snap remove` — it's in `snap saved` (unless you used `--purge`).
- **PATH conflict** while both are installed — call `/usr/bin/firefox` explicitly until the snap is removed.
- **Confinement is the root cause** — snap notifications can't be seen by a D-Bus monitor; `.deb`/AppImage/unconfined apps can.
