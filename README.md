# EVE Bargain - Regional Market Arbitrage Alerts

A companion app for EVE Online that tracks your character's location across regions and alerts you when items are priced significantly below Jita market value -- enabling opportunistic arbitrage for players who travel frequently through wormholes and across New Eden.

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

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend starts at `http://localhost:5173` with a proxy to the backend.

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

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
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
