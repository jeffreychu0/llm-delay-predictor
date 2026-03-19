import sqlite3
import datetime

def init_db():
    conn = sqlite3.connect('mta.db')
    cursor = conn.cursor()
    

    """
    trip_statistics: Stores static information about each trip, such as route, direction, and scheduled arrival times. from a dataset we can get the scheduled arrival times for each trip, which will be used to calculate delays.
    train_observations: Stores real-time observations of train arrivals, including actual arrival times
    external_factors: Stores information about external factors that may influence train delays, such as weather conditions, special events, and holidays. This data can be collected from various sources, including weather APIs and event calendars.
    """
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS trip_statistics (
            trip_id TEXT PRIMARY KEY,
            route_id text,
            direction_id INTEGER,
            arrival_time TEXT,
            stop_id TEXT,
            day_type TEXT
        );
                   
        CREATE TABLE IF NOT EXISTS train_observations (   
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT,
            route_id TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            actual_arrival_time DATETIME,
            delay_seconds INTEGER,
            stop_id TEXT,
            FOREIGN KEY (trip_id) REFERENCES trip_statistics(trip_id)
                   
        );
        CREATE TABLE IF NOT EXISTS external_factors (
            timestamp DATETIME PRIMARY KEY,
            weather_condition TEXT,
            temp_f TEXT,
            mta_event TEXT,
            is_holiday BOOLEAN DEFAULT FALSE
        );
    ''')    
    
    conn.commit()
    conn.close()