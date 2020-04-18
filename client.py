import socket
import time


BUFSIZE = 1024


class Client:
    def __init__(self, ip="127.0.0.1", port=1001):
        self.remote_addr = (ip, port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def connect(self, username):
        self.username = username
        self.socket.connect(self.remote_addr)
        self._send(self.username)

    def _send(self, message):
        self.socket.send(bytes(message + "\n", "UTF-8"))

    def _send_and_recv(self, message):
        self._send(message)
        answer = self.socket.recv(BUFSIZE)
        # answers from the server are formatted like "status:message\n"
        status, message = answer.decode("UTF-8").strip().split(":")
        return (status, message)


if __name__ == "__main__":
    client = Client()
    username = input("username: ")
    client.connect(username)
    while True:
        msg = input("command> ")
        print(client._send_and_recv(msg))
