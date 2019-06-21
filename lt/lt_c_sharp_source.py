import ssl
import rsa
import sys
import json
import socket


with open("./key.txt", "r") as f:
    pubkey = rsa.PublicKey.load_pkcs1_openssl_pem(f.read().encode())
s = rsa.encrypt("ExHelper".encode("utf-8"), pubkey)
print(str(s))


def client(host, port, cafile=None):
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    hands_shake = json.dumps(
        {
            "cmd": "Auth",
            "data": {
                "rsa": str(s)
            }
        }
    ).encode("utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock = context.wrap_socket(sock, server_hostname=host)
    sock.connect((host, port))

    hands_shake_len = len(hands_shake) + 4
    length = bytearray(4)
    length[3] = hands_shake_len & 0xFF
    length[2] = (hands_shake_len >> 8) & 0xFF
    length[1] = (hands_shake_len >> 16) & 0xFF
    length[0] = (hands_shake_len >> 24) & 0xFF

    r = sock.send(length + hands_shake)
    print(f"send r: {r}")

    while True:
        data = sock.recv(1)
        print(repr(data))


if __name__ == '__main__':
    client("bilipage.expublicsite.com", 23332, None)
    # client("www.baidu.com", 443, None)
