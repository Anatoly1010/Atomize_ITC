#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from PyQt6.QtCore import QThread, pyqtSignal

class StatusPoller(QThread):
    status_received = pyqtSignal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.target_conn = ''

    def update_command(self, new_cmd):
        self.target_conn = new_cmd

    def run(self):
        while True:
            if self.target_conn.poll() == True:
                self.status_received.emit('')
                break
            
            time.sleep(1) 

