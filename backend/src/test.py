import sqlite3
import time

import api.mta_api
from db.gtfs_static_loader import GtfsStaticLoader
from db.init_db import DB_PATH, init_db
from db.static_extractor import static_to_db

TEST_ROUTE_ID = 'E'
TEST_FEED = 'nyct%2Fgtfs-ace'
POLL_INTERVAL_SECONDS = 30
MAX_POLL_CYCLES = 20


def _limit_static_tables_to_route(route_id):
    conn = sqlite3.connect(DB_PATH + '/mta.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM route_to_stop WHERE route_id <> ?', (route_id,))
    cursor.execute('DELETE FROM trip_statistics WHERE route_id <> ?', (route_id,))
    conn.commit()
    conn.close()


def main():
    print(f'Initializing single-line test DB for route {TEST_ROUTE_ID}...')
    init_db()

    static_loader = GtfsStaticLoader()
    static_summary = static_loader.execute(include_events=True)

    # Only load timetable rows for F line and trim static support tables to F.
    static_to_db(route_ids=[TEST_ROUTE_ID])
    _limit_static_tables_to_route(TEST_ROUTE_ID)

    print(f'GTFS static entities loaded before route filter: {static_summary}')
    print(f'Static tables limited to route {TEST_ROUTE_ID}')

    feed_url = f"{api.mta_api.base_url}{TEST_FEED}"
    for cycle in range(1, MAX_POLL_CYCLES + 1):
        print(f'Polling cycle {cycle}/{MAX_POLL_CYCLES} from {TEST_FEED} with route filter {TEST_ROUTE_ID}')
        api.mta_api.proccess_feed(feed_url, allowed_routes={TEST_ROUTE_ID})

        if cycle < MAX_POLL_CYCLES:
            time.sleep(POLL_INTERVAL_SECONDS)

    print('F-line test DB run complete.')


if __name__ == '__main__':
    main()
