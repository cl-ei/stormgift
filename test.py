from config.log4 import acceptor_logger
import socket
from config import config
PRIZE_SOURCE_PUSH_ADDR = tuple(config["PRIZE_SOURCE_PUSH_ADDR"])
print(PRIZE_SOURCE_PUSH_ADDR)

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.sendto("123".encode("utf-8"), ("localhost", 11111))
s.close()
