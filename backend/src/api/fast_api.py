import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from matplotlib.pyplot import streamplot

from backend.src.chatbot import Chatbot
from db.init_db import DB_PATH, view_train_timetable, view_all_stops_from_route, view_static_timetable_for_stop


logger = logging.getLogger(__name__)

app = FastAPI(
	title="MTA Delay API",
	description="FastAPI endpoints for line and station delay analytics from mta.db",
	version="1.0.0",
)

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


def get_connection() -> sqlite3.Connection:
	conn = sqlite3.connect(f"{DB_PATH}/mta.db")
	conn.row_factory = sqlite3.Row
	return conn


def normalize_direction(direction: str) -> int:
	value = direction.strip().lower()
	if value in {"northbound", "north", "n", "0"}:
		return 0
	if value in {"southbound", "south", "s", "1"}:
		return 1
	raise HTTPException(status_code=400, detail="direction must be northbound or southbound")


def _stop_id_error_detail(line: str, from_stop_id: str, to_stop_id: str) -> str:
	return (
		f"from_stop_id/to_stop_id must be GTFS stop IDs for line {line}. "
		f"Examples look like 'R01', 'A02S', or 'D43N'. "
		f"Received from_stop_id={from_stop_id!r}, to_stop_id={to_stop_id!r}. "
		"If your frontend is passing numeric Station ID values from stations.csv, "
		"map them to GTFS Stop ID before calling /delays/estimate."
	)


@app.get("/health")
def health_check():
	return {"status": "ok"}


@app.get("/delays/average")
def get_average_delay_across_all_lines():
	conn = get_connection()
	cursor = conn.cursor()
	try:
		cursor.execute(
			"""
			SELECT AVG(delay_seconds) AS global_average_delay_seconds,
				   COUNT(*) AS observation_count
			FROM train_observations
			WHERE delay_seconds IS NOT NULL
			"""
		)
		overall = cursor.fetchone()

		cursor.execute(
			"""
			SELECT route_id,
				   AVG(delay_seconds) AS average_delay_seconds,
				   COUNT(*) AS observation_count
			FROM train_observations
			WHERE delay_seconds IS NOT NULL
			GROUP BY route_id
			ORDER BY route_id
			"""
		)
		per_line = [dict(row) for row in cursor.fetchall()]
	finally:
		conn.close()

	return {
		"global_average_delay_seconds": overall["global_average_delay_seconds"],
		"observation_count": overall["observation_count"],
		"per_line": per_line,
	}


@app.get("/stations/headsigns")
def get_station_headboard_signs(line: str | None = Query(default=None, description="Optional route_id filter, e.g. A")):
	conn = get_connection()
	cursor = conn.cursor()
	try:
		if line:
			cursor.execute(
				"""
				SELECT route_id,
					   headsign,
					   COUNT(*) AS samples
				FROM train_timetable
				WHERE route_id = ?
				  AND headsign IS NOT NULL
				  AND TRIM(headsign) <> ''
				GROUP BY route_id, headsign
				ORDER BY route_id, samples DESC, headsign
				""",
				(line,),
			)
		else:
			cursor.execute(
				"""
				SELECT route_id,
					   headsign,
					   COUNT(*) AS samples
				FROM train_timetable
				WHERE headsign IS NOT NULL
				  AND TRIM(headsign) <> ''
				GROUP BY route_id, headsign
				ORDER BY route_id, samples DESC, headsign
				"""
			)
		rows = [dict(row) for row in cursor.fetchall()]
	finally:
		conn.close()

	return {"line": line, "headsigns": rows}


@app.get("/delays/estimate")
def get_estimated_delay_between_stations(
	line: str,
	from_stop_id: str,
	to_stop_id: str,
	direction: str,
):
	direction_id = normalize_direction(direction)
	conn = get_connection()
	cursor = conn.cursor()
	try:
		cursor.execute(
			"""
			SELECT stop_id, stop_sequence
			FROM route_to_stop
			WHERE route_id = ?
			  AND direction_id = ?
			  AND stop_sequence IS NOT NULL
			ORDER BY stop_sequence
			""",
			(line, direction_id),
		)
		stops = [dict(row) for row in cursor.fetchall()]
		if not stops:
			raise HTTPException(status_code=404, detail="No stops found for line and direction")

    
		sequence_by_stop = {row["stop_id"]: row["stop_sequence"] for row in stops}

		def _resolve_stop(requested_id: str) -> str | None:
			# If it's already a route_to_stop key, return it.
			if requested_id in sequence_by_stop:
				return requested_id

			# Try appending directional suffix (N for northbound(0), S for southbound(1)).
			suffix = "N" if direction_id == 0 else "S"
			cand = f"{requested_id}{suffix}"
			if cand in sequence_by_stop:
				return cand

			# If requested_id is a GTFS-style id (like 'M19'), map via stop_name
			cursor.execute(
				"SELECT stop_name FROM stops WHERE stop_id = ? LIMIT 1",
				(requested_id,),
			)
			row = cursor.fetchone()
			if row:
				stop_name = row["stop_name"]
				cursor.execute(
					"SELECT stop_id FROM stops WHERE stop_name = ?",
					(stop_name,),
				)
				candidates = [r["stop_id"] for r in cursor.fetchall()]
				# prefer exact direction-suffixed candidate
				for s in candidates:
					if s in sequence_by_stop and s.endswith(suffix):
						return s
				# else return any candidate that exists in sequence_by_stop
				for s in candidates:
					if s in sequence_by_stop:
						return s

			# As a last resort, if the requested_id is numeric and sequence_by_stop contains numeric keys without suffix
			if requested_id.isdigit() and requested_id in sequence_by_stop:
				return requested_id

			return None

		resolved_from = _resolve_stop(from_stop_id)
		resolved_to = _resolve_stop(to_stop_id)

		if not resolved_from or not resolved_to:
			raise HTTPException(
				status_code=422,
				detail=_stop_id_error_detail(line, from_stop_id, to_stop_id),
			)

		from_seq = sequence_by_stop[resolved_from]
		to_seq = sequence_by_stop[resolved_to]
		if from_seq > to_seq:
			raise HTTPException(
				status_code=400,
				detail="from_stop_id appears after to_stop_id for the selected direction",
			)

		cursor.execute(
			"""
			SELECT r.stop_id,
				   r.stop_sequence,
				   AVG(o.delay_seconds) AS average_delay_seconds,
				   COUNT(o.observation_id) AS observation_count
			FROM route_to_stop r
			LEFT JOIN train_observations o
				ON o.route_id = r.route_id
			   AND o.stop_id = r.stop_id
			   AND o.delay_seconds IS NOT NULL
			WHERE r.route_id = ?
			  AND r.direction_id = ?
			  AND r.stop_sequence BETWEEN ? AND ?
			GROUP BY r.stop_id, r.stop_sequence
			ORDER BY r.stop_sequence
			""",
			(line, direction_id, from_seq, to_seq),
		)
		segment_rows = [dict(row) for row in cursor.fetchall()]

		delay_values = [row["average_delay_seconds"] for row in segment_rows if row["average_delay_seconds"] is not None]
		segment_avg = sum(delay_values) / len(delay_values) if delay_values else None
	finally:
		conn.close()

	return {
		"line": line,
		"direction": "northbound" if direction_id == 0 else "southbound",
		"from_stop_id": from_stop_id,
		"to_stop_id": to_stop_id,
		"resolved_from_stop_id": resolved_from,
		"resolved_to_stop_id": resolved_to,
		"segment_average_delay_seconds": segment_avg,
		"stop_count": len(segment_rows),
		"segment_stops": segment_rows,
	}


@app.get("/lines/{line}/delays")
def get_delay_data_for_line(line: str, window_minutes: int = Query(default=15, ge=1, le=180)):
	conn = get_connection()
	cursor = conn.cursor()
	cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).strftime("%Y-%m-%d %H:%M:%S")

	try:
		cursor.execute(
			"""
			WITH latest_per_trip AS (
				SELECT trip_id,
					   MAX(timestamp) AS latest_timestamp
				FROM train_observations
				WHERE route_id = ?
				  AND timestamp >= ?
				GROUP BY trip_id
			)
			SELECT o.trip_id,
				   o.route_id,
				   o.stop_id,
				   s.stop_name,
				   o.delay_seconds,
				   o.actual_arrival_time,
				   o.timestamp
			FROM latest_per_trip l
			JOIN train_observations o
			  ON o.trip_id = l.trip_id
			 AND o.timestamp = l.latest_timestamp
			LEFT JOIN stops s
			  ON s.stop_id = o.stop_id
			ORDER BY o.timestamp DESC
			""",
			(line, cutoff),
		)
		trains = [dict(row) for row in cursor.fetchall()]

		cursor.execute(
			"""
			SELECT AVG(delay_seconds) AS average_delay_seconds,
				   COUNT(*) AS observation_count
			FROM train_observations
			WHERE route_id = ?
			  AND timestamp >= ?
			  AND delay_seconds IS NOT NULL
			""",
			(line, cutoff),
		)
		summary = cursor.fetchone()
	finally:
		conn.close()

	return {
		"line": line,
		"window_minutes": window_minutes,
		"currently_running_trains": len(trains),
		"average_delay_seconds": summary["average_delay_seconds"],
		"observation_count": summary["observation_count"],
		"trains": trains,
	}


@app.get("/stations/{stop_id}/delays")
def get_delay_data_for_station(stop_id: str, window_minutes: int = Query(default=60, ge=1, le=720)):
	conn = get_connection()
	cursor = conn.cursor()
	cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).strftime("%Y-%m-%d %H:%M:%S")

	try:
		cursor.execute(
			"""
			SELECT stop_id,
				   stop_name,
				   latitude,
				   longitude
			FROM stops
			WHERE stop_id = ?
			""",
			(stop_id,),
		)
		stop = cursor.fetchone()
		if not stop:
			raise HTTPException(status_code=404, detail="Station not found")

		cursor.execute(
			"""
			SELECT route_id,
				   trip_id,
				   delay_seconds,
				   actual_arrival_time,
				   timestamp
			FROM train_observations
			WHERE stop_id = ?
			  AND timestamp >= ?
			ORDER BY timestamp DESC
			""",
			(stop_id, cutoff),
		)
		observations = [dict(row) for row in cursor.fetchall()]

		cursor.execute(
			"""
			SELECT AVG(delay_seconds) AS average_delay_seconds,
				   COUNT(*) AS observation_count
			FROM train_observations
			WHERE stop_id = ?
			  AND timestamp >= ?
			  AND delay_seconds IS NOT NULL
			""",
			(stop_id, cutoff),
		)
		summary = cursor.fetchone()
	finally:
		conn.close()

	return {
		"station": dict(stop),
		"window_minutes": window_minutes,
		"average_delay_seconds": summary["average_delay_seconds"],
		"observation_count": summary["observation_count"],
		"observations": observations,
	}


@app.get("/stations/delays/average")
def get_average_delays_across_all_stations(min_observations: int = Query(default=1, ge=1)):
	conn = get_connection()
	cursor = conn.cursor()
	try:
		cursor.execute(
			"""
			SELECT o.stop_id,
				   s.stop_name,
				   AVG(o.delay_seconds) AS average_delay_seconds,
				   COUNT(*) AS observation_count
			FROM train_observations o
			LEFT JOIN stops s
			  ON s.stop_id = o.stop_id
			WHERE o.delay_seconds IS NOT NULL
			GROUP BY o.stop_id, s.stop_name
			HAVING COUNT(*) >= ?
			ORDER BY average_delay_seconds DESC
			""",
			(min_observations,),
		)
		rows = [dict(row) for row in cursor.fetchall()]
	finally:
		conn.close()

	return {
		"min_observations": min_observations,
		"stations": rows,
	}

def _resolve_db_stop_id(cursor: sqlite3.Cursor, gtfs_stop_id: str, train: str, direction_id: int | None) -> str | None:
	"""Resolve a GTFS stop ID (e.g. 'A41') to the stop_id used in train_observations.

	Queries route_to_stop first (same ID space as train_observations), then falls
	back to the stops table.  When direction_id is None, tries both N and S suffixes.
	"""
	suffixes = (["N", "S"] if direction_id is None else
				["N" if direction_id == 0 else "S", "S" if direction_id == 0 else "N"])
	candidates = [gtfs_stop_id] + [f"{gtfs_stop_id}{s}" for s in suffixes]

	# Primary: route_to_stop shares its stop_id space with train_observations
	dir_filter = "AND direction_id = ?" if direction_id is not None else ""
	for candidate in candidates:
		params = (train, candidate) if direction_id is None else (train, direction_id, candidate)
		cursor.execute(
			f"SELECT stop_id FROM route_to_stop WHERE route_id = ? {dir_filter} AND stop_id = ? LIMIT 1",
			params,
		)
		row = cursor.fetchone()
		if row:
			return row["stop_id"]
	params = (train, f"{gtfs_stop_id}%") if direction_id is None else (train, direction_id, f"{gtfs_stop_id}%")
	cursor.execute(
		f"SELECT stop_id FROM route_to_stop WHERE route_id = ? {dir_filter} AND stop_id LIKE ? LIMIT 1",
		params,
	)
	row = cursor.fetchone()
	if row:
		return row["stop_id"]

	# Fallback: stops table (direction-agnostic)
	for candidate in candidates:
		cursor.execute("SELECT stop_id FROM stops WHERE stop_id = ? LIMIT 1", (candidate,))
		row = cursor.fetchone()
		if row:
			return row["stop_id"]
	cursor.execute("SELECT stop_id FROM stops WHERE stop_id LIKE ? LIMIT 1", (f"{gtfs_stop_id}%",))
	row = cursor.fetchone()
	return row["stop_id"] if row else None


@app.get("/chatbot/response")
async def get_chatbot_response(
	stop_name: str,
	train: str,
	direction: int,
	stop_id: str | None = None,
	message: str | None = None,
):
	current_delay = 0
	train_data = None
	stop_data = None
	direction_id = int(direction)

	try:
		conn = get_connection()
		cursor = conn.cursor()

		# Resolve GTFS stop_id → actual DB stop_id
		db_stop_id = _resolve_db_stop_id(cursor, stop_id, train, direction_id) if stop_id else None
		logger.debug("chatbot stop resolution: gtfs=%s → db=%s (train=%s dir=%s)", stop_id, db_stop_id, train, direction_id)

		# Build stop_id filter — prefer resolved ID, fall back to name lookup
		if db_stop_id:
			stop_id_filter = db_stop_id
		else:
			cursor.execute("SELECT stop_id FROM stops WHERE stop_name = ? LIMIT 1", (stop_name,))
			row = cursor.fetchone()
			stop_id_filter = row["stop_id"] if row else None

		# Most recent delay at this stop
		if stop_id_filter:
			cursor.execute(
				"""
				SELECT o.delay_seconds, o.actual_arrival_time
				FROM train_observations o
				LEFT JOIN trip_statistics t ON t.trip_id = o.trip_id
				WHERE o.stop_id = ?
				  AND o.route_id = ?
				ORDER BY o.timestamp DESC
				LIMIT 1
				""",
				(stop_id_filter, train),
			)
			delay_result = cursor.fetchone()
			if delay_result:
				current_delay = delay_result["delay_seconds"]

		# Historical observations at this stop — last 7 days, up to 20 rows
		hist_cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

		if stop_id_filter:
			cursor.execute(
				"""
				SELECT o.stop_id, o.delay_seconds, o.actual_arrival_time, o.timestamp
				FROM train_observations o
				WHERE o.route_id = ?
				  AND o.stop_id = ?
				  AND o.timestamp >= ?
				ORDER BY o.timestamp DESC
				LIMIT 20
				""",
				(train, stop_id_filter, hist_cutoff),
			)
		else:
			cursor.execute("SELECT NULL LIMIT 0")
		recent_stop_obs = [dict(row) for row in cursor.fetchall()]

		# Route-level aggregate stats (7-day window)
		cursor.execute(
			"""
			SELECT
				AVG(o.delay_seconds)  AS avg_delay_seconds,
				MAX(o.delay_seconds)  AS max_delay_seconds,
				COUNT(*)              AS observation_count
			FROM train_observations o
			WHERE o.route_id = ?
			  AND o.timestamp >= ?
			  AND o.delay_seconds IS NOT NULL
			""",
			(train, hist_cutoff),
		)
		route_summary_row = cursor.fetchone()
		train_data = {
			"stop_id_used": stop_id_filter,
			"recent_stop_observations": recent_stop_obs,
			"route_summary_last_7d": dict(route_summary_row) if route_summary_row else {},
		}

		# Stop location info
		if stop_id_filter:
			cursor.execute(
				"SELECT stop_id, stop_name, latitude, longitude FROM stops WHERE stop_id = ?",
				(stop_id_filter,),
			)
		else:
			cursor.execute(
				"SELECT stop_id, stop_name, latitude, longitude FROM stops WHERE stop_name = ? LIMIT 1",
				(stop_name,),
			)
		stop_result = cursor.fetchone()
		if stop_result:
			stop_data = dict(stop_result)

	except Exception as e:
		logger.exception("chatbot DB query failed: %s", e)
		current_delay = 0
		train_data = []
		stop_data = None
	finally:
		try:
			cursor.close()
			conn.close()
		except Exception:
			pass

	chatbot = Chatbot()
	response = chatbot.get_response(stop_name, train, current_delay, train_data, stop_data, message)
	return response

@app.get("/chatbot/view_train_observations")
async def view_train(line: str, direction: int, time):
	data = await view_train_timetable(line, direction, time)
	return data

@app.get("/chatbot/view_stops_for_route")
async def view_stops_for_route(line: str, direction: int):
	data = await view_all_stops_from_route(line, direction)
	return data

@app.get("/chatbot/view_stop_timetable")
async def view_stop_timetable(stop_id: str):
	data = await view_static_timetable_for_stop(stop_id)
	return data

if __name__ == "__main__":
	import uvicorn

	uvicorn.run("api.fast_api:app", host="127.0.0.1", port=8000, reload=True)