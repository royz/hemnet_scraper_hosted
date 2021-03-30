import os
import json
import time
import pytz
import config
import random
import datetime
from utils import Faktakontroll, Hemnet

SOLD_PROPERTY_CACHE_FILE = os.path.join(config.CACHE_DIR, 'sold-cache.json')
logger = config.logger


class Location:
    def __init__(self):
        self.last_loc_index = 0

    @property
    def next(self) -> (dict or None, str or None):
        """
        :return: hemnet result, hemnet location
        """
        locations = config.locations
        new_loc_index = (self.last_loc_index + 1) % len(locations)
        self.last_loc_index = new_loc_index
        loc = locations[new_loc_index]

        # read the cache file
        cache_file = os.path.join(config.CACHE_DIR, f'{loc["id"]}.json')
        try:
            logger.debug(f'reading cache: {cache_file}')
            with open(cache_file, encoding='utf-8-sig') as f:
                cache = json.load(f)
                for loc_id, info in cache.items():
                    # check on faktakontroll if there is no match found previously and the script
                    # tried to find it less than a certain times
                    if info.get('matches') is None and info['try_count'] < config.fk_max_retry:
                        return info, loc
                return None, None
        except Exception as e:
            logger.error(f'could not read {cache_file}. error: {e}')
            return None, None


def main():
    location = Location()
    faktakontroll = Faktakontroll()
    while True:

        # run the script between 8 - 20 swedish time
        if config.faktakontroll_limited:
            now = datetime.datetime.now(pytz.timezone('Europe/Stockholm'))
            hour = now.hour
            minute = str(now.minute).rjust(2, '0')
            if hour < 8 or hour > 20:
                print(f'current time: {hour}:{minute}. office hour not started yet')
                time.sleep(15 * 60)
                continue

        try:
            hemnet_result = None
            hemnet_location = None

            # try to get location for the same number of times as the  total number of locations
            #  in case, new search result for a location on hemnet not found
            for _ in config.locations:
                hemnet_result, hemnet_location = location.next
                if hemnet_result:
                    break

            if not hemnet_result or not hemnet_location:
                logger.info('new hemnet result not found')
                time.sleep(15 * 60)
                continue

            hemnet = Hemnet(hemnet_location)
            fk_search_str = f'{hemnet_result["street_address"]}, {hemnet_result["city"]}'
            logger.info(f'searching faktakontroll ({hemnet_location["location"]}): {fk_search_str}')

            # search on faktakontroll
            results = faktakontroll.search(fk_search_str)
            matches_found = False

            # if results is not none (results were returned from fk)
            if results is not None:
                # find matches from faktakontroll search results
                matches = faktakontroll.find_matches(hemnet_result, results)
                matches_found = len(matches) > 0
                logger.info(f'{len(results)} results found on faktakontroll. {len(matches)} matches')
                # save the matches on hemnet cache and set complete as True
                hemnet.results[hemnet_result["id"]]['matches'] = matches
                hemnet.results[hemnet_result["id"]]['complete'] = True

            hemnet.results[hemnet_result["id"]]['try_count'] += 1
            hemnet.save_results()

            # if matches found then save the excel file
            if matches_found:
                hemnet.save_xlsx()

        except Exception as e:
            logger.critical(e)


if __name__ == '__main__':
    main()
