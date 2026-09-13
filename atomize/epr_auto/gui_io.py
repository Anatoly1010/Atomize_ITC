"""Line protocol for GUI prompts and graceful interruption over standard streams."""
import _thread
import json
import os
import queue
import signal
import sys
import threading

PREFIX = 'EPR_AUTO_GUI '


class GuiIO:
    def __init__(self):
        self.input_fd = sys.stdin.fileno()
        self.replies = queue.Queue()
        self.closed = threading.Event()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        """Avoid holding a buffered-stdin lock across acquisition-worker fork."""
        buffer = b''
        while not self.closed.is_set():
            try:
                chunk = os.read(self.input_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                reply = line.decode('utf-8', errors='replace').strip().lower()
                if self.closed.is_set():
                    return
                if reply == 'stop':
                    self._interrupt()
                else:
                    self.replies.put(reply)
        self._interrupt()

    def _interrupt(self):
        if self.closed.is_set():
            return
        if os.name == 'posix':
            os.kill(os.getpid(), signal.SIGINT)
        else:
            _thread.interrupt_main()

    def ask(self, prompt, answers, kind):
        print(PREFIX + json.dumps({'kind': kind, 'prompt': prompt}), flush=True)
        while True:
            try:
                reply = self.replies.get(timeout=0.2)
            except queue.Empty:
                continue
            if reply in answers:
                return answers[reply]

    def close(self):
        self.closed.set()
