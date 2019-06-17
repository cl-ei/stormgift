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


print(
    "\n"
    "CONFIG: \n"
    f"PROJECT_ROOT: {PROJECT_ROOT}\n"
    f"LOG_PATH: {LOG_PATH}\n"
    f"REDIS_CONFIG: {REDIS_CONFIG}\n"
    "\n"
    f"PRIZE_HANDLER_SERVE_ADDR: {PRIZE_HANDLER_SERVE_ADDR}\n"
    f"PRIZE_HANDLER_SERVE_ADDR: {PRIZE_HANDLER_SERVE_ADDR}\n"
    f"{'-'*80}\n"
)
