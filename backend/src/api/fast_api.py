import sqlite3
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.src.chatbot import Chatbot
from db.init_db import DB_PATH


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
		if from_stop_id not in sequence_by_stop or to_stop_id not in sequence_by_stop:
			raise HTTPException(status_code=404, detail="from_stop_id or to_stop_id not found for line/direction")

		from_seq = sequence_by_stop[from_stop_id]
		to_seq = sequence_by_stop[to_stop_id]
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
		"segment_average_delay_seconds": segment_avg,
		"stop_count": len(segment_rows),
		"segment_stops": segment_rows,
	}


@app.get("/lines/{line}/delays")
def get_delay_data_for_line(line: str, window_minutes: int = Query(default=15, ge=1, le=180)):
	conn = get_connection()
	cursor = conn.cursor()
	cutoff = (datetime.utcnow() - timedelta(minutes=window_minutes)).isoformat()

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
	cutoff = (datetime.utcnow() - timedelta(minutes=window_minutes)).isoformat()

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

@app.get("/chatbot/response")
async def get_chatbot_response(stop_name: str, train: str, direction: int):
	current_delay = 0
	train_data = None
	stop_data = None
	
	try:
		cursor = get_connection().cursor()

		# Get current delay
		cursor.execute(
			"""
			SELECT delay_seconds, actual_arrival_time
			FROM train_observations
			WHERE stop_id = (
				SELECT stop_id FROM stops WHERE stop_name = ?
			)
			  AND route_id = ?
			  AND direction_id = ?
			ORDER BY timestamp DESC
			LIMIT 1
			""",
			(stop_name, train, direction),
		)
		delay_result = cursor.fetchone()
		if delay_result:
			current_delay = delay_result["delay_seconds"]

		# Get all stops data (scheduled + observed)
		cursor.execute(
			"""
			SELECT 
				stop_id,
				stop_sequence,
				'scheduled' AS data_type,
				NULL AS delay_seconds,
				NULL AS actual_arrival_time,
				NULL AS timestamp
			FROM train_timetable
			WHERE route_id = ?
			  AND direction_id = ?
			
			UNION
			
			SELECT 
				o.stop_id,
				NULL AS stop_sequence,
				'observed' AS data_type,
				o.delay_seconds,
				o.actual_arrival_time,
				o.timestamp
			FROM train_observations o
			WHERE o.route_id = ?
			  AND o.direction_id = ?
			
			ORDER BY stop_id, data_type DESC
			""",
			(train, direction, train, direction),
		)
		train_data = [dict(row) for row in cursor.fetchall()]

		# Get stop location info
		cursor.execute(
			"""
			SELECT stop_id, stop_name, latitude, longitude
			FROM stops
			WHERE stop_name = ?
			""",
			(stop_name,),
		)
		stop_result = cursor.fetchone()
		if stop_result:
			stop_data = dict(stop_result)

	except Exception as e:
		current_delay = 0
		train_data = []
		stop_data = None
	finally:
		cursor.close()

	chatbot = Chatbot()
	response = await chatbot.get_response(stop_name, direction, train, current_delay, train_data, stop_data)
	return response

if __name__ == "__main__":
	import uvicorn

	uvicorn.run("api.fast_api:app", host="127.0.0.1", port=8000, reload=True)