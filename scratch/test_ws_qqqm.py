import yfinance as yf
import time

def handle_message(msg):
    print(f"WS Message: {msg}")

ws = yf.WebSocket(verbose=False)
ws.subscribe(["QQQM"])

import threading
t = threading.Thread(target=ws.listen, args=(handle_message,), daemon=True)
t.start()

print("Listening to WebSocket for QQQM...")
time.sleep(10)
ws.close()
