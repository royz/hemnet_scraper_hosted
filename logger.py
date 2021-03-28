import os
import sys
import glob
import logging
import datetime
from os.path import join

BASE_DIR = os.path.dirname(__file__)


def get_logger():
    # make the logs folder
    logs_folder = join(BASE_DIR, 'logs')
    os.makedirs(logs_folder, exist_ok=True)

    # remove logs older than 5 days
    now = datetime.datetime.now()
    existing_logs = glob.glob(join(logs_folder, '*.log'))
    for log in existing_logs:
        date_str = log[-14:-4]
        if (now - datetime.datetime.strptime(date_str, '%Y-%m-%d')).days > 15:
            print('removing log:', log)
            os.remove(log)
        else:
            print('keeping log:', log)

    current_logfile = join(logs_folder, f"{now.strftime('%Y-%m-%d')}.log")

    logging.basicConfig(
        level=logging.DEBUG,
        format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
        handlers=(
            logging.FileHandler(filename=current_logfile),
            logging.StreamHandler(sys.stdout)
        )
    )

    logging.getLogger('urllib3').setLevel(logging.ERROR)
    return logging.getLogger()
