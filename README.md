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

2. **Python 3.11+** and **Node.js 18+**

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

## Docker

```bash
cp .env.example .env
# Edit .env with your credentials
docker compose up --build
```

- Frontend (open this one): `http://localhost:3000`
- Backend API: `http://localhost:8000`

## Troubleshooting

**`{"detail":"Not Found"}` in the browser**

You are on the backend port. `http://localhost:8000` serves the API only -- the UI runs separately, at `http://localhost:5173` with `npm run dev`, or `http://localhost:3000` under Docker. The backend is fine if `http://localhost:8000/api/health` returns `{"status":"ok"}`.

**Login bounces to an EVE SSO error page**

`EVE_CLIENT_ID` / `EVE_SECRET_KEY` are not set. Put `.env` in the repo root (next to `docker-compose.yml`), not in `backend/`, and restart the backend -- it logs a warning at startup when the credentials are missing.

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
| GET | `/api/market/deals` | Get arbitrage opportunities |
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
- Location polling: every 30s per active user
- Market data refresh: every 5 min per region
- Jita price pre-warming: every 5 min globally

**Market Comparison Pipeline:**
1. Location poller detects region change
2. Fetch all sell orders for the new region from ESI
3. Fetch/use cached Jita sell orders
4. Compare lowest prices, filter by user preferences
5. Push matching deals via WebSocket to the browser
