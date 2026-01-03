import asyncio
import time
from collections import deque
import threading
import queue

import matplotlib.pyplot as plt
import matplotlib.animation as animation
from bleak import BleakClient

from brainlink_parser_linux import BrainLinkParser
from dotenv import load_dotenv
import os

# =======================
# Env
# =======================

load_dotenv()
ADDRESS = os.getenv("ADR", "CC:36:16:00:00:00")
RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# =======================
# Global stop flag
# =======================

stop_event = threading.Event()

# =======================
# Thread-safe queue
# =======================

eeg_queue = queue.Queue()

# =======================
# EEG callback
# =======================

def onEEG(d):
    eeg_queue.put((
        time.time(),
        d.attention,
        d.meditation
    ))

parser = BrainLinkParser(eeg_callback=onEEG)

def handle(_, data: bytearray):
    parser.parse(bytes(data))

# =======================
# BLE loop
# =======================

async def ble_loop():
    client = BleakClient(ADDRESS)
    try:
        await client.connect()
        await client.start_notify(RX_UUID, handle)

        while not stop_event.is_set():
            await asyncio.sleep(0.5)

    finally:
        if client.is_connected:
            try:
                await client.stop_notify(RX_UUID)
            except Exception:
                pass
            await client.disconnect()
        print("BLE disconnected cleanly")

def start_ble():
    asyncio.run(ble_loop())

# =======================
# Plot
# =======================

WINDOW_SEC = 60

times = deque(maxlen=WINDOW_SEC)
att = deque(maxlen=WINDOW_SEC)
med = deque(maxlen=WINDOW_SEC)

fig, ax = plt.subplots()
line_att, = ax.plot([], [], label="ATT", color="red")
line_med, = ax.plot([], [], label="MED", color="blue")

ax.set_ylim(0, 100)
ax.set_title("BrainLink ATT / MED (real-time)")
ax.set_xlabel("seconds")
ax.set_ylabel("value")
ax.legend()
ax.grid(True)

start_time = time.time()

def update(_):
    while not eeg_queue.empty():
        t, a, m = eeg_queue.get()
        times.append(t - start_time)
        att.append(a)
        med.append(m)

    if times:
        t0 = max(0, times[-1] - WINDOW_SEC)
        ax.set_xlim(t0, t0 + WINDOW_SEC)
        line_att.set_data(times, att)
        line_med.set_data(times, med)

    return line_att, line_med

ani = animation.FuncAnimation(fig, update, interval=200)

# =======================
# Clean shutdown on window close
# =======================

def on_close(event):
    print("Stopping...")
    stop_event.set()

fig.canvas.mpl_connect("close_event", on_close)

# =======================
# Start
# =======================

if __name__ == "__main__":
    ble_thread = threading.Thread(target=start_ble)
    ble_thread.start()

    plt.show()

    # ждём завершения BLE
    ble_thread.join()
    print("Exited cleanly")
