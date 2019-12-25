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


file_handler = logging.FileHandler(os.path.join(LOG_PATH, "lt_ws_source.log"))
file_handler.setFormatter(log_format)
lt_ws_source_logger = logging.getLogger("lt_ws_source")
lt_ws_source_logger.setLevel(logging.DEBUG)
lt_ws_source_logger.addHandler(console)
lt_ws_source_logger.addHandler(file_handler)
lt_ws_source_logger.addHandler(stormgift_file_handler)


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


file_handler = logging.FileHandler(os.path.join(LOG_PATH, "dxj_super.log"))
file_handler.setFormatter(log_format)
super_dxj_logger = logging.getLogger("dxj_super")
super_dxj_logger.setLevel(logging.DEBUG)
super_dxj_logger.addHandler(console)
super_dxj_logger.addHandler(file_handler)


file_handler = logging.FileHandler(os.path.join(LOG_PATH, "bili_api.log"))
file_handler.setFormatter(log_format)
bili_api_logger = logging.getLogger("bili_api")
bili_api_logger.setLevel(logging.DEBUG)
bili_api_logger.addHandler(console)
bili_api_logger.addHandler(file_handler)
bili_api_logger.addHandler(stormgift_file_handler)


file_handler = logging.FileHandler(os.path.join(LOG_PATH, "model_operation.log"))
file_handler.setFormatter(log_format)
model_operation_logger = logging.getLogger("model_operation")
model_operation_logger.setLevel(logging.DEBUG)
model_operation_logger.addHandler(console)
model_operation_logger.addHandler(file_handler)
model_operation_logger.addHandler(stormgift_file_handler)

silver_box_fh = logging.FileHandler(os.path.join(LOG_PATH, "silver_box.log"))
silver_box_fh.setFormatter(log_format)
silver_box_logger = logging.getLogger("silver_box")
silver_box_logger.setLevel(logging.DEBUG)
silver_box_logger.addHandler(console)
silver_box_logger.addHandler(silver_box_fh)


anchor_fh = logging.FileHandler(os.path.join(LOG_PATH, "anchor.log"))
anchor_fh.setFormatter(logging.Formatter("%(asctime)s^%(message)s"))
anchor_logger = logging.getLogger("anchor")
anchor_logger.setLevel(logging.DEBUG)
anchor_logger.addHandler(anchor_fh)


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
    "acceptor_logger",
    "crontab_task_logger",
    "cqbot_logger",
    "website_logger",
    "lt_source_logger",
    "lt_ws_source_logger",
    "lt_raffle_id_getter_logger",
    "lt_db_sync_logger",
    "dxj_hansy_logger",
    "dxj_xiaoke_logger",
    "dxj_dd_logger",
    "super_dxj_logger",
    "bili_api_logger",
    "model_operation_logger",
    "silver_box_logger",
    "config_logger",
    "anchor_logger",
)
