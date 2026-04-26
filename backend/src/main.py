from mimetypes import init
from sqlite3 import Time


import api.mta_api
import concurrent.futures
import time
import os
from db.init_db import *
from db.static_extractor import static_to_db

def main():
    init_db() 
    
    time.sleep(2) #wait for the database to be initialized before starting to process the feeds
    static_to_db() #extract the static data from the GTFS files and insert it into the database

    #parallel execuation of the feed processing function to speed up the data collection process
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        while True:
            for feed in api.mta_api.feeds:

                executor.submit(api.mta_api.proccess_feed, f"{api.mta_api.base_url}{feed}")
            time.sleep(30) #wait for 30 seconds before processing the feeds again to avoid overwhelming the MTA API with requests
        

if __name__ == "__main__":
    main()
