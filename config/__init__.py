import os
import configparser

config_file = "/etc/madliar.settings.ini"
if not os.path.exists(config_file):
    config_file = "./madliar.settings.ini"
    print("Warning: LOCAL CONFIG FILE!")

config = configparser.ConfigParser()
config.read(config_file)


try:
    CDN_URL = config["default"]["CDN_URL"]
except KeyError:
    CDN_URL = ""

try:
    PROJECT_ROOT = config["stormgift"]["PROJECT_ROOT"]
except KeyError:
    PROJECT_ROOT = "./"

try:
    LOG_PATH = config["stormgift"]["LOG_PATH"]
except KeyError:
    LOG_PATH = "./log"


REDIS_CONFIG = {}
try:
    REDIS_CONFIG["host"] = config["redis"]["host"]
    REDIS_CONFIG["port"] = int(config["redis"]["port"])
    REDIS_CONFIG["password"] = config["redis"]["password"]
    REDIS_CONFIG["db"] = int(config["redis"]["stormgift_db"])
except KeyError:
    REDIS_CONFIG["host"] = "47.104.176.84"
    REDIS_CONFIG["port"] = 19941
    REDIS_CONFIG["password"] = ""
    REDIS_CONFIG["db"] = 2

REDIS_CONFIG_X_NODE = {}
try:
    REDIS_CONFIG_X_NODE["host"] = config["redis_x_node"]["host"]
    REDIS_CONFIG_X_NODE["port"] = int(config["redis_x_node"]["port"])
    REDIS_CONFIG_X_NODE["password"] = config["redis_x_node"]["password"]
    REDIS_CONFIG_X_NODE["db"] = int(config["redis_x_node"]["stormgift_db"])
except KeyError:
    REDIS_CONFIG_X_NODE["host"] = "47.104.176.84"
    REDIS_CONFIG_X_NODE["port"] = 19941
    REDIS_CONFIG_X_NODE["password"] = ""
    REDIS_CONFIG_X_NODE["db"] = 2


MYSQL_CONFIG = {}
try:
    MYSQL_CONFIG["user"] = config["mysql"]["user"]
    MYSQL_CONFIG["host"] = config["mysql"]["host"]
    MYSQL_CONFIG["port"] = int(config["mysql"]["port"])
    MYSQL_CONFIG["password"] = config["mysql"]["password"]
    MYSQL_CONFIG["database"] = config["mysql"]["stormgift_database"]
except KeyError:
    MYSQL_CONFIG["user"] = "root"
    MYSQL_CONFIG["host"] = "49.234.17.23"
    MYSQL_CONFIG["port"] = 44444
    MYSQL_CONFIG["password"] = "calom310300"
    MYSQL_CONFIG["database"] = "bilibili"


CQBOT = {}
try:
    CQBOT["api_root"] = config["cqbot"]["api_root"]
    CQBOT["access_token"] = config["cqbot"]["access_token"]
    CQBOT["secret"] = config["cqbot"]["secret"]
except KeyError:
    CQBOT["api_root"] = "http://localhost:5700/"
    CQBOT["access_token"] = ""
    CQBOT["secret"] = ""


try:
    mail_auth_pass = config["mail"]["mail_auth_pass"]
except KeyError:
    mail_auth_pass = ""


local_keys = sorted([_ for _ in dir() if not _.startswith("_") and _ not in ("config", "configparser")])
local_vars = locals()
display_str = "\n".join([f"{k}: {local_vars[k]}" for k in local_keys])
print(f"{'-'*80}\nConfigurations:\n\n{display_str}\n{'-'*80}\n")
