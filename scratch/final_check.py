import yfinance as yf
import time

def handle(msg):
    print(f"Yahoo WS: {msg['id']} = ${msg['price']}")

ws = yf.WebSocket(verbose=False)
ws.subscribe(["GOOGL", "QQQM"])

import threading
t = threading.Thread(target=ws.listen, args=(handle,), daemon=True)
t.start()

print("Fetching latest from Yahoo WS...")
time.sleep(10)
ws.close()
