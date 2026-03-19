import sqlite3
import requests
import os
from google.transit import gtfs_realtime_pb2


current_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(current_dir, '..', 'mta.db')

base_url = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/"
feeds = [
    "nyct%2Fgtfs", "nyct%2Fgtfs-ace", "nyct%2Fgtfs-bdfm", 
    "nyct%2Fgtfs-g", "nyct%2Fgtfs-l", "nyct%2Fgtfs-7", 
    "nyct%2Fgtfs-nqrw", "nyct%2Fgtfs-jz"
]


def proccess_feed(feed_url):
    try:
        feed = gtfs_realtime_pb2.FeedMessage()
        response = requests.get(feed_url)
        feed.ParseFromString(response.content)
        
    
        connect = sqlite3.connect(db_path)
        cursor = connect.cursor()
        for entity in feed.entity:
            if entity.HasField('trip_update'):
                trip_update = entity.trip_update
                route_id = trip_update.trip.route_id
                for stop_time_update in trip_update.stop_time_update:
                    if stop_time_update.HasField('arrival'):
                        schedule_time = stop_time_update.arrival.time - stop_time_update.arrival.delay
                        stop_id = stop_time_update.stop_id
        
                        cursor.execute('''
                            INSERT OR IGNORE INTO train_observations (trip_id, route_id, timestamp, actual_arrival_time, delay_seconds, stop_id)
                            VALUES (?, ?, datetime('unixepoch', ?), datetime('unixepoch', ?), ?, ?)
                        ''', (trip_update.trip.trip_id, route_id, stop_time_update.arrival.time, schedule_time,  stop_time_update.arrival.delay, stop_id))
                
                        connect.commit()
                        connect.close()
        return
    except Exception as e:
        print(f"Error processing feed: {e}")
        return None
    

print(proccess_feed(f"{base_url}{feeds[0]}"))
