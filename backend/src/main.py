from sqlite3 import Time

from db.init_db import DB_PATH, init_db
import api.mta_api
import concurrent.futures
import time
import os

def main():
    init_db()
    time.sleep(2) #wait for the database to be initialized before starting to process the feeds
    print({DB_PATH})

    #parallel execuation of the feed processing function to speed up the data collection process
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(api.mta_api.proccess_feed, f"{api.mta_api.base_url}{api.mta_api.feeds[0]}")
        result = future.result()
        print(result)

if __name__ == "__main__":
    main()
