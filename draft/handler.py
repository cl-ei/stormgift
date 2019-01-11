import os
import sys
import logging
from threading import Thread
import socket
from websocket_server import WebsocketServer
import traceback


sys_argv = sys.argv[1:]
try:
    DEBUG = sys_argv[0] != "server"
except Exception:
    DEBUG = True

LOG_PATH = "./log" if DEBUG else "/home/wwwroot/log"
fh = logging.FileHandler(os.path.join(LOG_PATH, "handler.log"), encoding="utf-8")
fh.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
logger = logging.getLogger("handler")
logger.setLevel(logging.DEBUG)
logger.addHandler(fh)


def print_to_log(msg, level="info"):
    print(msg)
    fn = logger.error if level == "error" else logger.info
    fn(msg)


class NoticeHandle(object):
    def __init__(self):
        self.server = None

    @staticmethod
    def new_client(client, server):
        print_to_log("New client connected and was given id %d, addr: %s" % (client['id'], client['address']))

    @staticmethod
    def client_left(client, server):
        print_to_log("Client(%d) disconnected." % client['id'])

    def start_serve(self):
        server = WebsocketServer(11112, "0.0.0.0")
        server.set_fn_new_client(NoticeHandle.new_client)
        server.set_fn_client_left(NoticeHandle.client_left)
        self.server = server
        t = Thread(target=server.run_forever)
        t.start()

    def notice_to_all(self, msg):
        try:
            self.server.send_message_to_all(msg)
        except Exception as e:
            print_to_log("Failed to send some message: %s, e: %s\n" % (msg, e))
        else:
            print_to_log("Send message to all: %s\n" % msg)


class PrizeMsgReceiver(object):
    def __init__(self, notice_handler):
        self.notice_handler = notice_handler
        self.sub_thread = None

    def proc_new_sock(self, sock, addr):
        print_to_log("Prize message source added, addr: %s, port: %s" % addr)
        try:
            while True:
                data = sock.recv(10240)
                print_to_log("Message received from %s: [%s]" % (addr, data))
                self.notice_handler.notice_to_all(data)
        except Exception as e:
            print_to_log("Error happened in proc new sock, e: %s" % e, level="error")
            print_to_log(traceback.format_exc(), level="error")
        sock.close()

    def run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('0.0.0.0', 11111))
        s.listen(5)
        print_to_log("PrizeMsgReceiver started...")
        while True:
            sock, addr = s.accept()
            if "127.0.0.1" in addr:
                print_to_log("Accept new notice message source, addr: %s, port: %s" % addr)
                self.sub_thread = Thread(target=self.proc_new_sock, args=(sock, addr))
                self.sub_thread.start()
            else:
                print_to_log("Bad sock! addr: %s" % addr)


def main():
    env = "DEBUG" if DEBUG else "SERVER"
    print_to_log("Start HANDLER Proc, ENV: %s" % env)
    notice_handler = NoticeHandle()
    notice_handler.start_serve()
    receiver = PrizeMsgReceiver(notice_handler)
    receiver.run()


if __name__ == "__main__":
    main()

