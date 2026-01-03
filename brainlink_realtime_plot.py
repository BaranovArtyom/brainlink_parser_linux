import asyncio
import signal
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
# Thread-safe queue
# =======================

eeg_queue = queue.Queue()

# =======================
# EEG callback (BLE thread)
# =======================

def onEEG(d):
    # кладём только нужное
    eeg_queue.put((
        time.time(),
        d.attention,
        d.meditation
    ))

parser = BrainLinkParser(
    eeg_callback=onEEG
)

def handle(_, data: bytearray):
    parser.parse(bytes(data))

# =======================
# BLE loop (background)
# =======================

async def ble_loop():
    async with BleakClient(ADDRESS) as client:
        await client.start_notify(RX_UUID, handle)
        while True:
            await asyncio.sleep(1)

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
line_att, = ax.plot([], [], label="ATT", color="blue")
line_med, = ax.plot([], [], label="MED", color="red")

ax.set_ylim(0, 100)
ax.set_xlim(0, WINDOW_SEC)
ax.set_title("BrainLink ATT / MED (real-time)")
ax.set_xlabel("seconds")
ax.set_ylabel("value")
ax.legend()
ax.grid(True)

start_time = time.time()

def update(frame):
    # забираем все новые данные
    while not eeg_queue.empty():
        t, a, m = eeg_queue.get()
        times.append(t - start_time)
        att.append(a)
        med.append(m)

    if not times:
        return line_att, line_med

    # сдвигаем окно
    t0 = max(0, times[-1] - WINDOW_SEC)
    ax.set_xlim(t0, t0 + WINDOW_SEC)

    line_att.set_data(times, att)
    line_med.set_data(times, med)

    return line_att, line_med

ani = animation.FuncAnimation(
    fig,
    update,
    interval=200,   # как в Android (~5 fps)
    blit=False
)

# =======================
# Start
# =======================

if __name__ == "__main__":
    # BLE в отдельном потоке
    threading.Thread(target=start_ble, daemon=True).start()

    plt.show()
