import os
import sys
import logging
import json
import requests
import traceback
import time

sys_argv = sys.argv[1:]
try:
    DEBUG = sys_argv[0] == "server"
    ROOM_COUNT_LIMIT = int(sys_argv[1])
except Exception:
    DEBUG = True
    ROOM_COUNT_LIMIT = 500

LOG_PATH = "./log" if DEBUG else "/home/wwwroot/log"
fh = logging.FileHandler(os.path.join(LOG_PATH, "scanner.log"), encoding="utf-8")
fh.setFormatter(logging.Formatter('%(message)s'))
logger = logging.getLogger("prize")
logger.setLevel(logging.DEBUG)
logger.addHandler(fh)
logging = logger

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'
headers = {'User-Agent': UA}


def get_all_count():
    url = "https://api.live.bilibili.com/room/v1/Area/getLiveRoomCountByAreaID?areaId=0"
    for try_times in range(0, 3):
        try:
            time.sleep(1)
            r = requests.get(url=url, headers=headers)
            if r.status_code != 200:
                raise ValueError("Response status code Error! %s" % r.status_code)
            data = json.loads(r.content.decode("utf-8"))
            if data.get("code") != 0:
                raise ValueError("Response data Error! response: %s" % json.dumps(data))
            total_number = int(data.get("data", {}).get("num", 0))
            if 0 < total_number < 20000:
                return total_number
        except Exception as e:
            logging.error("Error happened in get all count, try times: %s, e: %s" % (try_times, e))
            logging.error(traceback.format_exc())
    return 0


def get_room_id_list(index):
    url = "https://api.live.bilibili.com/room/v1/Area/getListByAreaID?areaId=0&sort=online&pageSize=2000&page=%s" % index

    for try_times in range(0, 3):
        try:
            time.sleep(1)
            r = requests.get(url=url, headers=headers)
            if r.status_code != 200:
                raise ValueError("Response status code Error! %s" % r.status_code)
            data = json.loads(r.content.decode("utf-8"))
            if data.get("code") != 0:
                raise ValueError("Response data Error! response: %s" % json.dumps(data))
            data_list = []
            for d in data.get("data", []):
                data_list.append(int(d["roomid"]))
            return data_list
        except Exception as e:
            logging.error(
                "Error happened in get all count, index: %s, try times: %s, e: %s"
                % (index, try_times, e)
            )
            logging.error(traceback.format_exc())
    sys.exit(2)


def main():
    logging.info("Start scan lived room... Limit: %s" % ROOM_COUNT_LIMIT)
    total = get_all_count()
    pages = int(total/2000) + 1
    room_id_list = []
    for index in range(0, pages):
        room_id_list += get_room_id_list(index)
        room_id_list = list(set(room_id_list))
        if abs(len(room_id_list) - total) < 500:
            with open("./data/rooms.txt", "wb") as f:
                f.write("_".join(map(str, room_id_list[:ROOM_COUNT_LIMIT])).encode("utf-8"))
            logging.info("Room id saved. total: %s, final: %s" % (total, len(room_id_list)))
            return
    sys.exit(3)


if __name__ == "__main__":
    main()
