-- Ameer, Jeffery, Tony
-- LLM Delay Predictor Database Schema and Queries
-- FYI: sqlite used for prototyping; schema aims to be compatible with MySQL/Postgres
-- The `?` placeholders are for parameterized queries used by application code
-- NOTE: Since we used it with SQLite, the parameters were stored directly in python, hence running on MySQL will fail because of parameters

-- Drop tables (drop dependents first to avoid FK errors)
DROP TABLE IF EXISTS observation_diagnostics;
DROP TABLE IF EXISTS train_observations;
DROP TABLE IF EXISTS train_timetable;
DROP TABLE IF EXISTS trip_statistics;
DROP TABLE IF EXISTS route_to_stop;
DROP TABLE IF EXISTS stops;
DROP TABLE IF EXISTS mta_event_lookup;
DROP TABLE IF EXISTS external_factors;

-- Table to associate stop_id to route_id
CREATE TABLE IF NOT EXISTS route_to_stop (
    route_id VARCHAR(255) NOT NULL,
    stop_id VARCHAR(255) NOT NULL,
    direction_id INT NOT NULL,
    is_weekend INT DEFAULT 0,
    is_overnight INT DEFAULT 0,
    is_express INT DEFAULT 0,
    stop_sequence INT,
    PRIMARY KEY (route_id, stop_id, direction_id)
);

-- Table to store stops
CREATE TABLE IF NOT EXISTS stops (
    stop_id VARCHAR(255) PRIMARY KEY,
    stop_name VARCHAR(255),
    latitude REAL,
    longitude REAL
);

-- Table for MTA events (delay types, maintenance, etc.)
CREATE TABLE IF NOT EXISTS mta_event_lookup (
    event_id VARCHAR(255) PRIMARY KEY,
    event_name VARCHAR(255) NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    event_description TEXT,
    is_planned INT DEFAULT 0
);

-- Per-trip baseline statistics and descriptors
CREATE TABLE IF NOT EXISTS trip_statistics (
    trip_id VARCHAR(255) PRIMARY KEY,
    route_id VARCHAR(255),
    direction_id INT,
    service_id VARCHAR(255),
    start_time DATETIME,
    start_date DATE,
    end_date DATE,
    stop_id VARCHAR(255),
    day_type VARCHAR(255)
);

-- Train observations from realtime API
CREATE TABLE IF NOT EXISTS train_observations (
    observation_id INT PRIMARY KEY AUTO_INCREMENT,
    trip_id VARCHAR(255),
    route_id VARCHAR(255),
    `timestamp` DATETIME DEFAULT CURRENT_TIMESTAMP,
    actual_arrival_time DATETIME,
    delay_seconds INT,
    stop_id VARCHAR(255),
    event_id VARCHAR(255),
    FOREIGN KEY (trip_id) REFERENCES trip_statistics(trip_id),
    FOREIGN KEY (stop_id) REFERENCES stops(stop_id),
    FOREIGN KEY (event_id) REFERENCES mta_event_lookup(event_id)
);

-- Diagnostic and anomaly records tied to realtime observations
CREATE TABLE IF NOT EXISTS observation_diagnostics (
    diagnostic_id INT PRIMARY KEY AUTO_INCREMENT,
    observation_id INT NOT NULL,
    diagnostic_type VARCHAR(255) NOT NULL,
    details TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (observation_id) REFERENCES train_observations(observation_id)
);

-- External context factors for model features and analysis
CREATE TABLE IF NOT EXISTS external_factors (
    `timestamp` DATETIME PRIMARY KEY,
    weather_condition VARCHAR(255),
    temp_f REAL,
    is_holiday INT DEFAULT 0
);

-- Static train timetable data (GTFS supplemented)
CREATE TABLE IF NOT EXISTS train_timetable (
    trip_id VARCHAR(255),
    route_id VARCHAR(255),
    direction_id INT,
    stop_id VARCHAR(255),
    stop_sequence INT,
    arrival_time DATETIME,
    departure_time DATETIME,
    headsign VARCHAR(255),
    PRIMARY KEY (trip_id, stop_id)
);

-- Example INSERT templates used by loader scripts (parameterized)
INSERT INTO stops (stop_id, stop_name, latitude, longitude) VALUES (?, ?, ?, ?);

INSERT INTO route_to_stop (
    route_id, stop_id, direction_id, is_weekend, is_overnight, is_express, stop_sequence
) VALUES (?, ?, ?, ?, ?, ?, ?);

INSERT INTO trip_statistics (
    trip_id, route_id, direction_id, service_id, start_time, start_date, end_date, stop_id, day_type
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);

INSERT INTO mta_event_lookup (event_id, event_name, event_type, event_description, is_planned)
    VALUES (?, ?, ?, ?, ?);

-- Convenience "upsert/insert-if-not-exists" statements for loaders and app
INSERT IGNORE INTO route_to_stop (
    route_id, stop_id, direction_id, is_weekend, is_overnight, is_express, stop_sequence
) VALUES (?, ?, ?, 0, 0, 0, ?);

INSERT IGNORE INTO stops (stop_id, stop_name, latitude, longitude) VALUES (?, ?, ?, ?);

INSERT IGNORE INTO mta_event_lookup (event_id, event_name, event_type, event_description, is_planned)
    VALUES (?, ?, ?, ?, ?);

INSERT IGNORE INTO trip_statistics (
    trip_id, route_id, direction_id, service_id, start_time, start_date, end_date, stop_id, day_type
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);

INSERT IGNORE INTO external_factors (`timestamp`, weather_condition, temp_f, is_holiday) VALUES (?, ?, ?, ?);

INSERT INTO train_observations (trip_id, route_id, actual_arrival_time, delay_seconds, stop_id, event_id)
    VALUES (?, ?, ?, ?, ?, ?);

INSERT INTO observation_diagnostics (observation_id, diagnostic_type, details) VALUES (?, ?, ?);

INSERT IGNORE INTO train_timetable (
    trip_id, route_id, direction_id, stop_id, stop_sequence, arrival_time, departure_time, headsign
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);

-- Selects (Template)
-- Find static trip match for an observation to compute accurate delay
SELECT t.trip_id, t.direction_id, t.start_time,
       tt.arrival_time, tt.departure_time
FROM trip_statistics t
LEFT JOIN train_timetable tt
  ON tt.trip_id = t.trip_id AND tt.stop_id = ?
WHERE t.route_id = ?
  AND t.trip_id LIKE ?
  AND (t.day_type = ? OR t.day_type = 'mixed')
  AND (? IS NULL OR t.start_date IS NULL OR t.start_date <= ?)
  AND (? IS NULL OR t.end_date IS NULL OR t.end_date >= ?);

SELECT t.trip_id, t.direction_id, t.start_time,
       tt.arrival_time, tt.departure_time
FROM trip_statistics t
LEFT JOIN train_timetable tt
  ON tt.trip_id = t.trip_id AND tt.stop_id = ?
WHERE t.route_id = ?
  AND t.trip_id LIKE ?
  AND (t.day_type = ? OR t.day_type = 'mixed');

SELECT arrival_time, departure_time
FROM train_timetable
WHERE trip_id = ? AND stop_id = ?
ORDER BY stop_sequence
LIMIT 1;

SELECT route_id, headsign,
COUNT(*) AS samples
FROM train_timetable
WHERE route_id = ?
AND headsign IS NOT NULL
AND TRIM(headsign) <> ''
GROUP BY route_id, headsign
ORDER BY route_id, samples DESC, headsign;


WITH latest_per_trip AS (
SELECT trip_id,
MAX(`timestamp`) AS latest_timestamp
FROM train_observations
WHERE route_id = ?
AND `timestamp` >= ?
GROUP BY trip_id
)
SELECT o.trip_id,
o.route_id,
o.stop_id,
s.stop_name,
o.delay_seconds,
o.actual_arrival_time,
o.`timestamp`
FROM latest_per_trip l
JOIN train_observations o
ON o.trip_id = l.trip_id
AND o.`timestamp` = l.latest_timestamp
LEFT JOIN stops s
ON s.stop_id = o.stop_id
ORDER BY o.`timestamp` DESC;
-- delay estimate
SELECT stop_id, stop_sequence
FROM route_to_stop
WHERE route_id = ?
 AND direction_id = ? AND stop_sequence IS NOT NULL
ORDER BY stop_sequence;

SELECT o.delay_seconds, o.actual_arrival_time
FROM train_observations o
LEFT JOIN trip_statistics t ON t.trip_id = o.trip_id
WHERE o.stop_id = ?
    AND o.route_id = ?
ORDER BY o.`timestamp` DESC
LIMIT 1;

SELECT o.stop_id, o.delay_seconds, o.actual_arrival_time, o.`timestamp`
FROM train_observations o
WHERE o.route_id = ?
    AND o.stop_id = ?
    AND o.`timestamp` >= ?
ORDER BY o.`timestamp` DESC
LIMIT 20;

SELECT
    AVG(o.delay_seconds)  AS avg_delay_seconds,
    MAX(o.delay_seconds)  AS max_delay_seconds,
    COUNT(*)              AS observation_count
FROM train_observations o
WHERE o.route_id = ?
    AND o.`timestamp` >= ?
    AND o.delay_seconds IS NOT NULL;
-- station delay
SELECT stop_id,
        stop_name,
        latitude,
        longitude
FROM stops
WHERE stop_id = ?;
--stop name finder
SELECT stop_name FROM stops WHERE stop_id = ? LIMIT 1;
SELECT stop_id FROM stops WHERE stop_name = ?;

-- averages
SELECT AVG(delay_seconds) AS global_average_delay_seconds,
COUNT(*) AS observation_count
FROM train_observations
WHERE delay_seconds IS NOT NULL;

SELECT route_id,
AVG(delay_seconds) AS average_delay_seconds,
COUNT(*) AS observation_count
FROM train_observations
WHERE delay_seconds IS NOT NULL
GROUP BY route_id
ORDER BY route_id;

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
ORDER BY r.stop_sequence;

SELECT start_time FROM trip_statistics WHERE trip_id = ? LIMIT 1;

-- Timetable views and helper queries
CREATE OR REPLACE VIEW train_timetable_view AS SELECT * FROM train_timetable;
SELECT * FROM train_timetable_view
WHERE route_id = ? AND direction_id = ? AND arrival_time >= ?
LIMIT 10;
DROP VIEW IF EXISTS train_timetable_view;

CREATE OR REPLACE VIEW all_stops_from_route_view AS
  SELECT DISTINCT route_id FROM route_to_stop
  UNION
  SELECT DISTINCT route_id FROM train_timetable;
SELECT * FROM all_stops_from_route_view WHERE route_id = ?;
DROP VIEW IF EXISTS all_stops_from_route_view;

CREATE OR REPLACE VIEW static_timetable_view AS SELECT * FROM train_timetable;
SELECT * FROM static_timetable_view WHERE stop_id = ? LIMIT 10;
DROP VIEW IF EXISTS static_timetable_view;

CREATE OR REPLACE VIEW train_all_timetable_view AS SELECT * FROM train_timetable;
SELECT * FROM train_all_timetable_view;
DROP VIEW IF EXISTS train_all_timetable_view;

CREATE OR REPLACE VIEW all_made_stops_view AS
  SELECT DISTINCT stop_id FROM route_to_stop
  UNION
  SELECT DISTINCT stop_id FROM train_timetable;
