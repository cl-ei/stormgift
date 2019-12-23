import os
import configparser

config_file = "/etc/madliar.settings.ini"
if not os.path.exists(config_file):
    config_file = "./madliar.settings.ini"
    print("Warning: LOCAL CONFIG FILE!")

config = configparser.ConfigParser()
config.read(config_file)

CDN_URL = config["default"]["CDN_URL"]
PROJECT_ROOT = config["stormgift"]["PROJECT_ROOT"]
LOG_PATH = config["stormgift"]["LOG_PATH"]


REDIS_CONFIG = {
    "host": config["redis"]["host"],
    "port": int(config["redis"]["port"]),
    "password": config["redis"]["password"],
    "db": int(config["redis"]["stormgift_db"]),
}

REDIS_CONFIG_FOR_GO = {
    "host": config["redis"]["host"],
    "port": int(config["redis"]["port"]),
    "password": config["redis"]["password"],
    "db": int(config["redis"]["go_storm_db"]),
}


MYSQL_CONFIG = {
    "user": config["mysql"]["user"],
    "host": config["mysql"]["host"],
    "port": int(config["mysql"]["port"]),
    "password": config["mysql"]["password"],
    "database": config["mysql"]["stormgift_database"],
}


CQBOT = {
    "api_root": config["cqbot"]["api_root"],
    "access_token": config["cqbot"]["access_token"],
    "secret": config["cqbot"]["secret"],
}

CQBOT_ZY = {
    "api_root": config["cqbot_zy"]["api_root"],
    "access_token": config["cqbot_zy"]["access_token"],
    "secret": config["cqbot_zy"]["secret"],
}

mail_auth_pass = config["mail"]["mail_auth_pass"]
cloud_function_url = config["cloud_function"]["url"]
cloud_get_uid = config["cloud_function"]["get_uid"]
cloud_acceptors = [v for _, v in config["cloud_acceptor"].items()]
cloud_login = config["cloud_function"]["login"]

local_keys = sorted([_ for _ in dir() if not _.startswith("_") and _ not in ("config", "configparser")])
local_vars = locals()
display_str = "\n".join([f"{k}: {local_vars[k]}" for k in local_keys])
print(f"{'-'*80}\nConfigurations:\n\n{display_str}\n{'-'*80}\n")
