import sys
import threading
import time
import socket

def wait_for_port(port: int, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.25)
    return False

def open_browser(port):
    if wait_for_port(port, 20):
        print("Opening browser!")
    else:
        print("Timeout")

t = threading.Thread(target=open_browser, args=(8501,), daemon=True)
t.start()

import streamlit.web.bootstrap as bootstrap
import streamlit.config as config

with open("dummy_app.py", "w") as f:
    f.write("import streamlit as st\nst.write('Hello')")

config.set_option("server.headless", True)
config.set_option("browser.gatherUsageStats", False)
config.set_option("server.port", 8501)
config.set_option("server.address", "127.0.0.1")
config.set_option("global.developmentMode", False)

bootstrap.run("dummy_app.py", False, [], {})
