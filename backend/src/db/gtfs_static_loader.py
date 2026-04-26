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
        calendar_file = os.path.join(self.gtfs_path, 'calendar.txt')

        service_is_weekend = {}
        with open(calendar_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                service_id = row.get('service_id')
                if not service_id:
                    continue
                service_is_weekend[service_id] = (
                    row.get('saturday') == '1' or row.get('sunday') == '1'
                )

        trip_route_lookup = {}
        with open(trips_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                trip_id = row.get('trip_id')
                route_id = row.get('route_id')
                if not trip_id or not route_id:
                    continue
                service_id = row.get('service_id') or ''
                direction_id = self._safe_int(row.get('direction_id'))
                headsign = row.get('trip_headsign') or ''
                trip_route_lookup[trip_id] = {
                    'route_id': route_id,
                    'direction_id': direction_id,
                    'service_is_weekend': service_is_weekend.get(service_id, False),
                    'is_express': self._is_express_trip(route_id, headsign),
                }

        # Pass 1: track longest trip per (route_id, direction_id) by max stop_sequence.
        trip_max_seq = {}
        longest_trip_by_route_dir = {}
        with open(stop_times_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                trip_id = row.get('trip_id')
                trip_info = trip_route_lookup.get(trip_id)
                if not trip_info:
                    continue

                stop_sequence = self._safe_int(row.get('stop_sequence'))
                if stop_sequence is None:
                    continue

                current_max = trip_max_seq.get(trip_id)
                if current_max is None or stop_sequence > current_max:
                    trip_max_seq[trip_id] = stop_sequence

                route_dir_key = (trip_info['route_id'], trip_info['direction_id'])
                existing = longest_trip_by_route_dir.get(route_dir_key)
                if existing is None or trip_max_seq[trip_id] > existing[1]:
                    longest_trip_by_route_dir[route_dir_key] = (trip_id, trip_max_seq[trip_id])

        longest_trip_ids = {trip_id for trip_id, _ in longest_trip_by_route_dir.values()}

        # Pass 2: build feature flags for all route-stop-direction combos and sequence from longest trip.
        route_stop_features = {}
        longest_route_dir_stop_seq = {}

        with open(stop_times_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                trip_id = row.get('trip_id')
                stop_id = row.get('stop_id')
                trip_info = trip_route_lookup.get(trip_id)
                if not trip_id or not stop_id or not trip_info:
                    continue

                route_id = trip_info['route_id']
                direction_id = trip_info['direction_id']
                stop_sequence = self._safe_int(row.get('stop_sequence'))
                if stop_sequence is None:
                    continue

                key = (route_id, stop_id, direction_id)
                existing = route_stop_features.get(key)
                if existing is None:
                    route_stop_features[key] = {
                        'is_weekend': 1 if trip_info['service_is_weekend'] else 0,
                        'is_overnight': 1 if self._row_is_overnight(row) else 0,
                        'is_express': 1 if trip_info['is_express'] else 0,
                    }
                else:
                    if trip_info['service_is_weekend']:
                        existing['is_weekend'] = 1
                    if self._row_is_overnight(row):
                        existing['is_overnight'] = 1
                    if trip_info['is_express']:
                        existing['is_express'] = 1

                if trip_id in longest_trip_ids:
                    longest_route_dir_stop_seq[(route_id, direction_id, stop_id)] = stop_sequence

        rows = [
            (
                route_id,
                stop_id,
                direction_id,
                features['is_weekend'],
                features['is_overnight'],
                features['is_express'],
                longest_route_dir_stop_seq.get((route_id, direction_id, stop_id)),
            )
            for (route_id, stop_id, direction_id), features in route_stop_features.items()
        ]

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM route_to_stop')
            cursor.executemany(
                '''
                INSERT INTO route_to_stop(
                    route_id,
                    stop_id,
                    direction_id,
                    is_weekend,
                    is_overnight,
                    is_express,
                    stop_sequence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
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
                    row.get('end_date') or None,
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
            day_type, start_date, end_date = calendar_lookup.get(service_id, ('weekday', None, None))
            first_stop = first_stop_by_trip.get(trip_id)

            rows.append((
                trip_id,
                trip['route_id'],
                trip['direction_id'],
                service_id,
                first_stop['arrival_time'] if first_stop else None,
                start_date,
                end_date,
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
                    service_id,
                    start_time,
                    start_date,
                    end_date,
                    stop_id,
                    day_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    @staticmethod
    def _is_express_trip(route_id, trip_headsign):
        if route_id and route_id.upper().endswith('X'):
            return True
        return 'express' in (trip_headsign or '').lower()

    @staticmethod
    def _row_is_overnight(row):
        arrival_time = row.get('arrival_time') or ''
        departure_time = row.get('departure_time') or ''
        return (
            GtfsStaticLoader._is_overnight_time(arrival_time)
            or GtfsStaticLoader._is_overnight_time(departure_time)
        )

    @staticmethod
    def _is_overnight_time(value):
        if not value:
            return False
        try:
            hour = int(value.split(':', 1)[0])
            return hour >= 24 or hour < 5
        except (TypeError, ValueError):
            return False