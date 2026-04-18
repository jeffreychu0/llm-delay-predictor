import sqlite3
import requests
import os
from google.transit import gtfs_realtime_pb2
from db.init_db import DB_PATH

current_dir = os.path.dirname(os.path.abspath(__file__))


base_url = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/"
feeds = [
    "nyct%2Fgtfs", "nyct%2Fgtfs-ace", "nyct%2Fgtfs-bdfm", 
    "nyct%2Fgtfs-g", "nyct%2Fgtfs-l", "nyct%2Fgtfs-7", 
    "nyct%2Fgtfs-nqrw", "nyct%2Fgtfs-jz"
]

def row_exists(primary_key_value):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM train_observations WHERE id = ?", (primary_key_value,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def update_row(primary_key_value, new_values, table_name):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    set_clause = ", ".join([f"{column} = ?" for column in new_values.keys()])
    values = list(new_values.values()) + [primary_key_value]
    cursor.execute(f"UPDATE {table_name} SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    
def process_feed(feed_url):
    try:
        feed = gtfs_realtime_pb2.FeedMessage()
        response = requests.get(feed_url)
        feed.ParseFromString(response.content)
        
    
        connect = sqlite3.connect(DB_PATH + '/mta.db')
        cursor = connect.cursor()
        for entity in feed.entity:
            if entity.HasField('trip_update'):
                trip_update = entity.trip_update
                route_id = trip_update.trip.route_id
                for stop_time_update in trip_update.stop_time_update:
                    if stop_time_update.HasField('arrival'):
                        arrival = stop_time_update.arrival
                        delay = arrival.delay 
                        atual_time = arrival.time
                        schedule_time = atual_time - delay
                        stop_id = stop_time_update.stop_id
        
                        cursor.execute('''
                            INSERT OR IGNORE INTO train_observations (trip_id, route_id, timestamp, actual_arrival_time, delay_seconds, stop_id)
                            VALUES (?, ?, datetime( ?, 'unixepoch'), datetime( ?, 'unixepoch'), ?, ?)
                        ''', (trip_update.trip.trip_id, route_id, atual_time, schedule_time,  delay, stop_id))
                
        connect.commit()
        connect.close()
        print(f"Data Imported from: {feed_url}")
        return
    except Exception as e:
        print(f"Error processing feed {feed_url}: {e.with_traceback()}")
        return None

if __name__ == "__main__":
    print(process_feed(f"{base_url}{feeds[0]}"))
