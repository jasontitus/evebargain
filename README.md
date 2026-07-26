# EVE Bargain - Regional Market Arbitrage Alerts

## What Is This?

You know how the in-game market browser only shows you prices in your current region? And you know how some backwater region might have a Damage Control II listed for half what it goes for in Jita -- but you'd never know unless you happened to open the market and check?

**EVE Bargain watches for you.**

It runs on a second monitor (or your phone browser) while you play. Every time you jump into a new region -- whether you're roaming through lowsec, chain-rolling wormholes, or just autopiloting across the map -- it automatically checks: *"Is anything here selling for way less than Jita?"*

If it finds a deal, you hear a chime. You glance over, see that someone in Aridia is selling Conflagration L for 20% under Jita price, and you decide whether it's worth buying a stack and hauling it back. Or you ignore it and keep flying. That's it.

**You pick what matters to you.** Only care about ships and ammo? Track those. Want to watch for cheap manufacturing materials or underpriced SKINs? Add those categories. Set your own threshold -- maybe you only want to hear about 15%+ discounts, or maybe 10% is enough if the profit per unit is high.

This is built for the player who's already traveling. You're not going out of your way to find deals -- you're just getting told about them when they're right in front of you.

## How It Works

1. **Log in** with your EVE Online account via SSO
2. **Configure** which item categories to track (ships, ammo, modules, SKINs, etc.) and your discount threshold
3. **Play the game** -- the app polls your location every 30 seconds
4. **Get alerted** when you enter a region with items priced below Jita via desktop notification and chime

## Features

- **Real-time location tracking** via EVE ESI API
- **Automated price comparison** against Jita (The Forge) on region change
- **Configurable alerts** -- set discount threshold (5-50%), minimum profit, minimum volume
- **Category filtering** -- Ships, Ammunition, Modules, Drones, SKINs, Materials, Blueprints, Implants, Planetary
- **Live WebSocket notifications** -- instant alerts pushed to your browser
- **Desktop notifications + sound** -- don't miss a deal even on a second monitor
- **Sortable deal table** -- browse all opportunities by discount, profit, or name
- **Region browsing** -- check any of the 70 k-space markets from a dropdown without flying there; alerts keep tracking your real location

## Tech Stack

- **Backend:** Python / FastAPI / SQLAlchemy / APScheduler
- **Frontend:** React / TypeScript / Vite / Zustand
- **Database:** SQLite (WAL mode for concurrent reads)
- **Auth:** EVE SSO OAuth2

## Prerequisites

1. **EVE Online Developer Application** -- Register at [EVE Developers](https://developers.eveonline.com/)
   - Create a new application
   - Add scope: `esi-location.read_location.v1`
   - Set callback URL: `http://localhost:8000/api/auth/callback`
   - Note your Client ID and Secret Key

   A `localhost` callback is fine -- EVE SSO allows it, no public URL or tunnel
   needed. Note the callback points at the **backend** port (8000), not the UI:
   the backend exchanges the OAuth code, then sends you to `FRONTEND_URL`. The
   URL registered here must match `EVE_CALLBACK_URL` in `.env` character for
   character, port included.

2. **Python 3.11+**

3. **Node.js 20.19+ or 22.12+** -- required by Vite 8; Node 18 will not run the
   frontend at all. `frontend/.nvmrc` pins a good version, so with
   [nvm](https://github.com/nvm-sh/nvm):

   ```bash
   cd frontend && nvm install && nvm use
   ```

## Quick Start

### 1. Clone and configure

```bash
git clone <repo-url>
cd evebargain
cp .env.example .env
# Edit .env with your EVE Client ID and Secret Key
```

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The backend starts at `http://localhost:8000`. On first boot it creates the SQLite database and tables automatically.

This port serves the **API only** -- there is no web interface on it. Confirm it is healthy with `http://localhost:8000/api/health`, and browse the endpoints at `http://localhost:8000/docs`. Open the app itself at the frontend URL in the next step.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend starts at `http://localhost:5173` with a proxy to the backend. **This is the URL to open in your browser** -- it serves the UI and forwards `/api` and `/ws` to port 8000.

### 4. Load Static Data

On first use, trigger the static data loader to populate item types from ESI:

```bash
# In a Python shell with the backend's venv active
python -c "
import asyncio
from app.database import async_session, init_db
from app.services.sde_loader import load_all_static_data
async def main():
    await init_db()
    async with async_session() as db:
        await load_all_static_data(db)
asyncio.run(main())
"
```

This fetches item categories, groups, and types from ESI. It takes a few minutes on first run but is cached in the database.

## Desktop Launcher (Linux)

Instead of starting both servers by hand, install a menu entry that boots the
stack and opens it in a browser tab:

```bash
./scripts/install-launcher.sh
```

This writes `~/.local/share/applications/evebargain.desktop` and installs the
icon under `~/.local/share/icons/hicolor`. Look for **EVE Bargain** in the
application menu; drag it to the panel or desktop to pin it. Right-click gives
**Stop EVE Bargain** and **View Logs**.

The launcher runs `scripts/evebargain`, which you can also call directly:

```bash
./scripts/evebargain start   # start whatever isn't already running, open a tab
./scripts/evebargain stop    # stop both servers
./scripts/evebargain logs    # tail both logs
```

It is idempotent -- if a server is already listening on its port it is left
alone and only the tab opens, so clicking the launcher twice won't spawn
duplicates. Logs go to `~/.local/state/evebargain/`. It prefers Brave
(Flatpak `com.brave.Browser`, then a native install) and falls back to
`xdg-open`.

Note that this runs the Vite dev server, which is the intended setup for
watching the market while you play. It is not a hardened production deployment.

## Docker

```bash
cp .env.example .env
# Edit .env with your credentials
docker compose up --build
```

- Frontend (open this one): `http://localhost:3000`
- Backend API: `http://localhost:8000`

The same EVE application works for both setups: keep the callback registered as
`http://localhost:8000/api/auth/callback`, since compose publishes the backend
on 8000 too.

Compose sets `DATABASE_URL` and `FRONTEND_URL` itself, overriding `.env` --
they describe this stack (database on the `db-data` volume, UI on port 3000)
rather than your machine. Everything else, including your EVE credentials, is
read from `.env`, which is optional here: without it the stack still starts and
the backend logs a warning that login will fail.

The database lives on the `db-data` volume and survives `--build`. To start
over from an empty database:

```bash
docker compose down -v
```

## Troubleshooting

**`{"detail":"Not Found"}` in the browser**

You are on the backend port. `http://localhost:8000` serves the API only -- the UI runs separately, at `http://localhost:5173` with `npm run dev`, or `http://localhost:3000` under Docker. The backend is fine if `http://localhost:8000/api/health` returns `{"status":"ok"}`.

**Login bounces to an EVE SSO error page**

`EVE_CLIENT_ID` / `EVE_SECRET_KEY` are not set. Put `.env` in the repo root (next to `docker-compose.yml`), not in `backend/`, and restart the backend -- it logs a warning at startup when the credentials are missing.

**`Vite requires Node.js version 20.19+ or 22.12+`**

Your Node is too old. Check with `node --version`, then upgrade -- with nvm,
`cd frontend && nvm install && nvm use`. If `nvm use` reports the right version
but the error persists, you have another terminal on the old Node: `nvm use`
applies per shell.

**Logging in dumps me on JSON instead of the app**

`FRONTEND_URL` does not match where you actually browse the UI. It defaults to
`http://localhost:5173`; set it to `http://localhost:3000` under Docker, or to
whatever port Vite picked if 5173 was taken.

**`Invalid redirect_uri` from EVE SSO**

The callback registered on your EVE developer application must match `EVE_CALLBACK_URL` exactly, including port -- `http://localhost:8000/api/auth/callback` by default.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API index -- version and where the UI lives |
| GET | `/api/health` | Health check |
| GET | `/api/auth/login` | Redirect to EVE SSO |
| GET | `/api/auth/callback` | OAuth callback handler |
| GET | `/api/auth/me` | Current user info |
| GET | `/api/config/` | Get user configuration |
| PUT | `/api/config/` | Update configuration |
| GET | `/api/config/categories` | List trackable categories |
| GET | `/api/market/deals` | Get arbitrage opportunities (`?region_id=` to browse elsewhere) |
| GET | `/api/market/regions` | K-space regions for the browse dropdown |
| POST | `/api/market/refresh` | Force market refresh |
| GET | `/api/alerts/` | Alert history |
| POST | `/api/alerts/{id}/dismiss` | Dismiss an alert |
| WS | `/ws/alerts` | Real-time alert WebSocket |

## Architecture

```
Browser <---> Frontend (React) <---> Backend (FastAPI)
                                         |
                                    ESI API (EVE Online)
                                         |
                                    SQLite Database
```

**Background Tasks (APScheduler):**
- Location polling: every 30s per active user, starting immediately on login
- Market data refresh: every 5 min per region
- Jita price pre-warming: every 5 min globally

Location polling is registered in the SSO callback, so **restarting the backend
stops polling until you log in again.** Deals still render from cached data,
but region changes won't be picked up.

**Market Comparison Pipeline:**
1. Location poller detects region change
2. Fetch all sell orders for the new region from ESI
3. Fetch/use cached Jita sell orders
4. Compare lowest prices, filter by user preferences
5. Push matching deals via WebSocket to the browser

## Being a Good ESI Citizen

A full Jita pull is ~275 pages / 273k sell orders. Left unchecked the app would
issue roughly 6,800 requests an hour for a single user, most of them returning
byte-identical data. Four things keep that in bounds:

- **Identifying User-Agent.** CCP asks third-party apps to say who they are so
  they can contact you about a misbehaving client rather than just blocking it.
  Set `ESI_CONTACT` in `.env` to an email or Discord handle. It is sent on every
  ESI request, so treat it as public.
- **Cache-freshness guard.** ESI serves market order pages from a ~300s cache.
  `update_market_cache` skips the fetch entirely when the stored rows are
  younger than `MARKET_CACHE_TTL`, which is what stops the periodic Jita refresh
  and the per-user scan from each pulling the same 275 pages every 5 minutes.
- **ETag conditional requests.** Public GETs send `If-None-Match`; a 304 costs
  no body transfer and reuses the decoded payload.
- **Bounded concurrency.** `ESI_MAX_CONCURRENCY` (default 10) caps in-flight
  requests so a paginated pull can't open hundreds of sockets at once.

The manual **Refresh** button forces a refetch of your *local* region only.
Jita is deliberately left on the freshness guard so repeated clicks can't drag
275 pages along with them.

ESI's hard limit is an *error* rate limit, surfaced via
`X-Esi-Error-Limit-Remain` and a 420 response; `esi_client.py` backs off and
retries once when it sees one. Successful requests are not capped by a
documented rate, but that is not licence to hammer it.

For reference, measured against live ESI: there are **114 regions**, and
fetching page 1 of every one of them totals **1,210 pages** for a complete
all-region sweep. Only 6 regions exceed 50 pages (The Forge 274, Domain 128,
Sinq Laison 92, Heimatar 85, Lonetrek 60, Metropolis 53); 88 regions are 5
pages or fewer.
