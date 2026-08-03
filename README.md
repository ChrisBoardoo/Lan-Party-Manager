<div align="center">

<img src="assets/images/favicon_LPM.png" alt="LAN Party Manager logo" width="200" height="200" />

# LAN Party Manager

**Self-hosted event management for LAN parties** — crew invites, tournaments, treasury,
media, and live streams, all running on hardware you own. From a Raspberry Pi to a NUC.

[![Version](https://img.shields.io/badge/version-1.0.0--rc6-FF3D00?style=flat-square)](#)
[![License](https://img.shields.io/badge/license-GPL--2.0-4C566A?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-amd64%20%7C%20arm64%20(Pi%204%2F5)-555?style=flat-square)](#)
[![Docker](https://img.shields.io/badge/Docker-multi--arch-2496ED?style=flat-square&logo=docker&logoColor=white)](https://hub.docker.com/r/crosswax/lanpartymanager-backend)
[![i18n](https://img.shields.io/badge/i18n-EN%20%7C%20FR-3B82F6?style=flat-square)](#localization)

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://www.sqlite.org/)

`RC 1.0.0`

</div>

---

A single, private, self-hosted app for everything a LAN party needs: gate registration behind
per-event invite codes, RSVP with arrival/departure dates, run single-elimination and round-robin
tournaments, split shared costs pro-rata, curate Twitch streams, collect a shared photo/video
gallery, and keep a full activity and audit trail — all in **English and French**. No cloud account,
no telemetry, no subscription. Your crew's data stays on your box.

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Development](#development)
- [API Reference](#api-reference)
- [Roles & Permissions](#roles--permissions)
- [Pro-Rata Cost Splitting](#pro-rata-cost-splitting)
- [Troubleshooting](#troubleshooting)
- [Desktop App (Windows)](#desktop-app-windows)
- [Project Structure](#project-structure)
- [Localization](#localization)
- [License](#license)

---

## Features

| | |
|---|---|
| **Flexible Sign-In** | Log in with **either your nickname or your email**; optional **Discord SSO** for one-click sign-in and registration; self-service **forgot/reset password** by email (SMTP). Players link/unlink Discord from their profile; admins configure it in Settings. |
| **Crew Management** | Registration gated by a per-event invite code (6-char, seats tied to event capacity); user profiles, t-shirt sizes, WebP avatar uploads, public player profile pages. |
| **LAN Party Calendar** | Schedule events with dates, location, description, and optional capacity cap; RSVP with arrival/departure dates bounded to the event window and a live attendee count; QR-shareable invite code per event; **add-to-calendar** (Google Calendar link or `.ics` download) per event. |
| **Planning (Calendar View)** | Propose games for an event and **approval-vote on the hours** to play them on a day × hour heatmap — bounded by each player's RSVP window — then an organizer **locks** the schedule. Two independent toggles (members can propose / vote). Opt-in. |
| **Gear / BYO** | Per-event "who's bringing what": members **pledge** kit they're hauling in, admins post **requests** ("need a 4th monitor") a member can **claim**, and a personal gear locker carries a member's usual kit into the next event in one tap. Opt-in. |
| **Packing Checklist** | A **private**, per-member packing checklist for each event — 9 pre-filled items (computer, screen, cables, headset, …) plus up to 10 custom fields, with one-tap carryover of "your usual list" from the last event. Nobody but the owner can ever see it, not even an admin. Opt-in. |
| **Treasury** | Expense tracking by category, automatic **pro-rata cost splitting** based on attendance nights, P2P settlement, and one-click CSV export. |
| **Prizes** | Showcase per-event prizes (photo + description) for tournament winners. Enabling Prizes hides Treasury — crews giving out prizes don't usually split expenses. Opt-in. |
| **Sponsors** | Sponsor banners (image or video) with a click-through link, shown on the event, tournaments, and player profile pages. Opt-in. |
| **Arena / Tournaments** | Team or solo/individual events; **single-elimination brackets and round-robin** (W/L/D/Pts standings); per-team seeding; live score tracking; **self-service phone score reporting** (players report, organizer confirms); full-screen bracket view for projecting. |
| **Live Streams** | Twitch channel **and clip** embeds; live status + viewer count via the Twitch Helix API; optional chat iframe. |
| **Media Gallery** | Shared photo/video vault; event-tagged uploads; **emoji reactions**; admin bulk delete; ffmpeg-generated video thumbnails; inline lightbox. |
| **My Setup** | A member's gaming PC showcase on their profile — components, custom fields, up to 5 photos, emoji reactions from crewmates — with an optional public share link they mint and revoke themselves. Opt-in. |
| **Post-Event Recap** | Auto-generated highlight page for a finished event — champion, MVP, nights stayed, best photos, spend, and badges — derived on read from every other feature, nothing duplicated. Optional public share link (never includes money). Opt-in. |
| **Kiosk / Big Screen** | An ambient, read-only projector display for the LAN room, authorized by a revocable token (no personal login on the shared screen). Rotates through activity, standings, streams, and the planning schedule. Opt-in. |
| **Activity & Hall of Fame** | Dashboard feed of the 20 most recent events, plus a player win-rate leaderboard derived from completed tournaments. |
| **Announcements & Presence** | Admin **PA banner** (info/alert, auto-expiry, optional Discord fan-out) shown across the app; the HUB roster shows **who's online right now** via a lightweight browser heartbeat. |
| **Audit Log** | Admin-only trail of sensitive actions (event/tournament create & delete) with actor and timestamp. |
| **Admin Settings** | Twitch + Discord SSO credentials, SMTP (password-reset email), currency, per-feature opt-in/opt-out toggles, and a one-click DB + uploads backup as `tar.gz`. |
| **Role-Based Access** | Admin, Treasurer, and User roles enforced per route — not just hidden in the UI. |

---

## Tech Stack

| Layer     | Technology                                                              |
|-----------|-------------------------------------------------------------------------|
| Backend   | Python 3.11, FastAPI, SQLAlchemy 2, SQLite (WAL mode), Alembic migrations |
| Auth      | JWT (HS256), Bcrypt passwords, optional Discord OAuth2 SSO              |
| Frontend  | React 18, TypeScript, Tailwind CSS, Vite                                |
| Runtime   | Docker Compose, Nginx (frontend + static files), Uvicorn (API)         |
| Media     | Pillow (image processing), ffmpeg (video thumbnails)                    |
| External  | Twitch Helix API + Discord OAuth2 via httpx (optional, admin-configured) |

Multi-arch images are published for `linux/amd64` and `linux/arm64`, so the same stack runs on a
Raspberry Pi 4/5 or an x86 server without modification.

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2
- Ports `3001` and `8000` free on your host

### Option A — Pull from Docker Hub (fastest, no build step)

```bash
# 1. Create a working directory
mkdir lanpartymanager && cd lanpartymanager
mkdir -p data uploads

# 2. Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  backend:
    image: crosswax/lanpartymanager-backend:latest
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads
    environment:
      SECRET_KEY: change-me-to-a-long-random-string
      DATABASE_URL: sqlite:///./data/lanparty.db
      UPLOAD_DIR: /app/uploads
    restart: unless-stopped

  frontend:
    image: crosswax/lanpartymanager-frontend:latest
    ports:
      - "3001:80"
    volumes:
      - ./uploads:/app/uploads
    depends_on:
      - backend
    restart: unless-stopped
EOF

# 3. Run
docker compose up -d
```

> Images on Docker Hub: [`crosswax/lanpartymanager-backend`](https://hub.docker.com/r/crosswax/lanpartymanager-backend) · [`crosswax/lanpartymanager-frontend`](https://hub.docker.com/r/crosswax/lanpartymanager-frontend)

### Option B — Build from source

```bash
git clone <your-repo-url>
cd LANPARTYMANAGER
echo "SECRET_KEY=change-me-to-a-long-random-string" > .env
docker compose up --build
```

First build takes ~3–5 minutes (installs Python deps + ffmpeg, compiles the React app).

### Access

| Service  | URL                          |
|----------|------------------------------|
| Frontend | http://localhost:3001        |
| API      | http://localhost:8000        |
| API docs | http://localhost:8000/docs   |

> **Important:** always set a strong `SECRET_KEY` — it signs all JWT tokens.

### First admin account

Open http://localhost:3001/register — the **first** account registered automatically becomes
**admin**. Every subsequent registration requires an invite code generated from an event.

### Discord SSO (optional)

To let players sign in with Discord:

1. Create an application at [discord.com/developers](https://discord.com/developers/applications) → **OAuth2**. Copy the **Client ID** and **Client Secret** (the app requests the `identify` + `email` scopes automatically).
2. In LPM, go to **Settings** (admin): set `app_base_url` (in the Email section), then under **Discord sign-in (SSO)** paste the Client ID + Secret and enable it. The panel shows the exact redirect URI.
3. In Discord → **OAuth2 → Redirects**, add that exact URI — `{app_base_url}/api/auth/discord/callback` — and **Save Changes**.

A "Continue with Discord" button then appears on the Login and Register pages. New Discord users
still need a valid event invite code (except the first/admin user); existing accounts are auto-linked
when Discord's verified email matches. Credentials live in the database (`app_settings`), never in `.env`.

---

## Configuration

### Docker Compose reference

```yaml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data        # SQLite database (persisted)
      - ./uploads:/app/uploads  # Avatars, media, thumbnails (persisted)
    environment:
      SECRET_KEY: ${SECRET_KEY:-lanparty-secret-CHANGE-ME}
      DATABASE_URL: sqlite:///./data/lanparty.db
      UPLOAD_DIR: /app/uploads

  frontend:
    build: ./frontend
    ports:
      - "3001:80"
    volumes:
      - ./uploads:/app/uploads  # Nginx serves uploads directly (no Python hop)
    depends_on:
      - backend
```

### Environment variables

| Variable       | Default                        | Description                                  |
|----------------|--------------------------------|----------------------------------------------|
| `SECRET_KEY`   | `lanparty-secret-CHANGE-ME`    | JWT signing secret — **change this**         |
| `DATABASE_URL` | `sqlite:///./data/lanparty.db` | SQLAlchemy connection string                 |
| `UPLOAD_DIR`   | `/app/uploads`                 | Directory for avatars, media, and thumbnails |

> Twitch and Discord credentials are **not** environment variables — they're stored in the database
> via the admin **Settings** page, so they survive rebuilds and never land in `.env`.

### Persisted data

These host directories are mounted as Docker volumes and survive container restarts/rebuilds:

```
./data/      → SQLite database (lanparty.db)
./uploads/   → Avatars, media files, and video thumbnails
  ├── media/       uploaded images and videos
  └── thumbnails/  auto-generated video thumbnails (ffmpeg)
```

Create them before first run if you want explicit ownership:

```bash
mkdir -p data uploads
```

### Manual build (without Compose)

<details>
<summary>Backend / frontend <code>docker build</code> commands</summary>

```bash
# Backend
cd backend
docker build -t lanparty-backend .
docker run -p 8000:8000 \
  -e SECRET_KEY=your-secret \
  -v $(pwd)/../data:/app/data \
  -v $(pwd)/../uploads:/app/uploads \
  lanparty-backend

# Frontend
cd frontend
docker build -t lanparty-frontend .
docker run -p 3001:80 \
  -v $(pwd)/../uploads:/app/uploads \
  lanparty-frontend
```

> The uploads volume mount is required so Nginx can serve avatars, media, and thumbnails directly.

</details>

---

## Development

Run the stack without Docker for a fast edit/reload loop.

### Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

> Without Docker, `ffmpeg` must be installed for video thumbnail generation (`apt install ffmpeg` / `brew install ffmpeg`).

### Frontend

```bash
cd frontend
npm install
npm run dev   # Vite dev server on http://localhost:5173
```

> The Vite dev server proxies `/api` to `http://localhost:8000` — no CORS config needed locally.

### Tests & checks

```bash
cd backend && pytest                       # backend test suite
python scripts/check_i18n_parity.py        # EN/FR translation parity
python scripts/check_version_sync.py       # version consistency across files
```

---

## API Reference

All routes are prefixed `/api`. Interactive docs live at `/docs` (Swagger) and `/redoc`.
List endpoints support `?limit=` and `?offset=` pagination.

### Auth

| Method | Path                          | Auth     | Description                                                             |
|--------|-------------------------------|----------|------------------------------------------------------------------------|
| POST   | `/api/auth/register`          | Public   | Register (invite code + arrival/departure dates required after first user; auto-RSVPs into that event) |
| POST   | `/api/auth/login`             | Public   | Login with `identifier` (**nickname or email**) + password, returns JWT |
| GET    | `/api/auth/me`                | Required | Current user info                                                      |
| GET    | `/api/auth/invite-required`   | Public   | Returns `{ required: bool }`                                           |
| POST   | `/api/auth/forgot-password`   | Public   | Email a password-reset link if the address matches an account (SMTP)  |
| POST   | `/api/auth/reset-password`    | Public   | Set a new password from a valid reset token                           |
| GET    | `/api/auth/discord/config`    | Public   | Returns `{ enabled: bool }` — is Discord SSO configured?              |
| GET    | `/api/auth/discord/authorize` | Public   | Begin Discord login/registration (`?code=` optional invite)           |
| GET    | `/api/auth/discord/link`      | Required | Begin linking Discord to the current account                          |
| DELETE | `/api/auth/discord/link`      | Required | Unlink Discord (refused if the account has no password)               |
| GET    | `/api/auth/discord/callback`  | Public   | OAuth2 redirect target — completes login/link, hands back the JWT     |

### Users

| Method | Path                     | Auth          | Description                    |
|--------|--------------------------|---------------|--------------------------------|
| GET    | `/api/users/`            | Any           | List all users                 |
| GET    | `/api/users/{id}`        | Any           | Get user                       |
| PUT    | `/api/users/{id}`        | Self or Admin | Update profile                 |
| POST   | `/api/users/{id}/avatar` | Self or Admin | Upload avatar (saved as WebP)  |
| PUT    | `/api/users/{id}/role`   | Admin only    | Change user role               |

### Expenses

| Method | Path                    | Auth              | Description                                                        |
|--------|-------------------------|-------------------|-------------------------------------------------------------------|
| GET    | `/api/expenses/`        | Any               | List expenses                                                     |
| GET    | `/api/expenses/prorata` | Any               | Pro-rata breakdown (`?event_id=` optional, defaults to soonest upcoming event) |
| POST   | `/api/expenses/`        | Treasurer / Admin | Create expense                                                   |
| PUT    | `/api/expenses/{id}`    | Treasurer / Admin | Update expense                                                   |
| DELETE | `/api/expenses/{id}`    | Treasurer / Admin | Delete expense                                                   |

### Prizes

*Opt-in — 404 for non-admins while the `prizes` flag is off; enabling it hides Treasury.*

| Method | Path                        | Auth       | Description                        |
|--------|-----------------------------|------------|-------------------------------------|
| GET    | `/api/prizes/`              | Any        | List prizes (`?event_id=` filter)   |
| POST   | `/api/prizes/`              | Admin only | Create a prize                      |
| POST   | `/api/prizes/{id}/photo`    | Admin only | Upload/replace the prize photo      |
| PUT    | `/api/prizes/{id}`          | Admin only | Update title/description            |
| DELETE | `/api/prizes/{id}`          | Admin only | Delete a prize                      |

### Sponsors

*Opt-in — 404 for non-admins while the `sponsors` flag is off.*

| Method | Path                          | Auth       | Description                                    |
|--------|-------------------------------|------------|-------------------------------------------------|
| GET    | `/api/sponsors/`              | Any        | List sponsors (`?event_id=` filter)             |
| GET    | `/api/sponsors/active`        | Any        | Sponsors for the current/soonest event          |
| POST   | `/api/sponsors/`              | Admin only | Create a sponsor                                |
| POST   | `/api/sponsors/{id}/banner`   | Admin only | Upload a banner (image or `.webm` video)        |
| PUT    | `/api/sponsors/{id}`          | Admin only | Update name/link/sort order                     |
| DELETE | `/api/sponsors/{id}`          | Admin only | Delete a sponsor                                |

### Tournaments

| Method | Path                                         | Auth              | Description                              |
|--------|----------------------------------------------|-------------------|------------------------------------------|
| GET    | `/api/tournaments/`                          | Any               | List tournaments                         |
| GET    | `/api/tournaments/hall-of-fame`              | Any               | Player win-rate leaderboard              |
| GET    | `/api/tournaments/{id}`                      | Any               | Tournament detail                        |
| GET    | `/api/tournaments/{id}/standings`            | Any               | Round-robin standings (W/L/D/Pts)        |
| POST   | `/api/tournaments/`                          | Organizer+        | Create tournament                        |
| PUT    | `/api/tournaments/{id}`                      | Organizer / Admin | Update name or status                    |
| DELETE | `/api/tournaments/{id}`                      | Organizer / Admin | Delete tournament                        |
| POST   | `/api/tournaments/{id}/teams`                | Any               | Add team                                 |
| PUT    | `/api/tournaments/{id}/teams/{team_id}`      | Any               | Update team                              |
| PATCH  | `/api/tournaments/{id}/teams/{team_id}/seed` | Organizer / Admin | Set team seed                            |
| DELETE | `/api/tournaments/{id}/teams/{team_id}`      | Any               | Remove team                              |
| POST   | `/api/tournaments/{id}/generate-brackets`    | Organizer / Admin | Generate brackets / round-robin schedule |
| PUT    | `/api/tournaments/{id}/matches/{match_id}`   | Organizer / Admin | Update score / advance                   |

### LAN Events

| Method | Path                                 | Auth       | Description                                                           |
|--------|--------------------------------------|------------|----------------------------------------------------------------------|
| GET    | `/api/events/`                       | Any        | List all events (enriched with RSVP + my dates)                      |
| POST   | `/api/events/`                       | Admin only | Create event (optional capacity)                                    |
| PUT    | `/api/events/{id}`                   | Admin only | Update event                                                        |
| DELETE | `/api/events/{id}`                   | Admin only | Delete event                                                        |
| POST   | `/api/events/{id}/rsvp`              | Any        | RSVP "in" with `{arrival_date, departure_date}` bounded to the event window |
| DELETE | `/api/events/{id}/rsvp`              | Any        | Set RSVP status = "out"                                             |
| GET    | `/api/events/{id}/invite`            | Admin only | Get this event's invite code (or `null`)                            |
| POST   | `/api/events/{id}/invite`            | Admin only | Generate/regenerate this event's invite code                        |
| DELETE | `/api/events/{id}/invite`            | Admin only | Revoke this event's invite code                                     |
| GET    | `/api/events/invite/validate/{code}` | Public     | Validate a code — `{valid, full, event_title, event_start, event_end}` |

### Planning (Calendar View)

*Opt-in — 404 for non-admins while the `planning` flag is off; per-event `can_propose`/`can_vote` toggles further gate individual endpoints.*

| Method | Path                                    | Auth | Description                                              |
|--------|------------------------------------------|------|-----------------------------------------------------------|
| GET    | `/api/planning/events/{event_id}`         | Any  | Full planning board — proposals, blocks, votes           |
| POST   | `/api/planning/events/{event_id}/blocks`  | Any  | Propose a game for a day × hour block                    |
| DELETE | `/api/planning/blocks/{block_id}`         | Any  | Remove a proposed block                                  |
| PUT    | `/api/planning/blocks/{block_id}/votes`   | Any  | Cast/change your approval vote, bounded by your RSVP window |
| POST   | `/api/planning/blocks/{block_id}/lock`    | Any  | Organizer locks a block as the final pick                |
| POST   | `/api/planning/blocks/{block_id}/unlock`  | Any  | Unlock a previously locked block                          |

### Gear / BYO

*Opt-in — 404 for non-admins while the `gear` flag is off.*

| Method | Path                                        | Auth       | Description                                                    |
|--------|----------------------------------------------|------------|-------------------------------------------------------------------|
| GET    | `/api/gear/events/{event_id}`                 | Any        | The whole gear list for one event (pledges + open requests)       |
| GET    | `/api/gear/suggestions`                       | Any        | Your personal gear locker — everything you've pledged before      |
| POST   | `/api/gear/events/{event_id}/items`           | Any        | Pledge kit you're bringing                                        |
| POST   | `/api/gear/events/{event_id}/requests`        | Admin only | Post a "we need X" request a member can claim                     |
| POST   | `/api/gear/events/{event_id}/carryover`       | Any        | Bulk-pledge your usual kit from your gear locker (idempotent)      |
| POST   | `/api/gear/items/{item_id}/claim`             | Any        | Claim an open request                                              |
| POST   | `/api/gear/items/{item_id}/unclaim`           | Any        | Release a claimed request                                          |
| PUT    | `/api/gear/items/{item_id}`                   | Any        | Update a pledge/request                                            |
| DELETE | `/api/gear/items/{item_id}`                   | Any        | Remove a pledge/request                                            |

### Packing Checklist

*Opt-in — 404 for non-admins while the `checklist` flag is off. **Private by design:** every route resolves "the caller's own checklist" — there is no route that can read or write another member's list, not even for an admin.*

| Method | Path                                              | Auth | Description                                                     |
|--------|-----------------------------------------------------|------|-------------------------------------------------------------------|
| GET    | `/api/checklist/events/{event_id}`                    | Any  | Your checklist for this event (empty shape if unsaved)            |
| PUT    | `/api/checklist/events/{event_id}`                    | Any  | Save the 9 fixed items + up to 10 custom fields (replace-all)     |
| GET    | `/api/checklist/suggestions`                          | Any  | Your most recent non-empty checklist from another event           |
| POST   | `/api/checklist/events/{event_id}/carryover`          | Any  | Merge your usual list into this event's checklist (safe to repeat) |

### Live Streams

| Method | Path                       | Auth          | Description                             |
|--------|----------------------------|---------------|-----------------------------------------|
| GET    | `/api/streams/`            | Any           | List streams                            |
| GET    | `/api/streams/live-status` | Any           | Fetch live status from Twitch Helix API |
| POST   | `/api/streams/`            | Any           | Add stream (channel name or clip URL)   |
| PUT    | `/api/streams/{id}`        | Owner / Admin | Update stream                           |
| DELETE | `/api/streams/{id}`        | Owner / Admin | Remove stream                           |

### Media

| Method | Path                     | Auth          | Description                                            |
|--------|--------------------------|---------------|--------------------------------------------------------|
| GET    | `/api/media/`            | Any           | List media (`?event_id=` filter supported)             |
| POST   | `/api/media/upload`      | Any           | Upload image or video (max 100 MB); ffmpeg thumbnails  |
| POST   | `/api/media/bulk-delete` | Admin only    | Delete multiple items by ID list                       |
| DELETE | `/api/media/{id}`        | Owner / Admin | Delete media item                                      |

### My Setup

*Opt-in — 404 while the `setup` flag is off. Every route that writes is `/me` — there is no `/{user_id}` write route, so the owner-only rule is enforced by the URL space itself, not a role check.*

| Method | Path                              | Auth          | Description                                                        |
|--------|------------------------------------|---------------|----------------------------------------------------------------------|
| GET    | `/api/setup/shared`                 | Public (token) | A setup fetched by its public share token — no login, rate-limited |
| GET    | `/api/setup/me`                     | Any           | Your own setup (empty shape if unsaved)                              |
| PUT    | `/api/setup/me`                     | Any           | Save the 14 components + custom fields                               |
| POST   | `/api/setup/me/photos`              | Any           | Add a photo (up to 5)                                                 |
| PATCH  | `/api/setup/me/photos/{photo_id}`   | Any           | Caption a photo (blank clears it)                                    |
| DELETE | `/api/setup/me/photos/{photo_id}`   | Any           | Delete a photo                                                        |
| GET    | `/api/setup/me/share`               | Any           | Your current public share link, if any                               |
| POST   | `/api/setup/me/share`               | Any           | Mint/rotate your public share link                                   |
| DELETE | `/api/setup/me/share`               | Any           | Revoke your public share link                                        |
| GET    | `/api/setup/{user_id}`              | Any           | View another member's setup in-app                                    |
| POST   | `/api/setup/{user_id}/react`        | Any           | React to a member's rig with an emoji                                 |

### Post-Event Recap

*Opt-in — 404 for non-admins while the `recap` flag is off. Financial figures are included for signed-in members (when Treasury is on) but never in the publicly shared version.*

| Method | Path                             | Auth       | Description                                                     |
|--------|------------------------------------|------------|--------------------------------------------------------------------|
| GET    | `/api/recap/shared`                 | Public (token) | A recap fetched by its public share token — no login, no money |
| GET    | `/api/recap/{event_id}`             | Any        | Full recap for a member — champion, MVP, nights, photos, spend    |
| GET    | `/api/recap/{event_id}/share`       | Admin only | Current public share link, if any                                 |
| POST   | `/api/recap/{event_id}/share`       | Admin only | Mint/rotate the event's public share link                         |
| DELETE | `/api/recap/{event_id}/share`       | Admin only | Revoke the event's public share link                              |

### Kiosk / Big Screen

*Opt-in — the `/summary` read is authorized only by a revocable kiosk token (constant-time compare), never a personal JWT, so it's safe to leave running on a shared projector.*

| Method | Path                     | Auth            | Description                                              |
|--------|---------------------------|-----------------|--------------------------------------------------------------|
| GET    | `/api/kiosk/admin`          | Admin only      | Current kiosk state (token minted? enabled?)                  |
| POST   | `/api/kiosk/admin/token`    | Admin only      | Generate/rotate the kiosk token (invalidates any old URL)     |
| DELETE | `/api/kiosk/admin/token`    | Admin only      | Clear the token — no kiosk URL works until a new one is minted |
| GET    | `/api/kiosk/summary`        | Public (token)  | Everything the projector display rotates through, in one poll |

### Announcements & Presence

| Method | Path                       | Auth       | Description                                                    |
|--------|-----------------------------|------------|-------------------------------------------------------------------|
| GET    | `/api/announcements/`         | Any        | Currently active announcements (expired ones filtered out)        |
| POST   | `/api/announcements/`         | Admin only | Post an announcement (optional Discord fan-out)                    |
| DELETE | `/api/announcements/{id}`     | Admin only | Delete/dismiss an announcement                                     |
| POST   | `/api/presence/ping`          | Any        | Browser heartbeat — powers the HUB roster's "who's online" list   |

### Settings, Activity, Audit & Backup

| Method | Path                  | Auth       | Description                                                                 |
|--------|-----------------------|------------|-----------------------------------------------------------------------------|
| GET    | `/api/settings/`      | Admin only | List all configurable settings                                             |
| PUT    | `/api/settings/{key}` | Admin only | Upsert a setting (twitch_client_id/secret, discord_oauth_enabled/client_id/client_secret, …) |
| GET    | `/api/activity/`      | Any        | Paginated activity feed (`?limit=`)                                        |
| GET    | `/api/audit/`         | Admin only | Paginated admin audit log                                                  |
| GET    | `/api/backup/export`  | Admin only | Download `tar.gz` of DB + uploads folder                                   |

---

## Roles & Permissions

| Role        | Capabilities                                                                             |
|-------------|------------------------------------------------------------------------------------------|
| `admin`     | Everything — user management, roles, invites, expenses, tournaments, settings, audit log |
| `treasurer` | Create / edit / delete expenses; view all data                                          |
| `user`      | View all data; manage own profile; RSVP to events; participate in tournaments           |

The first registered account is automatically promoted to `admin`.

---

## Pro-Rata Cost Splitting

Expenses are split proportionally by the number of nights each attendee is present:

```
person_nights(user) = departure_date - arrival_date
share(user)         = person_nights(user) / total_person_nights * total_expenses
```

Dates are set **per event**, not globally: RSVP "in" on the **LAN Party** page and confirm your
arrival/departure within that event's window to appear in its breakdown. The Treasury Pro-Rata tab
lets you pick which event to split (defaults to the soonest upcoming one) and export the result as CSV.

---

## Troubleshooting

**Port already in use** — change the host port in `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"   # backend
  - "3002:80"     # frontend
```

**Database reset**
```bash
docker compose down
rm -rf data/
docker compose up
```

**Rebuild after code changes**
```bash
docker compose up --build          # normal
docker compose build --no-cache    # from scratch
```

**View logs**
```bash
docker compose logs -f backend
docker compose logs -f frontend
```

**Discord "Invalid OAuth2 redirect_uri"** — the URI registered in the Discord portal must exactly
match `{app_base_url}/api/auth/discord/callback` (same scheme, host, port, no trailing slash), and
you must click **Save Changes** in Discord.

**ARM / Raspberry Pi** — the backend Dockerfile installs native Pillow libs (`libjpeg-dev`,
`zlib1g-dev`, `libpng-dev`) and `ffmpeg`, all available for ARM64 (Pi 4/5) via the standard Debian
repos. The build runs unmodified on ARM64.

---

## Desktop App (Windows)

A native Windows tray client for crews who'd rather not keep a browser tab open — same login, same
everything, unmodified, plus native notifications and background updates.

- **Same app, real window.** A [Tauri](https://tauri.app/) shell asks for your instance's server URL
  once (like picking a Slack workspace), then embeds the actual web app unmodified — no separate UI
  to build or keep in sync.
- **Stays signed in.** 30-day sliding-session tokens; no daily re-login.
- **Lives in the tray.** Minimizes instead of quitting; native Windows toast notifications for new
  tournaments, media, planning updates, and gear requests, with per-category toggles, and a click on
  a toast jumps straight to the relevant page.
- **Discord SSO** opens in your system browser rather than an embedded popup, and hands control back
  automatically once you're signed in.
- **Auto-updates itself** once installed — checks once per launch, no manual re-downloads.

Source lives in [`desktopapp/`](desktopapp/) — see [`desktopapp/README.md`](desktopapp/README.md) for
build/dev instructions. Installers aren't published yet; build and run from source for now:

```powershell
cd desktopapp
npm install
npm run dev
```

---

## Project Structure

```
LANPARTYMANAGER/
├── docker-compose.yml
├── data/                      # SQLite DB (auto-created, gitignored)
├── uploads/                   # Avatars, media, thumbnails (auto-created, gitignored)
│
├── backend/
│   ├── Dockerfile             # python:3.11-slim + Pillow libs + ffmpeg
│   ├── requirements.txt
│   ├── main.py                # FastAPI app, middleware, startup migrations
│   ├── database.py            # SQLAlchemy engine, session, SQLite WAL mode
│   ├── models.py              # ORM models
│   ├── schemas.py             # Pydantic request/response schemas
│   ├── auth.py                # JWT helpers, password hashing, unusable-password sentinel
│   ├── oauth_discord.py       # Discord OAuth2 client + signed-state (SSO) helpers
│   ├── activity.py            # Activity + audit log helpers
│   ├── prorata.py             # Pro-rata calculation logic (per event)
│   ├── alembic/               # Schema migrations (versioned)
│   ├── router_auth.py         # /api/auth (login by nickname/email, invite gate, Discord SSO, password reset)
│   ├── router_users.py        # /api/users
│   ├── router_expenses.py     # /api/expenses (prorata takes ?event_id=)
│   ├── router_prizes.py       # /api/prizes (opt-in, replaces Treasury when on)
│   ├── router_sponsors.py     # /api/sponsors (opt-in banners: image/webm + link)
│   ├── router_tournaments.py  # /api/tournaments (round-robin, standings, HoF, seeding)
│   ├── router_events.py       # /api/events (RSVP with dates, capacity, per-event invite codes)
│   ├── router_planning.py     # /api/planning (opt-in propose/vote/lock scheduling)
│   ├── router_gear.py         # /api/gear (opt-in BYO pledges, requests, gear locker carryover)
│   ├── router_checklist.py    # /api/checklist (opt-in, private per-event packing checklist)
│   ├── router_streams.py      # /api/streams (clip detection, Twitch live status)
│   ├── router_media.py        # /api/media (event filter, reactions, bulk delete)
│   ├── router_setup.py        # /api/setup (opt-in "My Setup" showcase + public share link)
│   ├── router_recap.py        # /api/recap (opt-in post-event highlight page + public share link)
│   ├── router_kiosk.py        # /api/kiosk (opt-in token-authorized projector display)
│   ├── router_announcements.py# /api/announcements (admin PA banner + Discord fan-out)
│   ├── router_presence.py     # /api/presence (browser heartbeat, who's online)
│   ├── router_settings.py     # /api/settings
│   ├── router_activity.py     # /api/activity
│   ├── router_audit.py        # /api/audit
│   ├── router_backup.py       # /api/backup
│   ├── mailer.py               # SMTP client — password-reset emails
│   └── discord_notify.py       # Discord webhook — announcements + RSVP reminders
│
├── frontend/
    ├── Dockerfile             # node:20-alpine build → nginx:alpine serve
    ├── nginx.conf             # SPA fallback, /api proxy, /uploads direct serve
    ├── package.json
    └── src/
        ├── App.tsx            # Router, auth context, shared Layout
        ├── contexts/          # AuthContext, AppConfigContext
        ├── lib/api.ts         # Axios client + all API functions
        ├── types/index.ts     # TypeScript interfaces
        ├── i18n/              # i18next setup + EN/FR locale files
        ├── components/
        │   ├── Navbar.tsx     # Responsive nav; feature-gated links; admin-only Settings + Audit
        │   ├── Footer.tsx
        │   ├── TournamentBracket.tsx
        │   ├── ProRataTable.tsx
        │   ├── ChecklistSection.tsx  # Packing checklist widget (event detail page)
        │   ├── AnnouncementsManager.tsx # Admin: compose/expire the PA banner
        │   ├── KioskManager.tsx      # Admin: mint/revoke the kiosk token
        │   ├── MediaReactions.tsx    # Emoji reactions (shared by Media and My Setup)
        │   └── ui/            # QRModal, Lightbox, DiscordButton, LanguageToggle, …
        └── pages/
            ├── Login.tsx          # Nickname/email + password, invite quick-entry, Discord SSO
            ├── Register.tsx       # Invite code validation, event context, RSVP dates, Discord SSO
            ├── ForgotPassword.tsx # Request a reset link by email
            ├── ResetPassword.tsx  # Set a new password from a reset token
            ├── DiscordComplete.tsx # OAuth2 landing — reads JWT from URL fragment, then redirects
            ├── Dashboard.tsx      # Crew roster, activity feed, hall of fame
            ├── Profile.tsx        # Avatar, t-shirt, roles, Discord link, My Setup, upcoming events
            ├── PlayerProfile.tsx  # A crewmate's public-in-app profile (setup, sponsors, stats)
            ├── Events.tsx         # RSVP with dates, capacity display, admin invite codes
            ├── EventDetailPage.tsx # Gear, Checklist, Planning, Sponsors for one event
            ├── Planning.tsx       # Day × hour propose/vote heatmap, organizer lock
            ├── Finances.tsx       # Expenses + pro-rata CSV export
            ├── Prizes.tsx         # Per-event prize board (photo + description)
            ├── Tournaments.tsx    # Round-robin standings + seeding UI
            ├── Streams.tsx        # Clip + channel embeds, live badge, chat toggle
            ├── Media.tsx          # Event filter, reactions, bulk delete, video thumbnails
            ├── RecapPage.tsx      # Post-event highlight page (+ SharedRecapPage, token-based)
            ├── SharedSetupPage.tsx # Public "My Setup" view via share token
            ├── Kiosk.tsx          # Token-authorized, read-only projector display
            ├── Settings.tsx       # Admin: Twitch + Discord SSO, SMTP, currency, feature toggles, backup
            └── AuditLog.tsx       # Admin: audit trail
│
└── desktopapp/                # Windows tray client (Tauri) — see "Desktop App" above
    ├── ui/                     # the embedded shell — server-URL screen, tray settings panel
    └── src-tauri/              # Rust: window/tray, activity polling, Discord SSO, auto-updater
```

---

## Localization

The entire UI ships in **English and French**, switchable from the navbar (and the Login/Register
pages for guests). Language choice persists to `localStorage`. Translations live in
`frontend/src/i18n/locales/{en,fr}.json`, and CI enforces full key parity between the two via
`scripts/check_i18n_parity.py`.

---

## License

Released under the **GNU General Public License v2.0** — see [LICENSE](LICENSE).
