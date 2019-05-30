import os
import sys
import asyncio
import json
from utils.ws import ReConnectingWsClient
from utils.biliapi import WsApi
import logging


MONITOR_ROOM_ID = 2516117  # int(sys.argv[1])
LOG_NAME = f"recorder-{MONITOR_ROOM_ID}"

if "linux" in sys.platform:
    from config import config
    LOG_PATH = config["LOG_PATH"]
else:
    LOG_PATH = "./log"


log_format = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
console = logging.StreamHandler(sys.stdout)
console.setFormatter(log_format)
# file_handler = logging.FileHandler(os.path.join(LOG_PATH, LOG_NAME + ".log"), encoding="utf-8")
# file_handler.setFormatter(log_format)
logger = logging.getLogger(LOG_NAME)
logger.setLevel(logging.DEBUG)
logger.addHandler(console)
# logger.addHandler(file_handler)
logging = logger


async def main():
    async def on_connect(ws):
        logging.info(f"Live room {MONITOR_ROOM_ID} connected.")
        await ws.send(WsApi.gen_join_room_pkg(MONITOR_ROOM_ID))

    async def on_shut_down():
        logging.error("shutdown!")
        raise RuntimeError("Connection broken!")

    async def on_message(message):
        for m in WsApi.parse_msg(message):
            try:
                logging.info(json.dumps(m, ensure_ascii=False))
            except Exception as e:
                logging.error(f"Error happened when proc_message: {e}", exc_info=True)

    new_client = ReConnectingWsClient(
        uri=WsApi.BILI_WS_URI,
        on_message=on_message,
        on_connect=on_connect,
        on_shut_down=on_shut_down,
        heart_beat_pkg=WsApi.gen_heart_beat_pkg(),
        heart_beat_interval=10
    )

    await new_client.start()
    logging.info("Ws stated.")

    while True:
        await asyncio.sleep(10)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
