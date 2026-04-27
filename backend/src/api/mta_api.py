from datetime import datetime, timezone, timedelta
import re
import sqlite3
import traceback
from zoneinfo import ZoneInfo

import requests
import os
from google.transit import gtfs_realtime_pb2
from db.init_db import DB_PATH, insert_train_observation, insert_observation_diagnostic

current_dir = os.path.dirname(os.path.abspath(__file__))
NY_TZ = ZoneInfo("America/New_York")


base_url = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/"
stops = ""
feeds = [
    "nyct%2Fgtfs", "nyct%2Fgtfs-ace", "nyct%2Fgtfs-bdfm", 
    "nyct%2Fgtfs-g", "nyct%2Fgtfs-l", "nyct%2Fgtfs-si", 
    "nyct%2Fgtfs-nqrw", "nyct%2Fgtfs-jz"
]

def proccess_feed(feed_url, allowed_routes=None):
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
            if allowed_routes and route_id not in allowed_routes:
                continue
            direction = trip.direction_id
            start_date = trip.start_date

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

            actual_time = realtime_event.time if realtime_event.HasField("time") else 0
            if actual_time == 0:
                continue

            actual_arrical_time = datetime.fromtimestamp(actual_time, tz=timezone.utc).isoformat()

            closest = _find_best_static_match(
                route_id=route_id,
                direction_id=direction,
                realtime_trip_id=trip_id,
                realtime_start_date=start_date,
                realtime_stop_id=stop_id,
                actual_arrival_iso=actual_arrical_time,
            )

            delay = None
            if closest:
                computed_delay = _compute_schedule_delay_seconds(
                    static_trip_id=closest['static_trip_id'],
                    stop_id=stop_id,
                    actual_arrival_iso=actual_arrical_time,
                    realtime_start_date=start_date,
                    scheduled_stop_time=closest['stop_schedule_time'],
                )
                if computed_delay is not None:
                    delay = computed_delay
                print(
                    f"Match {trip_id} -> {closest['static_trip_id']} "
                    f"(stop delta {closest['stop_time_delta_seconds']}s, delay {delay}s)"
                )
            else:
                print(f"No static match for {trip_id} — recording observation without delay")

            observation_id = insert_train_observation(trip_id, route_id, actual_arrical_time, delay, stop_id, event_id=None)
            if closest:
                _record_match_diagnostics(
                    observation_id=observation_id,
                    realtime_trip_id=trip_id,
                    static_trip_id=closest['static_trip_id'],
                    stop_time_delta_seconds=closest['stop_time_delta_seconds'],
                    has_stop_schedule=closest['has_stop_schedule'],
                    direction_token_match=closest['direction_token_match'],
                    computed_delay=delay,
                )
        except Exception as e:
            print(f"Entity processing failed for feed {feed_url}: {e}")
            print(traceback.format_exc())
            continue


def _select_realtime_stop(trip_update):
    """Return the best stop update to use for delay calculation.

    Prefers the most recently-passed stop (historical actual time) over
    predicted future stops, since historical times give accurate delays.
    Falls back to the first upcoming stop, then any stop with timing data.
    """
    if not trip_update.stop_time_update:
        return None

    now_ts = datetime.now(timezone.utc).timestamp()

    best_past: tuple | None = None   # (timestamp, stop_update)
    first_future = None

    for su in trip_update.stop_time_update:
        if not su.stop_id:
            continue
        event = su.arrival if su.HasField("arrival") else (su.departure if su.HasField("departure") else None)
        if event is None:
            continue
        t = event.time if event.HasField("time") else 0
        if t <= 0:
            continue
        if t <= now_ts:
            if best_past is None or t > best_past[0]:
                best_past = (t, su)
        elif first_future is None:
            first_future = su

    if best_past:
        return _RealtimeStopSelection(best_past[1])
    if first_future:
        return _RealtimeStopSelection(first_future)

    # Fallback: first stop with any timing
    for su in trip_update.stop_time_update:
        if su.stop_id and (su.HasField("arrival") or su.HasField("departure")):
            return _RealtimeStopSelection(su)

    return _RealtimeStopSelection(trip_update.stop_time_update[0])


def _find_best_static_match(
    route_id,
    direction_id,
    realtime_trip_id,
    realtime_start_date,
    realtime_stop_id,
    actual_arrival_iso,
):
    """Match a realtime trip to a static trip using the embedded 6-digit time code.

    MTA NYCT trip IDs share a 6-digit time token across service periods, e.g.:
        Realtime: '012850_J..S'
        Static:   'BFA25GEN-J056-Weekday-00_012850_J..S12R'

    Returns None if no static trip contains the same time code — the caller
    skips insertion in that case so no unreliable data enters the database.
    """
    time_code = _extract_time_code_from_trip_id(realtime_trip_id)
    if not time_code:
        return None

    realtime_day_type = _day_type_from_start_date(realtime_start_date)
    # Underscores around the code ensure we match the delimiter-bounded token,
    # not a coincidental substring inside another number.
    pattern = f'%_{time_code}_%'

    conn = sqlite3.connect(f"{DB_PATH}/mta.db")
    cursor = conn.cursor()
    try:
        try:
            cursor.execute(
                '''
                SELECT t.trip_id, t.direction_id, t.start_time,
                       tt.arrival_time, tt.departure_time
                FROM trip_statistics t
                LEFT JOIN train_timetable tt
                    ON tt.trip_id = t.trip_id AND tt.stop_id = ?
                WHERE t.route_id = ?
                  AND t.trip_id LIKE ?
                  AND (t.day_type = ? OR t.day_type = 'mixed')
                  AND (? IS NULL OR t.start_date IS NULL OR t.start_date <= ?)
                  AND (? IS NULL OR t.end_date IS NULL OR t.end_date >= ?)
                ''',
                (
                    realtime_stop_id, route_id, pattern, realtime_day_type,
                    realtime_start_date, realtime_start_date,
                    realtime_start_date, realtime_start_date,
                ),
            )
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            cursor.execute(
                '''
                SELECT t.trip_id, t.direction_id, t.start_time,
                       tt.arrival_time, tt.departure_time
                FROM trip_statistics t
                LEFT JOIN train_timetable tt
                    ON tt.trip_id = t.trip_id AND tt.stop_id = ?
                WHERE t.route_id = ?
                  AND t.trip_id LIKE ?
                  AND (t.day_type = ? OR t.day_type = 'mixed')
                ''',
                (realtime_stop_id, route_id, pattern, realtime_day_type),
            )
            rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        return None

    realtime_direction_token = _extract_trip_token_direction(realtime_trip_id)

    # Direction matching breaks ties when multiple static trips share the same
    # time code (uncommon but possible on shared-track routes).
    best = None
    for static_trip_id, static_direction_id, sched_start, stop_arr, stop_dep in rows:
        stop_schedule_time = stop_arr or stop_dep

        # Apply the same overnight correction as _compute_schedule_delay_seconds.
        effective_date = realtime_start_date
        if sched_start:
            try:
                if int(str(sched_start).split(':')[0]) >= 24:
                    adjusted = datetime.strptime(str(realtime_start_date), "%Y%m%d") - timedelta(days=1)
                    effective_date = adjusted.strftime("%Y%m%d")
            except (ValueError, IndexError):
                pass

        stop_delta = None
        if stop_schedule_time and actual_arrival_iso:
            stop_delta = _compute_time_delta_seconds(
                actual_arrival_iso=actual_arrival_iso,
                service_date=effective_date,
                gtfs_time=stop_schedule_time,
            )

        score = 0
        direction_token_match = None
        static_direction_token = _extract_trip_token_direction(static_trip_id)
        if realtime_direction_token and static_direction_token:
            direction_token_match = (realtime_direction_token == static_direction_token)
            if not direction_token_match:
                score += 3600
        if direction_token_match is None and direction_id in (0, 1) and static_direction_id in (0, 1):
            if static_direction_id != direction_id:
                score += 600

        if best is None or score < best['match_score']:
            best = {
                'static_trip_id': static_trip_id,
                'stop_schedule_time': stop_schedule_time,
                'stop_time_delta_seconds': stop_delta,
                'has_stop_schedule': stop_schedule_time is not None,
                'direction_token_match': direction_token_match,
                'match_score': score,
            }

    return best


def _day_type_from_start_date(start_date):
    if not start_date:
        return 'weekday'
    try:
        dt = datetime.strptime(start_date, "%Y%m%d")
    except ValueError:
        return 'weekday'
    return 'weekend' if dt.weekday() >= 5 else 'weekday'


def _extract_time_code_from_trip_id(trip_id: str | None) -> str | None:
    """Return the 6-digit time token embedded in an MTA NYCT trip_id.

    Both realtime and static trip IDs contain this token separated by underscores:
        Realtime: '012850_J..S'           → '012850'
        Static:   '..._012850_J..S12R'   → '012850'
    """
    if not trip_id:
        return None
    for tok in str(trip_id).split('_'):
        if re.match(r'^\d{6}$', tok):
            return tok
    return None


def _compute_schedule_delay_seconds(
    static_trip_id,
    stop_id,
    actual_arrival_iso,
    realtime_start_date,
    scheduled_stop_time=None,
):
    if not static_trip_id or not stop_id or not actual_arrival_iso or not realtime_start_date:
        return None

    conn = sqlite3.connect(f"{DB_PATH}/mta.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
            SELECT arrival_time, departure_time
            FROM train_timetable
            WHERE trip_id = ? AND stop_id = ?
            ORDER BY stop_sequence
            LIMIT 1
            ''',
            (static_trip_id, stop_id),
        )
        row = cursor.fetchone()

        cursor.execute(
            "SELECT start_time FROM trip_statistics WHERE trip_id = ? LIMIT 1",
            (static_trip_id,),
        )
        st_row = cursor.fetchone()
    finally:
        conn.close()

    scheduled_gtfs_time = scheduled_stop_time or ((row[0] or row[1]) if row else None)
    if not scheduled_gtfs_time:
        return None

    effective_start_date = realtime_start_date
    if st_row and st_row[0]:
        try:
            if int(str(st_row[0]).split(':')[0]) >= 24:
                adjusted = datetime.strptime(str(realtime_start_date), "%Y%m%d") - timedelta(days=1)
                effective_start_date = adjusted.strftime("%Y%m%d")
        except (ValueError, IndexError):
            pass

    return _compute_signed_delay_seconds(actual_arrival_iso, effective_start_date, scheduled_gtfs_time)


def _compute_signed_delay_seconds(actual_arrival_iso, service_date, gtfs_time):
    scheduled_dt = _parse_service_datetime(service_date, gtfs_time)
    if scheduled_dt is None:
        return None

    try:
        actual_dt = datetime.fromisoformat(actual_arrival_iso)
    except ValueError:
        return None

    if actual_dt.tzinfo is None:
        actual_dt = actual_dt.replace(tzinfo=timezone.utc)

    return int((actual_dt - scheduled_dt).total_seconds())


def _compute_time_delta_seconds(actual_arrival_iso, service_date, gtfs_time):
    signed = _compute_signed_delay_seconds(actual_arrival_iso, service_date, gtfs_time)
    return abs(signed) if signed is not None else None


def _extract_trip_token_direction(trip_id):
    token = str(trip_id or '')
    north_idx = token.rfind('..N')
    south_idx = token.rfind('..S')
    if north_idx == -1 and south_idx == -1:
        return None
    return 'N' if north_idx > south_idx else 'S'


def _record_match_diagnostics(
    observation_id,
    realtime_trip_id,
    static_trip_id,
    stop_time_delta_seconds,
    has_stop_schedule,
    direction_token_match,
    computed_delay,
):
    insert_observation_diagnostic(
        observation_id,
        'match_debug',
        (
            f"realtime_trip_id={realtime_trip_id};static_trip_id={static_trip_id};"
            f"stop_time_delta_seconds={stop_time_delta_seconds};"
            f"has_stop_schedule={has_stop_schedule};"
            f"direction_token_match={direction_token_match};"
            f"computed_delay_seconds={computed_delay}"
        ),
    )

    if direction_token_match is False:
        insert_observation_diagnostic(
            observation_id,
            'direction_token_mismatch',
            f"realtime_trip_id={realtime_trip_id};static_trip_id={static_trip_id}",
        )

    if not has_stop_schedule:
        insert_observation_diagnostic(
            observation_id,
            'stop_missing_on_matched_trip',
            f"realtime_trip_id={realtime_trip_id};static_trip_id={static_trip_id}",
        )

    if computed_delay is not None and abs(computed_delay) > 900:
        insert_observation_diagnostic(
            observation_id,
            'large_abs_delay',
            f"delay_seconds={computed_delay};realtime_trip_id={realtime_trip_id};static_trip_id={static_trip_id}",
        )


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

    local_dt = datetime(
        base_date.year,
        base_date.month,
        base_date.day,
        normalized_hour,
        minute,
        second,
        tzinfo=NY_TZ,
    ) + timedelta(days=days_offset)

    return local_dt.astimezone(timezone.utc)


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
    

