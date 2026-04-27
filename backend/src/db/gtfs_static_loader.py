import csv
import os
import sqlite3

from db.init_db import DB_PATH


class GtfsStaticLoader:
    """Loads static GTFS text files into normalized SQLite tables."""

    def __init__(self):
        self.gtfs_path = os.path.join(os.path.dirname(__file__), 'gtfs_supplemented')
        self.db_file = os.path.join(DB_PATH, 'mta.db')

    # Runs execution of static information polling with optional mta event lookup
    # Summary returns the length of data returned, aka how many stops, etc
    def execute(self, include_events=True):
        summary = {
            'stops': self.load_stops(),
            'route_to_stop': self.load_route_to_stop(),
            'trip_statistics': self.load_trip_statistics(),
        }
        if include_events:
            summary['mta_event_lookup'] = self.load_mta_event_lookup_from_calendar_dates()
        return summary

    # add stop info within our database
    def load_stops(self):
        stops_file = os.path.join(self.gtfs_path, 'stops.txt')
        rows = []

        with open(stops_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                stop_id = row.get('stop_id')
                if not stop_id:
                    continue

                stop_name = row.get('stop_name') or ''
                latitude = self._safe_float(row.get('stop_lat'))
                longitude = self._safe_float(row.get('stop_lon'))

                rows.append((
                    stop_id,
                    stop_name,
                    latitude,
                    longitude,
                ))

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM stops')
            cursor.executemany(
                '''
                INSERT INTO stops(
                    stop_id,
                    stop_name,
                    latitude,
                    longitude
                ) VALUES (?, ?, ?, ?)
                ''',
                rows,
            )

        return len(rows)

    # Define our route_to_stop table, which implements the many-to-many association between routes and stops while maintaining stop sequence relationships
    def load_route_to_stop(self):
        trips_file = os.path.join(self.gtfs_path, 'trips.txt')
        stop_times_file = os.path.join(self.gtfs_path, 'stop_times.txt')

        trip_route_lookup = {}
        with open(trips_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                trip_id = row.get('trip_id')
                route_id = row.get('route_id')
                if not trip_id or not route_id:
                    continue
                trip_route_lookup[trip_id] = (
                    route_id,
                    self._safe_int(row.get('direction_id')),
                )

        route_stop_min_seq = {}
        with open(stop_times_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                trip_id = row.get('trip_id')
                stop_id = row.get('stop_id')
                if not trip_id or not stop_id or trip_id not in trip_route_lookup:
                    continue

                route_id, direction_id = trip_route_lookup[trip_id]
                stop_sequence = self._safe_int(row.get('stop_sequence'))
                if stop_sequence is None:
                    continue

                key = (route_id, stop_id)
                existing = route_stop_min_seq.get(key)
                if existing is None or stop_sequence < existing[1]:
                    route_stop_min_seq[key] = (direction_id, stop_sequence)

        rows = [
            (route_id, stop_id, direction_id, stop_sequence)
            for (route_id, stop_id), (direction_id, stop_sequence) in route_stop_min_seq.items()
        ]

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM route_to_stop')
            cursor.executemany(
                '''
                INSERT INTO route_to_stop(route_id, stop_id, direction_id, stop_sequence)
                VALUES (?, ?, ?, ?)
                ''',
                rows,
            )

        return len(rows)

    # Loads the general trip statistic information, such as if the trips are on weekday or weekend, what route and train they are on, etc
    def load_trip_statistics(self):
        trips_file = os.path.join(self.gtfs_path, 'trips.txt')
        stop_times_file = os.path.join(self.gtfs_path, 'stop_times.txt')
        calendar_file = os.path.join(self.gtfs_path, 'calendar.txt')

        calendar_lookup = {}
        with open(calendar_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                service_id = row.get('service_id')
                if not service_id:
                    continue
                calendar_lookup[service_id] = (
                    self._day_type_from_calendar_row(row),
                    row.get('start_date') or None,
                )

        trip_lookup = {}
        with open(trips_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                trip_id = row.get('trip_id')
                if not trip_id:
                    continue
                trip_lookup[trip_id] = {
                    'route_id': row.get('route_id') or '',
                    'direction_id': self._safe_int(row.get('direction_id')),
                    'service_id': row.get('service_id') or '',
                }

        first_stop_by_trip = {}
        with open(stop_times_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                trip_id = row.get('trip_id')
                if not trip_id or trip_id not in trip_lookup:
                    continue

                stop_sequence = self._safe_int(row.get('stop_sequence'))
                if stop_sequence is None:
                    continue

                existing = first_stop_by_trip.get(trip_id)
                if existing is None or stop_sequence < existing['stop_sequence']:
                    first_stop_by_trip[trip_id] = {
                        'stop_sequence': stop_sequence,
                        'stop_id': row.get('stop_id') or None,
                        'arrival_time': row.get('arrival_time') or None,
                    }

        rows = []
        for trip_id, trip in trip_lookup.items():
            service_id = trip['service_id']
            day_type, start_date = calendar_lookup.get(service_id, ('weekday', None))
            first_stop = first_stop_by_trip.get(trip_id)

            rows.append((
                trip_id,
                trip['route_id'],
                trip['direction_id'],
                first_stop['arrival_time'] if first_stop else None,
                start_date,
                first_stop['stop_id'] if first_stop else None,
                day_type,
            ))

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM trip_statistics')
            cursor.executemany(
                '''
                INSERT INTO trip_statistics(
                    trip_id,
                    route_id,
                    direction_id,
                    start_time,
                    start_date,
                    stop_id,
                    day_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                rows,
            )

        return len(rows)

    # Add all mta events associated with service changes. 
    def load_mta_event_lookup_from_calendar_dates(self):
        calendar_dates_file = os.path.join(self.gtfs_path, 'calendar_dates.txt')

        rows = []
        seen = set()
        with open(calendar_dates_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                service_id = row.get('service_id')
                date = row.get('date')
                exception_type = row.get('exception_type')
                if not service_id or not date or not exception_type:
                    continue

                event_id = f"service_change_{service_id}_{date}_{exception_type}"
                if event_id in seen:
                    continue
                seen.add(event_id)

                if exception_type == '1':
                    event_name = 'Service Added'
                    event_description = f'Added service for {service_id} on {date}.'
                else:
                    event_name = 'Service Removed'
                    event_description = f'Removed service for {service_id} on {date}.'

                rows.append((
                    event_id,
                    event_name,
                    'SERVICE_CHANGE',
                    event_description,
                    1,
                ))

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mta_event_lookup WHERE event_type = 'SERVICE_CHANGE'")
            cursor.executemany(
                '''
                INSERT INTO mta_event_lookup(
                    event_id,
                    event_name,
                    event_type,
                    event_description,
                    is_planned
                ) VALUES (?, ?, ?, ?, ?)
                ''',
                rows,
            )

        return len(rows)

    def _connect(self):
        return sqlite3.connect(self.db_file)

    @staticmethod
    def _safe_int(value):
        if value in (None, ''):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_float(value):
        if value in (None, ''):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _day_type_from_calendar_row(row):
        is_weekday = (
            row.get('monday') == '1'
            or row.get('tuesday') == '1'
            or row.get('wednesday') == '1'
            or row.get('thursday') == '1'
            or row.get('friday') == '1'
        )
        is_weekend = row.get('saturday') == '1' or row.get('sunday') == '1'

        if is_weekday and not is_weekend:
            return 'weekday'
        if is_weekend and not is_weekday:
            return 'weekend'
        return 'mixed'