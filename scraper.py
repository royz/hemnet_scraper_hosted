import os
import re
import csv
import json
from pprint import pprint

import config
import requests
import openpyxl
from bs4 import BeautifulSoup

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' \
             '(KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36'


class Hemnet:
    def __init__(self, location):
        self.location_id = location['id']
        self.location_name = location['city']
        self.results = None
        self.new_results = 0
        self.old_results = 0
        self.session = None
        self.load_results()
        self.init_session()

    def init_session(self):
        self.session = requests.session()
        self.session.headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Referer': '',
            'DNT': '1',
            'User-Agent': USER_AGENT,
            'X-Requested-With': 'XMLHttpRequest',
        }

    def search(self):
        results = []
        for page_num in range(1, 51):
            print(f'{self.location_name}: page {page_num}')
            params = {
                'by': 'creation',
                'housing_form_groups[]': ['houses', 'row_houses', 'apartments'],
                'location_ids[]': self.location_id,
                'order': 'desc',
                'page': str(page_num),
                'preferred_sorting': 'true',
                'new_construction': 'exclude'
            }
            try:
                res = self.session.get('https://www.hemnet.se/bostader', params=params)
                soup = BeautifulSoup(res.content, 'html.parser')
                # list all the search results in current page
                lis = soup.find_all('li', {'class': 'normal-results__hit js-normal-list-item'})

                for li in lis:
                    try:
                        result_id = json.loads(li['data-gtm-item-info'])['id']
                        results.append({
                            'url': li.find('a')['href'],
                            'id': result_id
                        })
                    except Exception as e:
                        print(f'could not get link. error: {e}')
                if len(lis) == 0:
                    break
            except Exception as e:
                print(e)
        return results

    def get_details(self, result):
        try:
            response = self.session.get(result['url'])
            datalayer_text = re.findall(r'dataLayer *?= *?.*?;', response.text)[0]
            datalayer_text = datalayer_text[datalayer_text.index('['):-1]
            datalayer = json.loads(datalayer_text)

            _property = None
            for dl in datalayer:
                _property = dl.get('property')
                if _property:
                    break
            if not _property:
                print('property not found')
                return None

            # get address
            street_address = _property.get('street_address')
            try:
                street_address = street_address.split(',')[0]
            except:
                pass

            # get floor
            try:
                matches = re.findall(r'\d+ ?tr', _property.get('street_address'))
                if len(matches) > 0:
                    floor = re.match(r'\d+', matches[0])[0]
                else:
                    floor = None
            except:
                floor = None

            return {
                'id': _property.get('id'),
                'city': _property.get('location'),
                'street_address': street_address,
                'floor': floor,
                'area': _property.get('living_area'),
                'extra_area': _property.get('supplemental_area'),
                'publication_date': _property.get('publication_date'),
                'complete': False,
                'sold_date': None,
                'matches': []
            }
        except Exception as e:
            print(f'could not get data for [{result["url"]}]. errorL: {e}')
            return None

    @staticmethod
    def parse_area(area_string):
        # remove any extra characters from the area value
        area_string = area_string.strip()
        if area_string.endswith('m²'):
            area_string = area_string[:len('m²')].strip().replace(',', '.')
        area_strings = area_string.split('+')
        area = float(area_strings[0].strip())
        if len(area_strings) > 1:
            extra_area = float(area_strings[1].strip())
        else:
            extra_area = None
        return area, extra_area

    def save_results(self):
        # create the cache folder if it doesn't exist
        os.makedirs(os.path.join(config.BASE_DIR, 'cache'), exist_ok=True)

        with open(os.path.join(config.BASE_DIR, 'cache', f'{self.location_id}.json'), 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2)

    def load_results(self):
        old_result_path = os.path.join(config.CACHE_DIR, f'{self.location_id}.json')
        if os.path.exists(old_result_path):
            with open(old_result_path, encoding='utf-8-sig') as f:
                self.results = json.load(f)
        else:
            self.results = {}

    @staticmethod
    def get_more_data(url):
        headers = {
            'authority': 'www.hemnet.se',
            'user-agent': USER_AGENT,
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
        }

        response = requests.get(url, headers=headers)
        # with open('resp.html', 'w', encoding='utf-8') as f:
        #     f.write(response.text)
        #     quit()

        # find publish date
        matches = re.findall(r'(?<="publication_date":")(.*?)(?=")', response.text)
        if matches:
            publication_date = matches[0]
        else:
            publication_date = None

        # find housing type
        matches = re.findall(r'(?<="housing_form":")(.*?)(?=")', response.text)
        if matches:
            housing_form = matches[0]
        else:
            housing_form = None

        return {
            'publication_date': publication_date,
            'housing_form': housing_form
        }

    def search_sold_properties(self):
        headers = {
            'authority': 'www.hemnet.se',
            'upgrade-insecure-requests': '1',
            'dnt': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.104 Safari/537.36',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'accept-language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7,sv;q=0.6',
        }

        sold_properties = []

        for page_num in range(1, 51):
            print(f'page: {page_num}')
            params = {
                'housing_form_groups[]': ['houses', 'row_houses', 'apartments'],
                'location_ids[]': self.location_id,
                'page': page_num
            }

            response = requests.get('https://www.hemnet.se/salda/bostader', headers=headers, params=params)
            soup = BeautifulSoup(response.content, 'html.parser')
            links = soup.find_all('a', {'class': 'sold-property-listing'})
            for link in links:
                href = link['href']
                sold_properties.append(href)
        return sold_properties

    @staticmethod
    def get_sold_property_id(property_link):
        headers = {
            'authority': 'www.hemnet.se',
            'user-agent': USER_AGENT,
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
        }

        try:
            sold_date = 'sold but date not found'
            resp = requests.get(property_link, headers=headers)

            # with open('hemnet-error.html', 'w', encoding='utf-8') as f:
            #     f.write(resp.text)

            datalayer_text = re.findall(r'(?<=dataLayer = )(.*)(?=;)', resp.text)[0]
            datalayer = json.loads(datalayer_text)
            for dl in datalayer:
                try:
                    if 'property' in dl.keys():
                        prop_id = dl['property']['id']
                    if 'sold_property' in dl.keys():
                        sold_date = dl['sold_property']['sold_at_date']
                except:
                    pass
            return prop_id, sold_date
        except Exception as e:
            return None, None


class Faktakontroll:
    pass


if __name__ == '__main__':
    locations = [{
        'city': 'Stockholms län',
        'id': '17744'
    }, {
        'city': 'Stockholms län',
        'id': '17744'
    }]

    h = Hemnet(locations[0])
    res = h.search()
    pprint(res)
