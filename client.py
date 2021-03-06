import socket
from queue import Queue
import selectors
import threading
import time
from argparse import ArgumentParser
import logging
logger = logging.getLogger("client")


BUFSIZE = 1024


class TichuError(Exception):
    pass


class Client:
    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
        self._hand = [] # the player's cards
        self._stage = [] # cards that the player is about to play
        self.turn = False # is it my turn?
        self.push_msgs = Queue()
        self.response_msgs = Queue()

    @property
    def hand(self):
        return self._hand

    @hand.setter
    def hand(self, h):
        # save the original indices
        self._hand = list(enumerate(h))

    @hand.getter
    def hand(self):
        # the original indices are noone's business
        return [c for _, c in self._hand]

    @property
    def stage(self):
        return self._stage

    @stage.getter
    def stage(self):
        # same as above
        return [c for _, c in self._stage]

    def connect(self, username, ip="127.0.0.1", port=1001):
        self.remote_addr = (ip, port)
        self.username = username
        logger.info("connecting to {}".format(self.remote_addr))
        self.socket.connect(self.remote_addr)
        self.connected = True
        listener = threading.Thread(target=self._listen, daemon=True)
        listener.start()
        # it is important to use _send_and_recv because recv blocks the thread until
        # it gets the message, this way it is guaranteed that the connection is
        # established before going on
        logger.debug("waiting for answer ...")
        status, message = self._send_and_recv(self.username)
        if status == "err":
            raise TichuError(message)
        logger.debug("got it, connection established")

    def disconnect(self):
        logger.info("disconnecting ...")
        self.connected = False
        if hasattr(self, "selector"):
            self.selector.unregister(self.socket)
            self.selector.close()
        self.socket.close()
        logger.debug("done")

    def _listen(self):
        sel = selectors.DefaultSelector()
        # save the selector for later
        self.selector = sel
        sel.register(self.socket, selectors.EVENT_READ, data=b"")
        while self.connected:
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
                            # the server must send push messages of the form topic:message
                            topic, msg = msg.split(":", 1)
                            if topic == "newtrick":
                                msg = msg.lower().split(",")[:-1]
                            elif topic == "yourturn":
                                self.turn = True
                                continue
                            elif topic == "clearcards":
                                self.delete_cards()
                            self.push_msgs.put((topic, msg))
                        else:
                            self.response_msgs.put((status, msg))

    def _send(self, message):
        self.socket.send(bytes(message + "\n", "UTF-8"))

    def _send_and_recv(self, message):
        self._send(message)
        return self.response_msgs.get() # get response from the response-queue (blocking)

    def has_push_msgs(self):
        return not self.push_msgs.empty()

    def get_newest_push(self):
        return self.push_msgs.get()

    def request_cards(self):
        """after a deal, request the new cards from the server
        """
        status, message = self._send_and_recv("takecards")
        if status == "ok":
            # the message contains the cards seperated by comma (last one is empty)
            self.hand = message.lower().split(",")[:-1]
        elif status == "err":
            raise TichuError(message)

    def stage_card(self, i, j):
        """move card i from hand to j in stage
        """
        self._stage.insert(j, self._hand.pop(i))

    def unstage_card(self, i, j):
        """reverse action to stage
        """
        self._hand.insert(j, self._stage.pop(i))

    def move_hand(self, i, j):
        """move card i in hand to j
        """
        self._hand.insert(j, self._hand.pop(i))

    def move_stage(self, i, j):
        """move card i in stage to j
        """
        self._stage.insert(j, self._stage.pop(i))

    def delete_cards(self):
        """deletes all cards (after finished round)
        """
        self._stage = []
        self._hand = []

    def play(self):
        """submit the current stage to the table
        """
        indices = [i for i, _ in self._stage]
        status, message = self._send_and_recv("play {}".format(" ".join(map(str, indices))))
        if status == "ok":
            self._stage = []
            self.turn = False
        else:
            raise TichuError(message)

    def pass_play(self):
        status, message = self._send_and_recv("pass")
        if status == "ok":
            self.turn = False
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
