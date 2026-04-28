import api.mta_api
import concurrent.futures
import time
from db.init_db import init_db, view_all_made_stops, view_static_timetable_for_all
from db.gtfs_static_loader import GtfsStaticLoader
from db.static_extractor import static_to_db

from chatbot import Chatbot
POLL_INTERVAL_SECONDS = 30


def main():
    init_db()
    view_all_made_stops()
    view_static_timetable_for_all()

    static_loader = GtfsStaticLoader()
    

    # Wait for DB initialization before starting static loads.
    time.sleep(2)
    static_summary = static_loader.execute(include_events=True)
    static_to_db()

    

    time.sleep(15)
    view_all_made_stops()
    view_static_timetable_for_all()
 
    print(f"GTFS static entities loaded: {static_summary}")
    print("Static DB Formed")

    # Process all configured realtime feeds in parallel.
    with concurrent.futures.ThreadPoolExecutor() as executor:
        while True:
            futures = []
            for feed in api.mta_api.feeds:
                futures.append(executor.submit(api.mta_api.proccess_feed, f"{api.mta_api.base_url}{feed}"))

            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Feed worker failed: {e}")

            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
