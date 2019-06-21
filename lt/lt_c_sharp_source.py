import ssl
import json
import socket

rsa = """MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCmzmmY8qjMY9/izLKRvGO/kVqWys/S5y39Ly6LsYJNAMrYPoG1YlCWiuRT3Fh/YpJeDo+XsO2Rx+Bussl6XoPPr1RGn1kVFyfM8Q8INCMhnW3NaM6P8IEnBnr+WBb8RTNxuVrnVeSMomPGCKqDavVQ9jCV8ih9y5W3gfrWMYBsqQIDAQAB"""


def client(host, port, cafile=None):
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock = context.wrap_socket(sock, server_hostname=host)
    sock.connect((host, port))

    hands_shake = json.dumps(
        {
            "cmd": "Auth",
            "data": {
                "rsa": rsa
            }
        }
    ).encode("utf-8")
    hands_shake_len = len(hands_shake)
    length = bytearray(4)
    length[0] = hands_shake_len & 0xFF
    length[1] = (hands_shake_len >> 8) & 0xFF
    length[2] = (hands_shake_len >> 16) & 0xFF
    length[3] = (hands_shake_len >> 24) & 0xFF

    r = sock.send(length + hands_shake)
    print(f"send r: {r}")

    while True:
        data = sock.recv(1)
        print(repr(data))


if __name__ == '__main__':
    client("bilipage.expublicsite.com", 23332, None)
    # client("www.baidu.com", 443, None)
