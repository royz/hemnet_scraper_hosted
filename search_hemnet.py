import os
import config
from utils import Hemnet
from config import logger

LAST_LOCATION_INDEX_FILE = os.path.join(config.CACHE_DIR, 'last_loc.txt')


def get_location():
    locations = config.locations

    # read index of last searched location
    try:
        with open(LAST_LOCATION_INDEX_FILE) as f:
            last_loc_index = int(f.read())
            new_loc_index = (last_loc_index + 1) % len(locations)
    except:
        new_loc_index = 0

    # save the index of current location
    with open(LAST_LOCATION_INDEX_FILE, 'w') as f:
        f.write(str(new_loc_index))

    return locations[new_loc_index]


def main():
    location = get_location()
    hemnet = Hemnet(location)
    search_results = hemnet.search()

    results_count = len(search_results)
    logger.info(f'{results_count} new results found for: {location["location"]}')

    for i, search_result in enumerate(search_results):
        if i == (results_count - 1) or (i + 1) % 10 == 0 and i != 1:
            logger.info(f'{i + 1} of {results_count} properties searched on hemnet')
        hemnet.get_details(search_result)

    hemnet.save_results()


if __name__ == '__main__':
    main()
