import sqlite3
import os

file = os.path.abspath(__file__)
# static var to ensure when connecting to the db the path is correct regardless of where the script is being run from, this is important for the feed processing function which is being executed in a different thread and may have a different working directory
DB_PATH = os.path.dirname(file) 
def init_db(reset=False):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()

    if reset:
        # Explicit destructive reset path.
        cursor.execute('DROP TABLE IF EXISTS route_to_stop')
        cursor.execute('DROP TABLE IF EXISTS train_observations')
        cursor.execute('DROP TABLE IF EXISTS observation_diagnostics')
        cursor.execute('DROP TABLE IF EXISTS trip_statistics')
    

    """
    trip_statistics: Stores static information about each trip, such as route, direction, and scheduled arrival times. from a dataset we can get the scheduled arrival times for each trip, which will be used to calculate delays.
    train_observations: Stores real-time observations of train arrivals, including actual arrival times
    external_factors: Stores information about external factors that may influence train delays, such as weather conditions, special events, and holidays. This data can be collected from various sources, including weather APIs and event calendars.
    """
    cursor.executescript('''
        -- Table to associate stop_id to route_id
        CREATE TABLE IF NOT EXISTS route_to_stop (
            route_id TEXT NOT NULL,
            stop_id TEXT NOT NULL,
            direction_id INTEGER,
            is_weekend INTEGER DEFAULT 0,
            is_overnight INTEGER DEFAULT 0,
            is_express INTEGER DEFAULT 0,
            stop_sequence INTEGER,
            PRIMARY KEY (route_id, stop_id, direction_id)
        );

        -- Table to associate stop_id
        CREATE TABLE IF NOT EXISTS stops (
            stop_id TEXT PRIMARY KEY,
            stop_name TEXT,
            latitude REAL,
            longitude REAL
        );

        -- Table to associate mta events to id's (includes delay events, scheduled repair, etc)
        CREATE TABLE IF NOT EXISTS mta_event_lookup (
            event_id TEXT PRIMARY KEY,
            event_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_description TEXT,
            is_planned BOOLEAN DEFAULT FALSE
        );

        -- Per-trip baseline statistics and descriptors
        CREATE TABLE IF NOT EXISTS trip_statistics (
            trip_id TEXT PRIMARY KEY,
            route_id TEXT,
            direction_id INTEGER,
            service_id TEXT,
            start_time DATETIME,
            start_date DATETIME,
            end_date DATETIME,
            stop_id TEXT,
            day_type TEXT
        );
                 
        -- Train observations from API
        CREATE TABLE IF NOT EXISTS train_observations (
            observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT,
            route_id TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            actual_arrival_time DATETIME,
            delay_seconds INTEGER,
            stop_id TEXT,
            event_id TEXT,
            FOREIGN KEY (trip_id) REFERENCES trip_statistics(trip_id),
            FOREIGN KEY (stop_id) REFERENCES stops(stop_id),
            FOREIGN KEY (event_id) REFERENCES mta_event_lookup(event_id)
        );

        -- Diagnostic and anomaly records tied to realtime observations.
        CREATE TABLE IF NOT EXISTS observation_diagnostics (
            diagnostic_id INTEGER PRIMARY KEY AUTOINCREMENT,
            observation_id INTEGER NOT NULL,
            diagnostic_type TEXT NOT NULL,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (observation_id) REFERENCES train_observations(observation_id)
        );

        -- External context factors for model features and analysis
        CREATE TABLE IF NOT EXISTS external_factors (
            timestamp DATETIME PRIMARY KEY,
            weather_condition TEXT,
            temp_f TEXT,
            is_holiday BOOLEAN DEFAULT FALSE
        );
        -- Table for static train timetable data extracted from GTFS supplemented
            CREATE TABLE IF NOT EXISTS train_timetable (
            trip_id TEXT,
            route_id TEXT,
            direction_id INTEGER,
            stop_id TEXT,
            stop_sequence INTEGER,
            arrival_time DATETIME,
            departure_time DATETIME,
            headsign TEXT,
            PRIMARY KEY (trip_id, stop_id));
            
    ''')    
    
    conn.commit()
    conn.close()
    



def insert_route_stop(route_id, stop_id, direction_id, stop_sequence):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO route_to_stop(
            route_id,
            stop_id,
            direction_id,
            is_weekend,
            is_overnight,
            is_express,
            stop_sequence
        )
        VALUES (?, ?, ?, 0, 0, 0, ?)
    ''', (route_id, stop_id, direction_id, stop_sequence))
    conn.commit()
    conn.close(
    )

def insert_stop(stop_id, stop_name, borough, latitude, longitude):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO stops (stop_id, stop_name, latitude, longitude)
        VALUES (?, ?, ?, ?)
    ''', (stop_id, stop_name, latitude, longitude))
    conn.commit()
    conn.close()

def insert_mta_event(event_id, event_name, event_type, event_description, is_planned):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO mta_event_lookup (event_id, event_name, event_type, event_description, is_planned)
        VALUES (?, ?, ?, ?, ?)
    ''', (event_id, event_name, event_type, event_description, is_planned))
    conn.commit()
    conn.close()

def insert_trip_statistic(trip_id, route_id, direction_id, service_id, start_time, start_date, end_date, stop_id, day_type):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO trip_statistics (
            trip_id,
            route_id,
            direction_id,
            service_id,
            start_time,
            start_date,
            end_date,
            stop_id,
            day_type
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (trip_id, route_id, direction_id, service_id, start_time, start_date, end_date, stop_id, day_type))
    conn.commit()
    conn.close()

def insert_external_factor(timestamp, weather_condition, temp_f, is_holiday):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO external_factors (timestamp, weather_condition, temp_f, is_holiday)
        VALUES (?, ?, ?, ?)
    ''', (timestamp, weather_condition, temp_f, is_holiday))
    conn.commit()
    conn.close()

def insert_train_observation(trip_id, route_id, actual_arrival_time, delay_seconds, stop_id, event_id):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO train_observations (trip_id, route_id, actual_arrival_time, delay_seconds, stop_id, event_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (trip_id, route_id, actual_arrival_time, delay_seconds, stop_id, event_id))
    observation_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return observation_id


def insert_observation_diagnostic(observation_id, diagnostic_type, details):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO observation_diagnostics (observation_id, diagnostic_type, details)
        VALUES (?, ?, ?)
    ''', (observation_id, diagnostic_type, details))
    diagnostic_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return diagnostic_id


def insert_train_timetable(trip_id, 
                           stop_id, 
                           stop_sequence, route_id, 
                           trip_headsign, 
                           direction_id, 
                           arrival_time, 
                           departure_time):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO train_timetable(trip_id,
            route_id,
            direction_id,
            stop_id,
            stop_sequence,
            arrival_time,
            departure_time,
            headsign) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                  ''', (trip_id, route_id, direction_id, stop_id, stop_sequence, arrival_time,departure_time, trip_headsign))

    conn.commit()
    conn.close()


def bulk_refresh_train_timetable(entries, chunk_size=10000):
    if not entries:
        return

    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()

    # Replace stale or partial static imports with a full refresh.
    cursor.execute('DELETE FROM train_timetable')

    sql = '''
        INSERT INTO train_timetable(
            trip_id,
            route_id,
            direction_id,
            stop_id,
            stop_sequence,
            arrival_time,
            departure_time,
            headsign
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    '''

    for start in range(0, len(entries), chunk_size):
        chunk = entries[start:start + chunk_size]
        cursor.executemany(sql, chunk)

    conn.commit()
    conn.close()
    
def view_train_timetable(route_id, direction_id, time):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('CREATE VIEW IF NOT EXISTS train_timetable_view AS SELECT * FROM train_timetable;')
    cursor.execute('SELECT * FROM train_timetable_view LIMIT 10 WHERE route_id = ? AND direction_id = ? AND arrival_time >= ?; LIMIT 10', (route_id, direction_id, time))
    rows = cursor.fetchall()
    cursor.execute('DROP VIEW IF EXISTS train_timetable_view;')
    conn.close()
    return rows

def view_all_stops_from_route(route_id):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('CREATE VIEW IF NOT EXISTS all_stops_from_route_view AS SELECT DISTINCT (route_id) FROM route_to_stop UNION SELECT DISTINCT (route_id) FROM train_timetable;')
    cursor.execute('SELECT * FROM all_stops_from_route_view where route_id = ?;', (route_id,))
    rows = cursor.fetchall()
    cursor.execute('DROP VIEW IF EXISTS all_stops_from_route_view;')
    conn.close()
    return rows

def view_static_timetable_for_stop(stop_id):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute(';CREATE VIEW IF NOT EXISTS static_timetable_view AS SELECT * FROM train_timetable')
    cursor.execute('SELECT * FROM static_timetable_view where stop_id = ? LIMIT 10;', (stop_id,))
    rows = cursor.fetchall()
    cursor.execute('DROP VIEW IF EXISTS static_timetable_view;')
    conn.close()
    return rows

def view_all_train_timetable(route_id, direction_id, time):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('CREATE VIEW IF NOT EXISTS train_all_timetable_view AS SELECT * FROM train_timetable;')
    cursor.execute('SELECT * FROM train_all_timetable_view;')
    rows = cursor.fetchall()
    cursor.execute('DROP VIEW IF EXISTS train_all_timetable_view;')
    conn.close()
    return rows
  

def view_static_timetable_for_all():
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('CREATE VIEW IF NOT EXISTS static_timetable_view AS SELECT * FROM train_timetable;')

    conn.close()


def view_all_made_stops():
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('CREATE VIEW IF NOT EXISTS all_made_stops_view AS SELECT DISTINCT (stop_id) FROM route_to_stop UNION SELECT DISTINCT (stop_id) FROM train_timetable;')
    conn.close()
