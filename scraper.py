import os
import re
import csv
import time
import json
from pprint import pprint
import config
import requests
from bs4 import BeautifulSoup

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' \
             '(KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36'


class Hemnet:
    def __init__(self, location):
        self.location_id = location['id']
        self.location_name = location['city']
        self.results = None
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

    def save_results(self):
        # create the cache folder if it doesn't exist
        os.makedirs(config.CACHE_DIR, exist_ok=True)

        with open(os.path.join(config.CACHE_DIR, f'{self.location_id}.json'), 'w', encoding='utf-8-sig') as f:
            json.dump(self.results, f, indent=2)

    def load_results(self):
        old_result_path = os.path.join(config.CACHE_DIR, f'{self.location_id}.json')
        if os.path.exists(old_result_path):
            with open(old_result_path, encoding='utf-8-sig') as f:
                self.results = json.load(f)
        else:
            self.results = {}

    def search_sold_properties(self):
        sold_property_links = []
        print('getting sold properties on hemnet')
        for page_num in range(1, 51):
            print(f'page: {page_num}')
            params = {
                'housing_form_groups[]': ['houses', 'row_houses', 'apartments'],
                'location_ids[]': self.location_id,
                'page': page_num
            }

            response = self.session.get('https://www.hemnet.se/salda/bostader', params=params)
            soup = BeautifulSoup(response.content, 'html.parser')
            links = soup.find_all('a', {'class': 'sold-property-listing'})
            for link in links:
                href = link['href']
                sold_property_links.append(href)
        return sold_property_links

    def get_sold_property_date(self, property_link):
        try:
            sold_date = 'date not found'
            prop_id = None
            resp = self.session.get(property_link)
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
    def __init__(self):
        self.access_token = None
        self.access_token_valid_till = 0
        self.session = requests.session()
        self.session.headers = {'api-key': config.fk_api_key}

    def get_token(self):
        if self.access_token and self.access_token_valid_till > time.time():
            return self.access_token

        try:
            response = requests.post(f'{config.host}/getToken', headers={
                'api-key': config.fk_api_key
            })
            if response.status_code == 200:
                data = response.json()
                self.access_token = data['accessToken']
                self.access_token_valid_till = time.time() + data['validFor']
                print(f'faktakontroll access token updated. valid for: {data["validFor"]}s')
                return self.access_token
            else:
                print('could not get access token for faktakontroll')
                return None
        except:
            print('could not get access token for faktakontroll')
            return None


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
