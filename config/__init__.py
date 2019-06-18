import configparser

print("-"*80)

config = configparser.ConfigParser()
config.read('/etc/madliar.settings.ini')


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

MYSQL_CONFIG = {}
try:
    MYSQL_CONFIG["user"] = config["mysql"]["user"]
    MYSQL_CONFIG["host"] = config["mysql"]["host"]
    MYSQL_CONFIG["port"] = int(config["mysql"]["port"])
    MYSQL_CONFIG["password"] = config["mysql"]["password"]
    MYSQL_CONFIG["database"] = config["mysql"]["stormgift_database"]
except KeyError:
    MYSQL_CONFIG["user"] = "mysql"
    MYSQL_CONFIG["host"] = "localhost"
    MYSQL_CONFIG["port"] = 44444
    MYSQL_CONFIG["password"] = ""
    MYSQL_CONFIG["database"] = "bilibili"


try:
    PRIZE_HANDLER_SERVE_ADDR = (
        config["stormgift"]["PRIZE_SOURCE_PUSH_HOST"],
        int(config["stormgift"]["PRIZE_SOURCE_PUSH_PORT"])
    )

    PRIZE_SOURCE_PUSH_ADDR = (
        config["stormgift"]["PRIZE_HANDLER_SERVE_HOST"],
        int(config["stormgift"]["PRIZE_HANDLER_SERVE_PORT"])
    )
except KeyError:
    PRIZE_HANDLER_SERVE_ADDR = ("localhost", 11111)
    PRIZE_SOURCE_PUSH_ADDR = ("localhost", 11112)


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
    LT_ACCEPTOR_HOST = config["stormgift"]["LT_ACCEPTOR_HOST"]
    LT_ACCEPTOR_PORT = int(config["stormgift"]["LT_ACCEPTOR_PORT"])
    LT_RAFFLE_ID_GETTER_HOST = config["stormgift"]["LT_RAFFLE_ID_GETTER_HOST"]
    LT_RAFFLE_ID_GETTER_PORT = int(config["stormgift"]["LT_RAFFLE_ID_GETTER_PORT"])

except KeyError:
    LT_ACCEPTOR_HOST = "127.0.0.1"
    LT_ACCEPTOR_PORT = 30000
    LT_RAFFLE_ID_GETTER_HOST = "127.0.0.1"
    LT_RAFFLE_ID_GETTER_PORT = 30001

print(
    "\n"
    "CONFIG: \n"
    f"PROJECT_ROOT: {PROJECT_ROOT}\n"
    f"LOG_PATH: {LOG_PATH}\n"
    f"REDIS_CONFIG: {REDIS_CONFIG}\n"
    f"MYSQL_CONFIG: {MYSQL_CONFIG}\n"
    f"CQBOT: {CQBOT}\n"
    "\n"
    f"PRIZE_HANDLER_SERVE_ADDR: {PRIZE_HANDLER_SERVE_ADDR}\n"
    f"PRIZE_SOURCE_PUSH_ADDR: {PRIZE_SOURCE_PUSH_ADDR}\n"
    f"{'-'*80}\n"
)
