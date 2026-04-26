import csv
import os
from db.init_db import bulk_refresh_train_timetable


def _load_train_route_ids(routes_file):
    train_route_ids = set()
    with open(routes_file, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            route_id = row.get('route_id')
            route_type = row.get('route_type')
            if not route_id:
                continue

            train_route_ids.add(route_id)

    return train_route_ids


def extract_timetable_from_txt(route_ids=None):
    gtfs_path = os.path.join(os.path.dirname(__file__), 'gtfs_supplemented')
    calender_file = os.path.join(gtfs_path, 'calendar.txt')
    routes_file = os.path.join(gtfs_path, 'routes.txt')
    trips_file = os.path.join(gtfs_path, 'trips.txt')
    stop_times_file = os.path.join(gtfs_path, 'stop_times.txt')

    allowed_route_ids = set(route_ids) if route_ids else _load_train_route_ids(routes_file)
    
    #calender to get service
    calender = {}

    with open(calender_file, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            service_id = row['service_id']
            is_weekday = row['monday'] == '1' or row['tuesday'] == '1' or row['wednesday'] == '1' or row['thursday'] == '1' or row['friday'] == '1'
            is_weekend = row['saturday'] == '1' or row['sunday'] == '1'

            # Classify as weekday or weekend
            if is_weekday and not is_weekend:
                schedule_type = 'weekday'
            elif is_weekend:
                schedule_type = 'weekend'
            else:
                schedule_type = 'weekday'

            calender[service_id] = schedule_type
    #load all trips

    trips = {}
    with open(trips_file, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['route_id'] not in allowed_route_ids:
                continue

            trips[row['trip_id']] = {
                'route_id': row['route_id'],
                'service_id': row['service_id'],
                'trip_headsign': row.get('trip_headsign', ''),
                'direction_id': row.get('direction_id', '0')
            }
    # Extract timetables from stop_times
    timetables = {
        'weekday': [],
        'weekend': []
    }
    with open(stop_times_file, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            trip_id = row['trip_id']
            if trip_id not in trips:
                continue
                        
            trip = trips[trip_id]
            schedule_type = calender.get(trip['service_id'], 'weekday')
            
            # Create timetable entry
            entry = {
                'stop_id': row['stop_id'],
                'stop_sequence': int(row['stop_sequence']),
                'arrival_time': row['arrival_time'],
                'departure_time': row['departure_time'],
                'trip_id': trip_id,
                'route_id': trip['route_id'],
                'headsign': trip['trip_headsign'],
                'direction_id': trip['direction_id']
            }
            
            timetables[schedule_type].append(entry)

    return timetables


def static_to_db(route_ids=None):
    timetables = extract_timetable_from_txt(route_ids=route_ids)

    rows = []
    for entries in timetables.values():
        for entry in entries:
            rows.append((
                entry['trip_id'],
                entry['route_id'],
                entry['direction_id'],
                entry['stop_id'],
                entry['stop_sequence'],
                entry['arrival_time'],
                entry['departure_time'],
                entry['headsign']
            ))

    bulk_refresh_train_timetable(rows)
        
