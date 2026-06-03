# LLM Delay Predictor

Predicts transit delays using LLMs and historical GTFS data. This repository contains a Python backend that loads GTFS data, exposes APIs for predictions and history, a SQLite database to store MTA records, and a React frontend for interacting with predictions, maps, and dashboards.

## Features

- Load and supplement GTFS static data and historical arrival records
- Provide model-based delay predictions via HTTP API
- Interactive frontend with station selection, map display, and prediction visualization
- Simple dashboard and history viewer for analysis

## Repository Structure

- `backend/` — Python services and APIs
	- `src/` — application source
	- `db/` — GTFS loaders, DB initialization, and history data
	- `requirements.txt` — Python dependencies
- `frontend/` — React + Vite application
	- `src/` — React source components and pages
	- `public/` — static assets (stations.csv)

## Quick Start

Prerequisites:

- Python 3.10+ (recommended)
- Node.js 16+ and npm or yarn

Overview:

1. Download GTFS static data (see below) and populate `backend/src/db`.
2. Set up the backend environment and install Python dependencies.
3. Initialize or populate the backend database (see `backend/src/db`).
4. Start the backend API server and frontend dev server (see run steps below).

GTFS static data:

- Download the GTFS (GTFS Supplemented) text file from the MTA Developers site: https://www.mta.info/developers and choose the GTFS Supplemented package.
- Extract the downloaded GTFS file and place the extracted files under `backend/src/db` (the repo expects GTFS static files in that folder).

Sample database:

- If you want a ready-made sample `.db` file, you can download one here:

- https://drive.google.com/file/d/12Ru4VDAhpY-Zmme75HC7YWsTEwCh0Lb0/view?usp=sharing

Environment variables:

- Copy `.env-example` to `.env` in the `backend/src` folder and fill in the required values before running the services.

## Run (what to run)

To have the full app running you need to run three processes (they can run concurrently). All backend steps assume you are inside the `backend/src` directory (use `cd backend/src` first).

A) Run the backend main app (data initialization and retrieval) — from `backend/src`:

```powershell
cd backend/src
python main.py
```

B) Run the FastAPI server (ASGI) — from `backend/src`:

```powershell
cd backend/src
uvicorn api.fast_api:app --reload
```

C) Run the frontend dev server (from `frontend`):

```bash
cd frontend
npm install   # only once
npm run dev
```

## Backend (Python)

1. Create a virtual environment and install dependencies (run inside `backend/src`):

```powershell
cd backend/src
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Database initialization and data retrieval:

`backend/src/main.py` runs the repository's data initialization and retrieval workflow. Running `python backend/src/main.py` will initialize or populate the local SQLite database (where applicable) and import GTFS/static records into `backend/src/db`.

If you need to run a separate DB-initialization script directly, run it from `backend/src`:

```powershell
cd backend/src
python db/init_db.py
```

3. Run the FastAPI server (ASGI):

Start the HTTP API using `uvicorn` from `backend/src` pointed at the FastAPI app implementation in `api/fast_api.py`:

```powershell
cd backend/src
uvicorn api.fast_api:app --reload
```

Files of interest:

- `backend/src/main.py` — application launcher
- `backend/src/api/fast_api.py` — FastAPI routes and endpoints
- `backend/src/db/gtfs_static_loader.py` — GTFS static loader and supplement scripts

## Frontend (React + Vite)

1. Install dependencies and run the dev server:

```bash
cd frontend
npm install
npm run dev
```

2. Open the URL printed by Vite (usually `http://localhost:5173`).

Files of interest:

- `frontend/src/pages/ChatPage.jsx` — chat UI and interactions
- `frontend/src/components/PredictionDisplay.jsx` — visualization of predictions
- `frontend/src/utils/api.js` — frontend API helpers

## Usage

- Use the frontend to select a station and request predictions.
- The frontend calls backend endpoints to retrieve historical data and model predictions.
- For debugging or direct API access, issue HTTP requests to the backend endpoints (see `fast_api.py`).

## Testing

- Backend: there is a `backend/src/test.py` file for quick ad-hoc tests. Convert to a proper test suite as needed.
- Frontend: use standard `npm` test workflows if you add tests (e.g., `npm test`).

## Development Notes

- GTFS files are located under `backend/src/db/gtfs_supplemented/` for local static data.
- Historical arrival data is tracked in `backend/src/db/` (CSV & DB files).
- The repo mixes research scripts and production-ish APIs; separate concerns when hardening for production.
