import socket
from queue import Queue
import selectors
import threading
import time
from argparse import ArgumentParser


BUFSIZE = 1024


class TichuError(Exception):
    pass


class Client:
    def __init__(self, ip="127.0.0.1", port=1001):
        self.remote_addr = (ip, port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._hand = [] # the player's cards
        self._stage = [] # cards that the player is about to play
        self.push_msgs = Queue()
        self.response_msgs = Queue()

    def connect(self, username):
        self.username = username
        self.socket.connect(self.remote_addr)
        listener = threading.Thread(target=self._listen)
        listener.start()
        # it is important to use _send_and_recv because recv blocks the thread until
        # it gets the message, this way it is guaranteed that the connection is
        # established before going on
        status, message = self._send_and_recv(self.username)
        if status == "err":
            raise TichuError(message)

    def _listen(self):
        sel = selectors.DefaultSelector()
        sel.register(self.socket, selectors.EVENT_READ, data=b"")
        while True:
            # sel.select blocks so we don't have a busy loop
            events = sel.select(timeout=None)
            for key, mask in events:
                sock = key.fileobj
                data = key.data
                # check if the socket is ready to be read
                if mask & selectors.EVENT_READ:
                    recv_data = sock.recv(BUFSIZE)
                    # TODO: check if recv_data is empty
                    data += recv_data
                    # extract all messages (seperated by newline)
                    while b"\n" in data:
                        index = data.find(b"\n")
                        # get the message until the line break and delete it from data
                        # messages from the server are formatted like "status:message\n" so we split by ":"
                        status, msg = data[:index].decode("UTF-8").split(":", 1)
                        data = data[(index + 1):]
                        # check what kind of message we got and put it in the appropriate queue
                        if status == "push":
                            self.push_msgs.put(msg)
                        else:
                            self.response_msgs.put((status, msg))

    def _send(self, message):
        self.socket.send(bytes(message + "\n", "UTF-8"))

    def _send_and_recv(self, message):
        self._send(message)
        return self.response_msgs.get() # get response from the response-queue (blocking)

    def deal(self):
        """tell the server to mix up the deck and deal new cards
        raises TichuError if it's not the player's turn or if the round is still ongoing
        """
        status, message = self._send_and_recv("deal")
        if status == "err":
            raise TichuError(message)

    def request_cards(self):
        """after a deal, request the new cards from the server
        """
        status, message = self._send_and_recv("takecards")
        if status == "ok":
            # the message contains the cards seperated by comma (last one is empty)
            self._hand = message.lower().split(",")[:-1]
        elif status == "err":
            raise TichuError(message)

    def stage(self, i, j):
        """move card i from hand to j in stage (locally and remotely)
        """
        status, message = self._send_and_recv("stage {} {}".format(i, j))
        if status == "ok":
            self._stage.insert(j, self._hand.pop(i))
        elif status == "err":
            raise TichuError(message)

    def unstage(self, i, j):
        """reverse action to stage
        """
        status, message = self._send_and_recv("unstage {} {}".format(i, j))
        if status == "ok":
            self._hand.insert(j, self._stage.pop(i))
        elif status == "err":
            raise TichuError(message)

    def play(self):
        """submit the current stage to the table
        """
        status, message = self._send_and_recv("play")
        if status == "ok":
            self._stage = []
        else:
            raise TichuError(message)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--user")
    args = parser.parse_args()

    client = Client()
    client.connect(args.user)
    client.deal()
    client.request_cards()
    print(client._hand)
    client.stage(0, 0)
    client.play()
