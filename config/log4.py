import os
import sys
import logging

from config import LOG_PATH


log_format = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
console = logging.StreamHandler(sys.stdout)
console.setFormatter(log_format)

stormgift_file_handler = logging.FileHandler(os.path.join(LOG_PATH, "stormgift.log"))
stormgift_file_handler.setFormatter(log_format)


console_logger = logging.getLogger("console")
console_logger.setLevel(logging.DEBUG)
console_logger.addHandler(console)

_lt_server_fh = logging.FileHandler(os.path.join(LOG_PATH, "lt_server.log"))
_lt_server_fh.setFormatter(log_format)
lt_server_logger = logging.getLogger("lt_server")
lt_server_logger.setLevel(logging.DEBUG)
lt_server_logger.addHandler(console)
lt_server_logger.addHandler(_lt_server_fh)


acceptor_file_handler = logging.FileHandler(os.path.join(LOG_PATH, "acceptor_stormgift.log"))
acceptor_file_handler.setFormatter(log_format)
acceptor_logger = logging.getLogger("acceptor_stormgift")
acceptor_logger.setLevel(logging.DEBUG)
acceptor_logger.addHandler(console)
acceptor_logger.addHandler(acceptor_file_handler)
acceptor_logger.addHandler(stormgift_file_handler)


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

file_handler = logging.FileHandler(os.path.join(LOG_PATH, "website.log"))
file_handler.setFormatter(log_format)
website_logger = logging.getLogger("website")
website_logger.setLevel(logging.DEBUG)
website_logger.addHandler(console)
website_logger.addHandler(file_handler)

file_handler = logging.FileHandler(os.path.join(LOG_PATH, "lt_db_sync.log"))
file_handler.setFormatter(log_format)
lt_db_sync_logger = logging.getLogger("lt_db_sync")
lt_db_sync_logger.setLevel(logging.DEBUG)
lt_db_sync_logger.addHandler(console)
lt_db_sync_logger.addHandler(file_handler)
lt_db_sync_logger.addHandler(stormgift_file_handler)


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

file_handler = logging.FileHandler(os.path.join(LOG_PATH, "dxj_dd.log"))
file_handler.setFormatter(log_format)
dxj_dd_logger = logging.getLogger("dxj_dd")
dxj_dd_logger.setLevel(logging.DEBUG)
dxj_dd_logger.addHandler(console)
dxj_dd_logger.addHandler(file_handler)


file_handler = logging.FileHandler(os.path.join(LOG_PATH, "bili_api.log"))
file_handler.setFormatter(log_format)
bili_api_logger = logging.getLogger("bili_api")
bili_api_logger.setLevel(logging.DEBUG)
bili_api_logger.addHandler(console)
bili_api_logger.addHandler(file_handler)
bili_api_logger.addHandler(stormgift_file_handler)


silver_box_fh = logging.FileHandler(os.path.join(LOG_PATH, "silver_box.log"))
silver_box_fh.setFormatter(log_format)
silver_box_logger = logging.getLogger("silver_box")
silver_box_logger.setLevel(logging.DEBUG)
silver_box_logger.addHandler(console)
silver_box_logger.addHandler(silver_box_fh)


web_access_fh = logging.FileHandler(os.path.join(LOG_PATH, "web_access.log"))
web_access_fh.setFormatter(log_format)
web_access_logger = logging.getLogger("web_access")
web_access_logger.setLevel(logging.DEBUG)
web_access_logger.addHandler(console)
web_access_logger.addHandler(web_access_fh)

fh = logging.FileHandler(os.path.join(LOG_PATH, "lt_login.log"))
fh.setFormatter(log_format)
lt_login_logger = logging.getLogger("lt_login")
lt_login_logger.setLevel(logging.DEBUG)
lt_login_logger.addHandler(console)
lt_login_logger.addHandler(fh)


def config_logger(file_name):
    file_name = file_name.lower()
    if not file_name.endswith(".log"):
        file_name += ".log"

    fh = logging.FileHandler(os.path.join(LOG_PATH, file_name))
    fh.setFormatter(log_format)
    console_logger.addHandler(fh)
    return console_logger


__all__ = (
    "log_format",
    "console_logger",
    "lt_server_logger",

    "acceptor_logger",
    "crontab_task_logger",
    "cqbot_logger",
    "website_logger",
    "lt_db_sync_logger",
    "dxj_hansy_logger",
    "dxj_xiaoke_logger",
    "dxj_dd_logger",
    "bili_api_logger",
    "silver_box_logger",
    "web_access_logger",
    "config_logger",
    "lt_login_logger",
)
