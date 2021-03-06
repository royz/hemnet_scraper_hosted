import os
import re
import time
import json
import config
import random
import openpyxl
import requests
from bs4 import BeautifulSoup

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' \
             '(KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36'

logger = config.logger


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
            logger.info(f'{self.location_name}: page {page_num}')
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
                        logger.error(f'could not get link. error: {e}')
                if len(lis) == 0:
                    break
            except Exception as e:
                logger.error(e)
        return results

    def get_details(self, result):
        try:
            # get the response
            response = self.session.get(result['url'])

            # get datalayer text
            datalayer_text = re.findall(r'dataLayer *?= *?.*?;', response.text)[0]
            datalayer_text = datalayer_text[datalayer_text.index('['):-1]
            datalayer = json.loads(datalayer_text)

            # get property details from datalayer
            _property = None
            for dl in datalayer:
                _property = dl.get('property')
                if _property:
                    break
            if not _property:
                logger.error('property not found')
                return False

            floor = None
            floor_patterns = [r'\d{1,2} ?tr', r'v??n ?\d{1,2}']
            # get full address address
            full_address = _property.get('street_address')
            # remove everything after comma
            address_wo_floor = full_address.split(',')[0]

            try:
                # check for floor in this stripped address
                # remove from address: <number> tr, v??n <number>
                floor_patterns = [r'\d{1,2} ?tr', r'v??n ?\d{1,2}']
                for re_pattern in floor_patterns:
                    matches = re.findall(re_pattern, address_wo_floor)
                    if len(matches) > 0:
                        try:
                            floor = int(re.findall(r'\d{1,2}', matches[0])[0])
                            address_wo_floor = re.sub(re_pattern, '', address_wo_floor).strip()
                            break
                        except Exception:
                            pass
            except Exception:
                pass

            # if floor already not found get it from the entire address
            if not floor:
                for re_pattern in floor_patterns:
                    matches = re.findall(re_pattern, full_address)
                    if len(matches) > 0:
                        try:
                            floor = int(re.findall(r'\d{1,2}', matches[0])[0])
                            break
                        except Exception:
                            pass

            property_id = str(_property.get('id'))

            self.results[property_id] = {
                'id': property_id,
                'url': result['url'],
                'city': _property.get('location'),
                'street_address': address_wo_floor,
                'floor': floor,
                'area': _property.get('living_area'),
                'house_type': _property.get('housing_form') or '',
                'extra_area': _property.get('supplemental_area'),
                'publication_date': _property.get('publication_date'),
                'complete': False,
                'sold_date': '',
                'matches': None,
                'try_count': 0
            }
            return True
        except Exception as e:
            logger.error(f'could not get data for [{result["url"]}]. errorL: {e}')
            return False

    def save_results(self):
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(config.CACHE_DIR, f'{self.location_id}.json')

        # other scripts might try to access this file at the same time.
        # so try to save it 3 times if failed to save
        for _ in range(3):
            try:
                with open(cache_file, 'w', encoding='utf-8-sig') as f:
                    json.dump(self.results, f)
                logger.info(f'cache saved as: {cache_file}')
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
        logger.info('getting sold properties on hemnet')
        for page_num in range(1, 51):
            if page_num % 10 == 0:
                logger.debug(f'{self.location_name} sold properties: page {page_num}')
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

    def save_xlsx(self):
        logger.info('saving data in excel file...')
        headers = ['Id', 'Tot Hits', 'Tot Apartments', 'Address', 'City', 'Bostadstyp', 'Area', 'Extra Area',
                   'Floor', 'Name', 'K??n', 'Personnr', '??lder'] + [
                      'Phone 1', 'Phone 2', 'Phone 3', 'Phone 4', 'Phone 5', 'Phone 6',
                  ] + ['Apartment', 'Area Match Type', 'Publish Date', 'Sold']

        data = []
        for match_id, entry in self.results.items():
            if not entry['complete'] or not entry['matches']:
                continue

            try:
                address = entry.get('street_address') or ''
                city = entry.get('city') or ''
                house_type = entry.get('house_type') or ''
                area = entry.get('area') or ''
                extra_area = entry.get('extra_area') or ''
                floor = entry.get('floor') or ''
                total_matches = len(entry['matches'])
                apartments = []
                sold = entry.get('sold')
                row_template = [match_id, total_matches, 1, address, city, house_type, area, extra_area, floor]

                new_rows = []
                for match in entry['matches']:
                    new_row = row_template.copy()
                    apartment = match.get('apartment') or ''
                    if apartment and apartment in apartments:
                        pass
                    else:
                        apartments.append(apartment)
                    # print('pn:', match.get('person_number') or '')
                    new_row += [match['name'], match.get('gender') or '', match['person_number'],
                                match.get('age') or '',
                                ] + self.get_phone_columns(match['numbers']) + [
                                   f'lgh {apartment}' if apartment else '',
                                   'Full' if match[
                                       'full_match'] else 'Partial',
                                   entry.get('publication_date'),
                                   sold
                               ]
                    new_rows.append(new_row)

                    # check if apartment is empty then number of apartments would be 1
                    for row in new_rows:
                        if row[len(row_template) + 10].strip() == '':
                            row[2] = 1
                        else:
                            row[2] = len(apartments)

                if len(new_rows) <= config.max_results:
                    data.extend(new_rows)
            except Exception as e:
                # logger.error(e)
                pass

        # create the excel workbook
        wb = openpyxl.Workbook()
        sheet = wb.active
        sheet.append(headers)
        for row in data:
            sheet.append(row)

        # freeze the header
        sheet.freeze_panes = 'A2'

        # add filters to all columns
        sheet.auto_filter.ref = sheet.dimensions

        # save the workbook in this location
        filename = os.path.join(config.DOC_DIR, f'{self.location_name}.xlsx')

        # create the doc dir if not present
        os.makedirs(config.DOC_DIR, exist_ok=True)

        # try to save the file at most 3 times in case some error occurs
        for _ in range(3):
            try:
                wb.save(filename)
                logger.info(f'data saved as "{filename}"')
                break
            except Exception as e:
                time.sleep(random.randint(2, 5))
                logger.error(f'could not save "{filename}". retrying...')

    @staticmethod
    def get_phone_columns(phone_numbers):
        if len(phone_numbers) > 6:
            phone_numbers = phone_numbers[:6]
        elif len(phone_numbers) < 6:
            phone_numbers += [''] * (6 - len(phone_numbers))
        return phone_numbers


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
                logger.info(f'faktakontroll access token updated. valid for: {data["validFor"]}s')
                return self.access_token
            else:
                logger.error('could not get access token for faktakontroll')
                return None
        except Exception as e:
            logger.error(f'could not get access token for faktakontroll. error: {e}')
            return None

    def search(self, search_string, try_count=0):
        config.sleep_between_searches()

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
                    logger.warning('could not get result from faktakontroll. retrying...')
                    return self.search(search_string, 1)
                else:
                    logger.error('could not get result from faktakontroll')
                    return None

            data = response.json()
            results = data['hits']
            return [result['individual'] for result in results if result.get('individual')]

        except Exception as e:
            if try_count == 0:
                logger.warning(f'error while searching address on faktakontroll. error: {e}. retrying...')
                return self.search(search_string, 1)
            else:
                logger.error(f'error while searching address on faktakontroll. error: {e}')
                return None

    def get_more_details(self, result_id):
        config.sleep_between_each_person()

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
        matched_results = []
        for result in faktakontroll_results:
            try:
                is_match = True

                # get apartment and floor number
                street_address = result['fbfStreetAddress']

                if 'lgh' in street_address:
                    staddr = street_address[street_address.index('lgh'):]
                    try:
                        apartment = re.findall(r'\d{4}', staddr)[0]
                        floor = (int(apartment[0]) - 1) * 10 + int(apartment[1])
                    except:
                        apartment = None
                        floor = None
                else:
                    floor = None
                    apartment = None

                # if floor not found then use alternate method
                # find floor on faktakontroll "\d{1,2} ?tr" or "v??n ?\d{1,2}"
                floor_patterns = [r'\d{1,2} ?tr', r'v??n ?\d{1,2}']
                for re_pattern in floor_patterns:
                    matches = re.findall(re_pattern, street_address)
                    if len(matches) > 0:
                        try:
                            floor = int(re.findall(re_pattern, matches[0])[0])
                            break
                        except Exception:
                            pass

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

                # if house type is villa or radhus then don't match anything. just add the results
                if hemnet_result.get('house_type') not in ['Radhus', 'Villa']:
                    ########### compare the areas ###############
                    # convert the areas to float
                    try:
                        hemnet_area = float(hemnet_result.get('area'))
                    except:
                        hemnet_area = None
                    try:
                        faktakontroll_area = float(area)
                    except:
                        faktakontroll_area = None

                    if hemnet_area:
                        if not faktakontroll_area:
                            is_match = False
                        else:
                            if hemnet_area == faktakontroll_area:
                                pass
                            elif faktakontroll_area - 1 < hemnet_area < faktakontroll_area + 1:
                                potential_match['full_match'] = False
                            else:
                                is_match = False

                    # check floor if floor found on hemnet
                    try:
                        hemnet_floor = int(hemnet_result['floor'])
                    except:
                        hemnet_floor = None

                    if hemnet_floor is not None:
                        # if no floor found in faktakontroll then its not a match
                        if floor is None:
                            is_match = False
                        elif floor < hemnet_floor - 1:
                            is_match = False
                        elif floor > hemnet_floor + 1:
                            is_match = False

                if is_match:
                    extra_info = self.get_more_details(result['id'])
                    potential_match.update(extra_info)
                    potential_match.update({
                        'area': area,
                        'name': name,
                        'floor': floor,
                        'apartment': apartment,
                        'street_address': street_address
                    })
                    matched_results.append(potential_match)
            except Exception as e:
                logger.error(f'error while trying to find a match. error: {e}')
        return matched_results
