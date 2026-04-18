import sqlite3
import os

file = os.path.abspath(__file__)
# static var to ensure when connecting to the db the path is correct regardless of where the script is being run from, this is important for the feed processing function which is being executed in a different thread and may have a different working directory
DB_PATH = os.path.dirname(file) 
def init_db():
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    

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
            stop_sequence INTEGER,
            PRIMARY KEY (route_id, stop_id, direction_id)
        );

        -- Table to associate stop_id
        CREATE TABLE IF NOT EXISTS stops (
            stop_id TEXT PRIMARY KEY,
            stop_name TEXT,
            borough TEXT,
            latitude REAL,
            longitude REAL,
            is_active BOOLEAN DEFAULT TRUE
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
            start_time DATETIME,
            start_date DATETIME,
            stop_id TEXT,
            day_type TEXT
        );
                 
        -- Train observations from API
        CREATE TABLE IF NOT EXISTS train_observations (   
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT,
            route_id TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            actual_arrival_time DATETIME,
            delay_seconds INTEGER,
            stop_id TEXT,
            event_id TEXT,
            FOREIGN KEY (trip_id) REFERENCES trip_statistics(trip_id),
            FOREIGN KEY (stop_id) REFERENCES stop_catalog(stop_id),
            FOREIGN KEY (event_id) REFERENCES mta_event_lookup(event_id)
        );

        -- External context factors for model features and analysis
        CREATE TABLE IF NOT EXISTS external_factors (
            timestamp DATETIME PRIMARY KEY,
            weather_condition TEXT,
            temp_f TEXT,
            is_holiday BOOLEAN DEFAULT FALSE
        );
    ''')    
    
    conn.commit()
    conn.close()