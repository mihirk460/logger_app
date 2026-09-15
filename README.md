# Logger

A tiny Flask web app for logging daily activities. Create a category (name, note, color, icon), tap it to log it for today (or any date), and see your history in a calendar and a bar chart. Login is username + 4-digit PIN. Each user sees only their own categories and logs.

Everything lives in one process on the Raspberry Pi. The database is a single SQLite file at `data/logger.db`.

```
app.py            all routes and DB code
templates/        HTML pages
static/           CSS + Chart.js (vendored, no CDN needed)
logger.service    systemd unit so the app starts on boot
data/             created on first run: logger.db + secret_key (not in git)
```

## 1. Run it on the Pi

SSH in and clone:

```sh
ssh mihirpi@192.168.1.229
git clone https://github.com/mihirk460/logger_app.git
cd logger_app
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python app.py
```

Open `http://192.168.1.229:5000` from any phone on your home Wi-Fi. Ctrl-C stops it.

### Run it permanently (starts on boot, restarts on crash)

```sh
sudo cp logger.service /etc/systemd/system/logger.service
sudo systemctl daemon-reload
sudo systemctl enable --now logger
sudo systemctl status logger        # should say "active (running)"
journalctl -u logger -f             # live logs
```

The unit assumes the repo is at `/home/mihirpi/logger_app` and the user is `mihirpi`. Edit the file if that differs.

### Updating

```sh
cd ~/logger_app && git pull && sudo systemctl restart logger
```

### Backup

The whole database is one file. Copy it somewhere now and then:

```sh
cp ~/logger_app/data/logger.db ~/logger-backup-$(date +%F).db
```

## 2. Letting family in India reach it

The app runs only on your home LAN until you pick one of these. Pick **A** unless you have a reason not to.

### A. Tailscale (recommended)

Tailscale makes a private network (a "tailnet") between your Pi and your family's phones, over the internet, with no port forwarding and no public exposure.

- Free personal plan: up to 6 users, unlimited devices.
- Nobody on the internet can even see the app. Only people you invite.
- Family members do **not** need your account. You invite them; they sign in with their own Google/Apple/Microsoft/GitHub login and become members of your tailnet.
- Downside: each family member installs the Tailscale app and signs in once.

Steps (the Pi is already on your tailnet from another project, so skip step 1 if `tailscale status` on the Pi shows it connected):

1. On the Pi: `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`. Open the link it prints and sign in.
2. Invite family: go to https://login.tailscale.com/admin/users, click **Invite external users**, and either enter their emails or copy the invite link and send it on WhatsApp. Invites expire in 30 days. If you have "user approval" turned on in the admin console, approve them under Users after they accept.
3. Each family member: install **Tailscale** from the App Store / Play Store, open the invite link on the phone, sign in with any account they already have (Google, Apple, Microsoft, GitHub). Turn the toggle on.
4. On the phone, open `http://mihirpi:5000` (or `http://<tailscale-ip-of-pi>:5000`, from `tailscale ip -4` on the Pi). Tap "Add to Home Screen" in the browser so it behaves like an app.

That's it. The app itself doesn't change.

Invited users can see every device on your tailnet, including whatever runs whatsinmyfridge. That's fine for family. If you ever want to limit them to the Pi only, that's an ACL edit at https://login.tailscale.com/admin/acls, not an app change.

Battery on iPhone: Tailscale idles at a few percent per day when it is only used to reach a home device like this. The two things that actually drain phones are (1) routing all traffic through an **exit node**, so never turn that on, and (2) the occasional buggy release. If someone sees Tailscale near the top of Settings > Battery, update the app first. Anyone who wants zero background cost can open Tailscale, set VPN On Demand to "Do Nothing" for Cellular and Wi-Fi, and just flip the toggle on when they want to log.

### B. Cloudflare Tunnel (public URL, no app on phones)

Gives you a normal `https://logger.yourdomain.com` link that works from any browser. Free, but you need a domain in Cloudflare (roughly $10/year).

- Anyone with the link can reach the login page, so your only protection is username + 4-digit PIN. That's weak against a bot that guesses PINs. If you go this route, turn on **Cloudflare Access** (free for up to 50 users) in front of it so they must also pass an email one-time-code check.
- More setup than Tailscale: domain, `cloudflared` install, tunnel config, DNS.

Rough steps: install `cloudflared` on the Pi, `cloudflared tunnel login`, `cloudflared tunnel create logger`, route DNS to it, run it as a service pointing at `http://localhost:5000`. Cloudflare's docs walk through it.

### C. Port forwarding on your router + dynamic DNS

Works, free, no third party. Not recommended: it exposes a Flask app with a 4-digit PIN directly to the whole internet, your home IP changes so you need DDNS, and you'd want HTTPS in front of it. More work and more risk than A or B for zero benefit.

### D. Frontend on GitHub Pages, database on the Pi

No. GitHub Pages can only serve static files. The page would still have to call the Pi over the internet, so the Pi must be exposed anyway (back to A/B/C). You'd end up with two codebases (a JS frontend and a Pi API), CORS, token auth, and nothing simpler. It solves nothing and doubles the code.

### E. Database on GitHub

No. GitHub is not a database. Every tap would have to be a commit, every phone would need a write token to your repo, concurrent edits conflict, and there's no server to run login. If the repo is public your logs are public.

## 3. Using the app

- **First visit:** tap "Create an account", pick a username and a 4-digit PIN. There's always a "Create account" link on the login page, and a "Log out" link at the top when logged in.
- **Home:** tap "+ New category" to create an activity with a name, optional note, color and icon. Tap a category to log it. The "Logging for" date defaults to today (your phone's timezone); change it before tapping to log a different day. After logging, a "Change / undo" link lets you fix the date or delete it. The pencil next to a category edits or deletes it.
- **Calendar:** month grid with the icons of everything logged under each day. The dropdown at the top filters to one category. Tap a day to see its logs, edit their date/note, delete them, or log more for that day.
- **Chart:** pick a category (or all) and either "Last 30 days" or a specific month. Bars show logs per day, colored by category, with a per-category total underneath.

## Notes

- PINs are stored hashed. Sessions last a year, so you log in once per phone.
- Timezone: the home page uses your phone's date for "today". The chart's "last 30 days" and the calendar's "today" marker use the Pi's clock. Set the Pi to your timezone with `sudo timedatectl set-timezone America/New_York` (or whichever you use).
- Forgot a PIN? There's no reset flow. On the Pi: `sqlite3 data/logger.db "DELETE FROM users WHERE username='name';"` deletes the user and their data, then re-register. Or ask me to add a reset.
