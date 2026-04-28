# To run code in /backend/src

## To run FASTAPI:

python -m uvicorn api.fast_api:app --host 127.0.0.1 --port 8000

## Chatbot API key

Create a `.env` file in `backend/src` and add your Gemini key there:

GOOGLE_API_KEY=your_key_here

The chatbot loader reads `GOOGLE_API_KEY` automatically when `api.fast_api` imports `chatbot.py`.

If you prefer, `GEMINI_API_KEY` also works with the Google GenAI client, but this codebase checks `GOOGLE_API_KEY` first.

## Stop IDs used by the API

The delay endpoints expect GTFS stop IDs like `R01`, `A02S`, or `D43N`.
The numeric `Station ID` values in `stations.csv` are not valid for `/delays/estimate` unless you map them to GTFS stop IDs first.

## To run test DB:

python test.py

## To run main DB collection

python main.py

## to run main.py visualization (while executing)

python delay_dashboard.py

