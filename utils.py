import os
import random
import re
import time
import json
import config
import requests
from bs4 import BeautifulSoup

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' \
             '(KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36'


class Hemnet:
    def __init__(self, location):
        self.location_id = location['id']
        self.location_name = location['location']
        self.results = None
        self.session = None
        self.ignored_location_ids = None
        self.load_ignored_locations()
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
                        if result_id not in self.ignored_location_ids and result_id not in self.results:
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
                return False

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

            property_id = str(_property.get('id'))

            self.results[property_id] = {
                'id': property_id,
                'city': _property.get('location'),
                'street_address': street_address,
                'floor': floor,
                'area': _property.get('living_area'),
                'house_type': _property.get('housing_form') or '',
                'extra_area': _property.get('supplemental_area'),
                'publication_date': _property.get('publication_date'),
                'complete': False,
                'sold_date': None,
                'matches': []
            }
            return True
        except Exception as e:
            print(f'could not get data for [{result["url"]}]. errorL: {e}')
            return False

    def save_results(self):
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(config.CACHE_DIR, f'{self.location_id}.json')

        # other scripts might try to access this file at the same time.
        # so try to save it 3 times if failed to save
        for _ in range(3):
            try:
                with open(cache_file, 'w', encoding='utf-8-sig') as f:
                    json.dump(self.results, f, indent=2)
                print(f'cache saved as: {cache_file}')
                break
            except:
                time.sleep(random.randint(3, 10))

    def load_results(self):
        old_result_path = os.path.join(config.CACHE_DIR, f'{self.location_id}.json')
        if os.path.exists(old_result_path):
            with open(old_result_path, encoding='utf-8-sig') as f:
                self.results = json.load(f)
        else:
            self.results = {}

    def load_ignored_locations(self):
        try:
            with open(os.path.join(config.CACHE_DIR, 'ignored.json')) as f:
                self.ignored_location_ids = json.load(f)
        except:
            self.ignored_location_ids = []

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
            try:
                response = self.session.get('https://www.hemnet.se/salda/bostader', params=params)
                soup = BeautifulSoup(response.content, 'html.parser')
                links = soup.find_all('a', {'class': 'sold-property-listing'})
            except:
                links = []
            for link in links:
                try:
                    href = link['href']
                    sold_property_links.append(href)
                except:
                    pass
        return sold_property_links

    def get_sold_property_date(self, property_link):
        sold_date = 'date not found'
        prop_id = None
        try:
            resp = self.session.get(property_link)
            datalayer_text = re.findall(r'(?<=dataLayer = )(.*)(?=;)', resp.text)[0]
            datalayer = json.loads(datalayer_text)
            for dl in datalayer:
                try:
                    if 'property' in dl.keys():
                        prop_id = str(dl['property']['id'])
                    if 'sold_property' in dl.keys():
                        sold_date = dl['sold_property']['sold_at_date']
                except:
                    pass
            if prop_id:
                return {'date': sold_date, 'id': prop_id}
        except Exception as e:
            return None


class Faktakontroll:
    def __init__(self):
        self.access_token = None
        self.access_token_valid_till = 0
        self.token_server_session = requests.session()
        self.token_server_session.headers = {'api-key': config.fk_api_key}

    @property
    def faktakontroll_headers(self):
        return {
            'Connection': 'keep-alive',
            'Accept': 'application/json, text/plain, */*',
            'X-Initialized-At': str(int(time.time() * 1000)),
            'X-Auth-Token': self.get_token(),
            'User-Agent': USER_AGENT,
            'DNT': '1',
            'Content-Type': 'application/json;charset=UTF-8',
            'Origin': 'https://www.faktakontroll.se',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Referer': 'https://www.faktakontroll.se/app/sok',
            'Accept-Language': 'en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
        }

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

    def search(self, search_string, try_count=0):

        data = {
            "searchString": search_string,
            "filterType": "p",
            "subscriptionRefNo": "20.750.025.01"
        }
        try:
            response = requests.post('https://www.faktakontroll.se/app/api/search',
                                     headers=self.faktakontroll_headers, json=data)

            # if failed to get 200 response then try once more
            if response.status_code != 200:
                if try_count == 0:
                    print('could not get result from faktakontroll. retrying...')
                    return self.search(search_string, 1)
                else:
                    print('could not get result from faktakontroll')
                    return None

            data = response.json()
            results = data['hits']
            return [result['individual'] for result in results if result.get('individual')]

        except Exception as e:
            if try_count == 0:
                print(f'error while searching address on faktakontroll. error: {e}. retrying...')
                return self.search(search_string, 1)
            else:
                print(f'error while searching address on faktakontroll. error: {e}')
                return None

    def get_more_details(self, result_id):
        params = {'subscriptionRefNo': '20.750.025.01'}

        try:
            response = requests.get(f'https://www.faktakontroll.se/app/api/search/entity/{result_id}',
                                    headers=self.faktakontroll_headers, params=params)

            data = response.json()['individual']

            try:
                phone_numbers = [phone_number['phoneNumber'] for phone_number in data['phoneNumbers']]
            except:
                phone_numbers = []

            return {
                'numbers': phone_numbers,
                'age': data.get('age'),
                'gender': data.get('gender'),
                'person_number': data.get('personalNumber')
            }
        except:
            return {
                'numbers': [],
                'age': None,
                'gender': None,
                'person_number': None
            }

    def find_matches(self, hemnet_result, faktakontroll_results):
        matches = []
        for result in faktakontroll_results:
            is_match = True

            # get floor number
            street_address = result['fbfStreetAddress']

            if 'lgh' in street_address:
                staddr = street_address[street_address.index('lgh'):]
                floor = int(re.findall(r'\d', staddr)[1])
                try:
                    apartment = re.findall(r'\d{4}', staddr)[0]
                except:
                    apartment = None
            else:
                floor = None
                apartment = None

            # get name
            try:
                first_name = result.get('firstNames')
                middle_name = result.get('middleNames')
                last_name = result.get('lastNames')

                name = first_name or ''
                if middle_name:
                    name += f' {middle_name}'
                if last_name:
                    name += f' {last_name}'
            except:
                name = ''

            # get area
            try:
                area = result['housingInfo']['area']
            except:
                area = None

            # check if the data matches with hemnet data
            potential_match = {'full_match': True}

            try:
                if hemnet_result['area'] == area:
                    pass
                elif area - 1 < hemnet_result['area'] < area + 1:
                    potential_match['full_match'] = False
                else:
                    is_match = False
            except:
                is_match = False

            if (hemnet_result['floor'] is None and floor == 0) or (hemnet_result['floor'] == 0 and floor is None):
                is_match = False

            elif hemnet_result['floor'] and floor:
                # if both hemnet and faktakontroll have floor info then check if they match
                if hemnet_result['floor'] != floor:
                    # if the floors don't match, then don't include them as a match
                    is_match = False

            if is_match:
                extra_info = self.get_more_details(result['id'])
                potential_match.update(extra_info)

                potential_match.update({
                    'name': name,
                    'floor': floor,
                    'apartment': apartment,
                    'street_address': street_address
                })
                matches.append(potential_match)
        return matches
