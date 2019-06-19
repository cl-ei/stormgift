import os
import sys
import logging

from config import LOG_PATH


log_format = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")

console = logging.StreamHandler(sys.stdout)
console.setFormatter(log_format)
stormgift_file_handler = logging.FileHandler(os.path.join(LOG_PATH, "stormgift.log"))
stormgift_file_handler.setFormatter(log_format)


acceptor_file_handler = logging.FileHandler(os.path.join(LOG_PATH, "acceptor_stormgift.log"))
acceptor_file_handler.setFormatter(log_format)
acceptor_logger = logging.getLogger("acceptor_stormgift")
acceptor_logger.setLevel(logging.DEBUG)
acceptor_logger.addHandler(console)
acceptor_logger.addHandler(acceptor_file_handler)
acceptor_logger.addHandler(stormgift_file_handler)


status_file_handler = logging.FileHandler(os.path.join(LOG_PATH, "status_stormgift.log"))
status_file_handler.setFormatter(log_format)
status_logger = logging.getLogger("status_stormgift")
status_logger.setLevel(logging.DEBUG)
status_logger.addHandler(console)
status_logger.addHandler(status_file_handler)
status_logger.addHandler(stormgift_file_handler)


file_handler = logging.FileHandler(os.path.join(LOG_PATH, "crontab_task.log"))
file_handler.setFormatter(log_format)
crontab_task_logger = logging.getLogger("crontab_task")
crontab_task_logger.setLevel(logging.DEBUG)
crontab_task_logger.addHandler(console)
crontab_task_logger.addHandler(file_handler)

file_handler = logging.FileHandler(os.path.join(LOG_PATH, "cqbot.log"))
file_handler.setFormatter(log_format)
cqbot_logger = logging.getLogger("cqbot")
cqbot_logger.setLevel(logging.DEBUG)
cqbot_logger.addHandler(console)
cqbot_logger.addHandler(file_handler)


file_handler = logging.FileHandler(os.path.join(LOG_PATH, "lt_raffle_id_getter.log"))
file_handler.setFormatter(log_format)
lt_raffle_id_getter_logger = logging.getLogger("lt_raffle_id_getter")
lt_raffle_id_getter_logger.setLevel(logging.DEBUG)
lt_raffle_id_getter_logger.addHandler(console)
lt_raffle_id_getter_logger.addHandler(file_handler)
lt_raffle_id_getter_logger.addHandler(stormgift_file_handler)


file_handler = logging.FileHandler(os.path.join(LOG_PATH, "lt_source.log"))
file_handler.setFormatter(log_format)
lt_source_logger = logging.getLogger("lt_source")
lt_source_logger.setLevel(logging.DEBUG)
lt_source_logger.addHandler(console)
lt_source_logger.addHandler(file_handler)
lt_source_logger.addHandler(stormgift_file_handler)


file_handler = logging.FileHandler(os.path.join(LOG_PATH, "dxj_hansy.log"))
file_handler.setFormatter(log_format)
dxj_hansy_logger = logging.getLogger("dxj_hansy")
dxj_hansy_logger.setLevel(logging.DEBUG)
dxj_hansy_logger.addHandler(console)
dxj_hansy_logger.addHandler(file_handler)

file_handler = logging.FileHandler(os.path.join(LOG_PATH, "dxj_xiaoke.log"))
file_handler.setFormatter(log_format)
dxj_xiaoke_logger = logging.getLogger("dxj_xiaoke")
dxj_xiaoke_logger.setLevel(logging.DEBUG)
dxj_xiaoke_logger.addHandler(console)
dxj_xiaoke_logger.addHandler(file_handler)

file_handler = logging.FileHandler(os.path.join(LOG_PATH, "dxj_wanzi.log"))
file_handler.setFormatter(log_format)
dxj_wanzi_logger = logging.getLogger("dxj_wanzi")
dxj_wanzi_logger.setLevel(logging.DEBUG)
dxj_wanzi_logger.addHandler(console)
dxj_wanzi_logger.addHandler(file_handler)


file_handler = logging.FileHandler(os.path.join(LOG_PATH, "bili_api.log"))
file_handler.setFormatter(log_format)
bili_api_logger = logging.getLogger("bili_api")
bili_api_logger.setLevel(logging.DEBUG)
bili_api_logger.addHandler(console)
bili_api_logger.addHandler(file_handler)
bili_api_logger.addHandler(stormgift_file_handler)


__all__ = (
    "acceptor_logger",
    "status_logger",
    "crontab_task_logger",
    "cqbot_logger",
    "lt_source_logger",
    "lt_raffle_id_getter_logger",
    "dxj_hansy_logger",
    "dxj_xiaoke_logger",
    "dxj_wanzi_logger",
    "bili_api_logger",
)
