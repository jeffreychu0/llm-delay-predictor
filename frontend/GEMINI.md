## Project: LLM Delay Predictor
This project is a Vite + React project that attempts to predict the amount of delays that a given MTA Line will experience.

A List of all subway stations, along with where each station is geolocated, is stored in /stations.csv

## Requirements:

Rendering:
- The User must first select their desired train line  (i.e., the 1 Train line or the D Train line)
- The user must type in two MTA stations on that line (- Currently, we are limiting the user selections to two stations on one train line.)
- Using the information stored in the stations.csv file, all subway stations on a given train line should be drawn, as well as the train line itself (Drawn via a UI layer)
- The currently selected MTA line should be displayed using a map, this will be rendered using the leaflet npm library (npm install leaflet) (https://leafletjs.com/reference.html)


Predictions:
- Currently, the predictions are being stored in an API that we control. The Frontend should periodically request this API (As of now, use dummy information). This should be done every 30 seconds

## Page Structure:
This describes the structure of the frontend. We are using a basic Vite + React setup, as well as React Router to describe the page routes

main.jsx - Describes the routes of the page using react router. 
Layout.jsx - Describes the layout of the page (Header and Page content)
/pages/ - all of the rest of the main pages

## Coding Style

- Use 2 spaces for indentation.
- Prefix interface names with `I` (for example, `IUserService`).
- Always use strict equality (`===` and `!==`).
- Prefer to use Typescript for scripts that do not interact with react
