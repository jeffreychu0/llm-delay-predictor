import db.init_db
import api.mta_api
import concurrent.futures


def main():
    db.init_db()
    print("Database initialized successfully.")

    #parallel execuation of the feed processing function to speed up the data collection process
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(api.mta_api.proccess_feed, f"{api.mta_api.base_url}{api.mta_api.feeds[0]}")
        result = future.result()
        print(result)

if __name__ == "__main__":
    main()
