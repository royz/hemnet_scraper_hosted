import os
import config
from utils import Hemnet
import json
from logger import get_logger

LAST_LOCATION_INDEX_FILE = os.path.join(config.CACHE_DIR, 'last_sold_loc.txt')
SOLD_PROPERTY_CACHE_FILE = os.path.join(config.CACHE_DIR, 'sold-cache.json')


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
    logger = get_logger()
    location = get_location()
    hemnet = Hemnet(location)

    # load old sold properties cache
    try:
        with open(SOLD_PROPERTY_CACHE_FILE) as f:
            sold_property_cache = json.load(f)
    except:
        sold_property_cache = {}

    logger.info(f'getting list of sold properties for: {location["location"]}')

    sold_properties_links = hemnet.search_sold_properties()
    new_sold_properties = [spl for spl in sold_properties_links if spl not in sold_property_cache]
    logger.info(f'{len(sold_properties_links)} sold properties found. {len(new_sold_properties)} new')

    for i, sold_prop_link in enumerate(new_sold_properties):
        sold = hemnet.get_sold_property_date(sold_prop_link)
        if sold:
            logger.debug(f'({i + 1}/{len(new_sold_properties)}) {sold["id"]}: {sold["date"]}')
            sold_property_cache[sold_prop_link] = sold

    all_sold_properties = {sp['id']: sp['date'] for sp in sold_property_cache.values()}

    try:
        with open(SOLD_PROPERTY_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(sold_property_cache, f)
        logger.info('saved sold property cache')
    except:
        logger.error('could not save sold property cache')

    for property_id in hemnet.results.keys():
        if property_id in all_sold_properties:
            hemnet.results[property_id]['sold_date'] = all_sold_properties[property_id]
    hemnet.save_results()


if __name__ == '__main__':
    main()
