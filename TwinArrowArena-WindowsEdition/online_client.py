"""Small threaded WebSocket client used by the Pygame online mode."""

import json
import queue
import threading

from websockets.sync.client import connect


class OnlineClient:
    def __init__(self, url):
        self.url = url
        self.incoming = queue.Queue()
        self.outgoing = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def send(self, message):
        if not self.stop_event.is_set():
            self.outgoing.put(message)

    def close(self):
        self.stop_event.set()

    def _run(self):
        try:
            with connect(self.url, open_timeout=15, ping_interval=20, close_timeout=2) as socket:
                self.incoming.put({"type": "connected"})
                while not self.stop_event.is_set():
                    try:
                        while True:
                            outgoing = self.outgoing.get_nowait()
                            socket.send(json.dumps(outgoing, separators=(",", ":")))
                    except queue.Empty:
                        pass
                    try:
                        message = socket.recv(timeout=0.05)
                        self.incoming.put(json.loads(message))
                    except TimeoutError:
                        continue
        except Exception as error:
            if not self.stop_event.is_set():
                self.incoming.put({"type": "error", "message": str(error)})
