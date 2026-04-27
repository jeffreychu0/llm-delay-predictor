from datetime import datetime, timezone
import sqlite3

import requests
import os
from google.transit import gtfs_realtime_pb2
from db.init_db import DB_PATH, insert_route_stop, insert_stop, insert_train_observation, insert_trip_statistic

current_dir = os.path.dirname(os.path.abspath(__file__))


base_url = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/"
stops = ""
feeds = [
    "nyct%2Fgtfs", "nyct%2Fgtfs-ace", "nyct%2Fgtfs-bdfm", 
    "nyct%2Fgtfs-g", "nyct%2Fgtfs-l", "nyct%2Fgtfs-si", 
    "nyct%2Fgtfs-nqrw", "nyct%2Fgtfs-jz"
]

def proccess_feed(feed_url):
    try:
        feed = gtfs_realtime_pb2.FeedMessage()
        response = requests.get(feed_url)
    except Exception as e:
         print(f"Error processing feed: {e}")
         
    feed.ParseFromString(response.content)
    routes_seen = set(
        entity.trip_update.trip.route_id 
        for entity in feed.entity 
        if entity.HasField('trip_update'))
    print(f"[{feed_url}] routes in feed: {routes_seen}")
    
    for entity in feed.entity:
        if not entity.HasField('trip_update'):
            continue
        trip_update = entity.trip_update
        trip = trip_update.trip
        trip_id = trip.trip_id
        route_id = trip.route_id
        direction = trip.direction_id
        start_time = trip.start_time
        start_date = trip.start_date
        #attempts to
        try:
            date_time = datetime.strptime(start_date, "%Y%m%d")
            type_of_day = "weekday" if date_time.weekday() < 5 else "weekend"
        except Exception as e:
            print(e)

        for sequence, stop in enumerate(trip_update.stop_time_update):
            stop_id = stop.stop_id
            insert_route_stop(route_id, stop_id, direction, sequence)
            insert_trip_statistic(trip_id, route_id, direction, start_time, start_date, stop_id, type_of_day)
      
            if not stop.HasField("arrival"):
                continue

            arrival = stop.arrival
            delay = arrival.delay
            actual_time = arrival.time

            if actual_time == 0: #NA
                continue
            
            actual_arrical_time = datetime.fromtimestamp(actual_time, tz= timezone.utc).isoformat() #formats the time

            insert_train_observation(trip_id, route_id, actual_arrical_time, delay, stop_id, event_id=None)

            

  
def process_daily_schedule():
    for feed in feeds:
        feed_url = base_url + feed
        proccess_feed(feed_url)
    

