from datetime import datetime, timezone, timedelta
import sqlite3
import traceback

import requests
import os
from google.transit import gtfs_realtime_pb2
from db.init_db import DB_PATH, insert_train_observation, insert_trip_feed_match

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
        response = requests.get(feed_url, timeout=20)
        response.raise_for_status()
    except Exception as e:
         print(f"Error processing feed {feed_url}: {e}")
         return
         
    feed.ParseFromString(response.content)
    routes_seen = set(
        entity.trip_update.trip.route_id 
        for entity in feed.entity 
        if entity.HasField('trip_update'))
    print(f"[{feed_url}] routes in feed: {routes_seen}")
    
    for entity in feed.entity:
        if not entity.HasField('trip_update'):
            continue

        try:
            trip_update = entity.trip_update
            trip = trip_update.trip
            trip_id = trip.trip_id
            route_id = trip.route_id
            direction = trip.direction_id
            start_time = trip.start_time
            start_date = trip.start_date
            realtime_day_type = _day_type_from_start_date(start_date)

            current_stop = _select_realtime_stop(trip_update)
            if current_stop is None:
                continue

            stop_id = current_stop.stop_id
            if not stop_id:
                continue

            arrival = current_stop.arrival if current_stop.HasField("arrival") else None
            departure = current_stop.departure if current_stop.HasField("departure") else None

            realtime_event = arrival or departure
            if realtime_event is None:
                continue

            delay = realtime_event.delay if realtime_event.HasField("delay") else None
            actual_time = realtime_event.time if realtime_event.HasField("time") else 0
            if actual_time == 0:
                continue

            actual_arrical_time = datetime.fromtimestamp(actual_time, tz=timezone.utc).isoformat()
            observation_id = insert_train_observation(trip_id, route_id, actual_arrical_time, delay, stop_id, event_id=None)

            match = _resolve_static_trip_match(
                route_id=route_id,
                direction_id=direction,
                start_time=start_time,
                start_date=start_date,
                realtime_day_type=realtime_day_type,
                realtime_stop_id=stop_id,
                realtime_stop_sequence=current_stop.sequence,
                actual_arrival_iso=actual_arrical_time,
            )
            static_trip_id = match['static_trip_id'] if match else None
            static_stop_id = match['static_stop_id'] if match else None
            static_stop_sequence = match['static_stop_sequence'] if match else None
            scheduled_start_time = match['scheduled_start_time'] if match else None
            scheduled_start_date = match['scheduled_start_date'] if match else None
            scheduled_day_type = match['scheduled_day_type'] if match else None
            schedule_lateness_seconds = _compute_schedule_lateness_seconds(
                actual_arrival_iso=actual_arrical_time,
                realtime_start_time=start_time,
                realtime_start_date=start_date,
                scheduled_start_time=scheduled_start_time,
                scheduled_start_date=scheduled_start_date,
            )
            match_score = match['match_score'] if match else 0.0
            match_method = match['match_method'] if match else 'unmatched'

            insert_trip_feed_match(
                observation_id=observation_id,
                realtime_trip_id=trip_id,
                static_trip_id=static_trip_id,
                route_id=route_id,
                direction_id=direction,
                realtime_start_time=start_time,
                realtime_start_date=start_date,
                scheduled_start_time=scheduled_start_time,
                scheduled_start_date=scheduled_start_date,
                scheduled_day_type=scheduled_day_type,
                realtime_stop_id=stop_id,
                realtime_stop_sequence=current_stop.sequence,
                static_stop_id=static_stop_id,
                static_stop_sequence=static_stop_sequence,
                actual_arrival_time=actual_arrical_time,
                delay_seconds=delay,
                schedule_lateness_seconds=schedule_lateness_seconds,
                match_method=match_method,
                match_score=match_score,
            )
        except Exception as e:
            print(f"Entity processing failed for feed {feed_url}: {e}")
            print(traceback.format_exc())
            continue


def _select_realtime_stop(trip_update):
    """Return the earliest actionable stop update for a trip.

    TripUpdate stop_time_update entries describe scheduled future updates.
    For a single-day operational view, we keep one observation per trip poll
    and use the nearest actionable stop update as the best available proxy.
    """
    if not trip_update.stop_time_update:
        return None

    for stop_update in trip_update.stop_time_update:
        if stop_update.stop_id and (stop_update.HasField("arrival") or stop_update.HasField("departure")):
            return _RealtimeStopSelection(stop_update, stop_time_update_index=stop_update.stop_sequence if stop_update.HasField('stop_sequence') else None)

    return _RealtimeStopSelection(trip_update.stop_time_update[0], stop_time_update_index=0)


def _resolve_static_trip_match(
    route_id,
    direction_id,
    start_time,
    start_date,
    realtime_day_type,
    realtime_stop_id,
    realtime_stop_sequence,
    actual_arrival_iso,
):
    """Resolve a realtime TripDescriptor to the most likely static GTFS trip.

    Primary key is route + direction + start_date + start_time.
    We enrich the result with the scheduled stop sequence for the realtime stop.
    """
    conn = sqlite3.connect(f"{DB_PATH}/mta.db")
    cursor = conn.cursor()

    static_row = None
    match_method = None
    match_score = None

    if start_time:
        try:
            cursor.execute(
                '''
                SELECT trip_id, stop_id, day_type, start_time, start_date
                FROM trip_statistics
                WHERE route_id = ?
                  AND direction_id = ?
                  AND start_time = ?
                  AND (day_type = ? OR day_type = 'mixed')
                  AND (? IS NULL OR start_date IS NULL OR start_date <= ?)
                  AND (? IS NULL OR end_date IS NULL OR end_date >= ?)
                ORDER BY CASE WHEN day_type = ? THEN 0 ELSE 1 END, trip_id
                LIMIT 1
                ''',
                (
                    route_id,
                    direction_id,
                    start_time,
                    realtime_day_type,
                    start_date,
                    start_date,
                    start_date,
                    start_date,
                    realtime_day_type,
                ),
            )
            static_row = cursor.fetchone()
            match_method = 'exact_route_direction_time_day_type'
            match_score = 1.0
        except sqlite3.OperationalError:
            # Compatibility for stale schemas missing end_date.
            cursor.execute(
                '''
                SELECT trip_id, stop_id, day_type, start_time, start_date
                FROM trip_statistics
                WHERE route_id = ?
                  AND direction_id = ?
                  AND start_time = ?
                  AND (day_type = ? OR day_type = 'mixed')
                ORDER BY CASE WHEN day_type = ? THEN 0 ELSE 1 END, trip_id
                LIMIT 1
                ''',
                (
                    route_id,
                    direction_id,
                    start_time,
                    realtime_day_type,
                    realtime_day_type,
                ),
            )
            static_row = cursor.fetchone()
            match_method = 'exact_route_direction_time_day_type_legacy'
            match_score = 0.95

    if static_row is None:
        cursor.execute(
            '''
            SELECT trip_id, stop_id, day_type, start_time, start_date
            FROM trip_statistics
            WHERE route_id = ?
              AND direction_id = ?
              AND start_time = ?
            ORDER BY trip_id
            LIMIT 1
            ''',
            (route_id, direction_id, start_time),
        )
        static_row = cursor.fetchone()
        match_method = 'exact_route_direction_time'
        match_score = 0.8

    if static_row is None:
        fallback_match = _fallback_match_by_nearest_stop_time(
            cursor=cursor,
            route_id=route_id,
            direction_id=direction_id,
            start_date=start_date,
            realtime_day_type=realtime_day_type,
            realtime_stop_id=realtime_stop_id,
            actual_arrival_iso=actual_arrival_iso,
        )
        if fallback_match is not None:
            static_row = (
                fallback_match['static_trip_id'],
                fallback_match['static_stop_id'],
                fallback_match['scheduled_day_type'],
                fallback_match['scheduled_start_time'],
                fallback_match['scheduled_start_date'],
            )
            match_method = fallback_match['match_method']
            match_score = fallback_match['match_score']

    if static_row is None:
        fallback_match = _fallback_match_by_stop_sequence(
            cursor=cursor,
            route_id=route_id,
            direction_id=direction_id,
            start_date=start_date,
            realtime_day_type=realtime_day_type,
            realtime_stop_id=realtime_stop_id,
            realtime_stop_sequence=realtime_stop_sequence,
        )
        if fallback_match is not None:
            static_row = (
                fallback_match['static_trip_id'],
                fallback_match['static_stop_id'],
                fallback_match['scheduled_day_type'],
                fallback_match['scheduled_start_time'],
                fallback_match['scheduled_start_date'],
            )
            match_method = fallback_match['match_method']
            match_score = fallback_match['match_score']

    if static_row is None:
        conn.close()
        return None

    static_trip_id, static_stop_id, day_type, scheduled_start_time, scheduled_start_date = static_row

    cursor.execute(
        '''
        SELECT stop_sequence, stop_id
        FROM train_timetable
        WHERE trip_id = ? AND stop_id = ?
        ORDER BY stop_sequence
        LIMIT 1
        ''',
        (static_trip_id, realtime_stop_id),
    )
    timetable_row = cursor.fetchone()
    if timetable_row is None:
        cursor.execute(
            '''
            SELECT stop_sequence, stop_id
            FROM route_to_stop
            WHERE route_id = ? AND direction_id = ? AND stop_id = ?
            ORDER BY stop_sequence
            LIMIT 1
            ''',
            (route_id, direction_id, realtime_stop_id),
        )
        route_stop_row = cursor.fetchone()
        static_stop_sequence = route_stop_row[0] if route_stop_row else None
    else:
        static_stop_sequence = timetable_row[0]

    conn.close()
    return {
        'static_trip_id': static_trip_id,
        'static_stop_id': static_stop_id,
        'static_stop_sequence': static_stop_sequence,
        'scheduled_start_time': scheduled_start_time,
        'scheduled_start_date': scheduled_start_date,
        'scheduled_day_type': day_type,
        'match_method': match_method,
        'match_score': match_score if match_score is not None else 0.8,
    }


def _fallback_match_by_nearest_stop_time(
    cursor,
    route_id,
    direction_id,
    start_date,
    realtime_day_type,
    realtime_stop_id,
    actual_arrival_iso,
):
    if not actual_arrival_iso:
        return None

    try:
        actual_dt = datetime.fromisoformat(actual_arrival_iso)
    except ValueError:
        return None
    if actual_dt.tzinfo is None:
        actual_dt = actual_dt.replace(tzinfo=timezone.utc)

    candidates = _fetch_stop_candidates(
        cursor=cursor,
        route_id=route_id,
        direction_id=direction_id,
        start_date=start_date,
        realtime_day_type=realtime_day_type,
        realtime_stop_id=realtime_stop_id,
    )
    if not candidates:
        return None

    best = None
    for candidate in candidates:
        (
            static_trip_id,
            static_stop_id,
            scheduled_day_type,
            scheduled_start_time,
            scheduled_start_date,
            static_stop_sequence,
            stop_arrival_time,
            stop_departure_time,
        ) = candidate

        scheduled_stop_time = stop_arrival_time or stop_departure_time
        scheduled_dt = _parse_service_datetime(start_date or scheduled_start_date, scheduled_stop_time)
        if scheduled_dt is None:
            continue

        abs_delta = abs(int((actual_dt - scheduled_dt).total_seconds()))
        if best is None or abs_delta < best['abs_delta']:
            best = {
                'abs_delta': abs_delta,
                'static_trip_id': static_trip_id,
                'static_stop_id': static_stop_id,
                'static_stop_sequence': static_stop_sequence,
                'scheduled_start_time': scheduled_start_time,
                'scheduled_start_date': scheduled_start_date,
                'scheduled_day_type': scheduled_day_type,
            }

    if best is None:
        return None

    # Score decays as stop-time difference grows.
    score = max(0.35, 0.75 - min(best['abs_delta'], 3600) / 7200.0)
    best['match_method'] = 'fallback_route_direction_stop_nearest_time'
    best['match_score'] = round(score, 3)
    return best


def _fallback_match_by_stop_sequence(
    cursor,
    route_id,
    direction_id,
    start_date,
    realtime_day_type,
    realtime_stop_id,
    realtime_stop_sequence,
):
    if realtime_stop_sequence is None:
        return None

    candidates = _fetch_stop_candidates(
        cursor=cursor,
        route_id=route_id,
        direction_id=direction_id,
        start_date=start_date,
        realtime_day_type=realtime_day_type,
        realtime_stop_id=realtime_stop_id,
    )
    if not candidates:
        return None

    best = None
    for candidate in candidates:
        (
            static_trip_id,
            static_stop_id,
            scheduled_day_type,
            scheduled_start_time,
            scheduled_start_date,
            static_stop_sequence,
            _,
            _,
        ) = candidate

        if static_stop_sequence is None:
            continue
        seq_delta = abs(static_stop_sequence - realtime_stop_sequence)
        if best is None or seq_delta < best['seq_delta']:
            best = {
                'seq_delta': seq_delta,
                'static_trip_id': static_trip_id,
                'static_stop_id': static_stop_id,
                'static_stop_sequence': static_stop_sequence,
                'scheduled_start_time': scheduled_start_time,
                'scheduled_start_date': scheduled_start_date,
                'scheduled_day_type': scheduled_day_type,
            }

    if best is None:
        return None

    score = max(0.3, 0.65 - min(best['seq_delta'], 12) / 40.0)
    best['match_method'] = 'fallback_route_direction_stop_sequence'
    best['match_score'] = round(score, 3)
    return best


def _fetch_stop_candidates(
    cursor,
    route_id,
    direction_id,
    start_date,
    realtime_day_type,
    realtime_stop_id,
):
    try:
        cursor.execute(
            '''
            SELECT t.trip_id,
                   t.stop_id,
                   t.day_type,
                   t.start_time,
                   t.start_date,
                   tt.stop_sequence,
                   tt.arrival_time,
                   tt.departure_time
            FROM trip_statistics t
            JOIN train_timetable tt ON tt.trip_id = t.trip_id
            WHERE t.route_id = ?
              AND t.direction_id = ?
              AND tt.stop_id = ?
              AND (t.day_type = ? OR t.day_type = 'mixed')
              AND (? IS NULL OR t.start_date IS NULL OR t.start_date <= ?)
              AND (? IS NULL OR t.end_date IS NULL OR t.end_date >= ?)
            ''',
            (
                route_id,
                direction_id,
                realtime_stop_id,
                realtime_day_type,
                start_date,
                start_date,
                start_date,
                start_date,
            ),
        )
    except sqlite3.OperationalError:
        cursor.execute(
            '''
            SELECT t.trip_id,
                   t.stop_id,
                   t.day_type,
                   t.start_time,
                   t.start_date,
                   tt.stop_sequence,
                   tt.arrival_time,
                   tt.departure_time
            FROM trip_statistics t
            JOIN train_timetable tt ON tt.trip_id = t.trip_id
            WHERE t.route_id = ?
              AND t.direction_id = ?
              AND tt.stop_id = ?
              AND (t.day_type = ? OR t.day_type = 'mixed')
            ''',
            (
                route_id,
                direction_id,
                realtime_stop_id,
                realtime_day_type,
            ),
        )

    return cursor.fetchall()


def _day_type_from_start_date(start_date):
    if not start_date:
        return 'weekday'
    try:
        dt = datetime.strptime(start_date, "%Y%m%d")
    except ValueError:
        return 'weekday'
    return 'weekend' if dt.weekday() >= 5 else 'weekday'


def _compute_schedule_lateness_seconds(
    actual_arrival_iso,
    realtime_start_time,
    realtime_start_date,
    scheduled_start_time,
    scheduled_start_date,
):
    if not actual_arrival_iso or not scheduled_start_time:
        return None

    try:
        actual_dt = datetime.fromisoformat(actual_arrival_iso)
    except ValueError:
        return None

    service_date = scheduled_start_date or realtime_start_date
    if not service_date:
        return None

    scheduled_dt = _parse_service_datetime(service_date, scheduled_start_time)
    if scheduled_dt is None:
        return None

    if actual_dt.tzinfo is None:
        actual_dt = actual_dt.replace(tzinfo=timezone.utc)

    return int((actual_dt - scheduled_dt).total_seconds())


def _parse_service_datetime(service_date, gtfs_time):
    try:
        base_date = datetime.strptime(str(service_date), "%Y%m%d")
        hour_str, minute_str, second_str = gtfs_time.split(':')
        hour = int(hour_str)
        minute = int(minute_str)
        second = int(second_str)
    except (ValueError, TypeError):
        return None

    days_offset, normalized_hour = divmod(hour, 24)
    return datetime(
        base_date.year,
        base_date.month,
        base_date.day,
        normalized_hour,
        minute,
        second,
        tzinfo=timezone.utc,
    ) + timedelta(days=days_offset)


class _RealtimeStopSelection:
    def __init__(self, stop_update, stop_time_update_index=None):
        self._stop_update = stop_update
        self.sequence = stop_time_update_index

    def __getattr__(self, item):
        return getattr(self._stop_update, item)

            

  
def process_daily_schedule():
    for feed in feeds:
        feed_url = base_url + feed
        proccess_feed(feed_url)
    

