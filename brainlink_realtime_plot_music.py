import asyncio
import time
import threading
import queue
import signal
import subprocess
import os
from collections import deque

import matplotlib.pyplot as plt
import matplotlib.animation as animation
from bleak import BleakClient
from dotenv import load_dotenv

from brainlink_parser_linux import BrainLinkParser

# =======================
# Env
# =======================

load_dotenv()
ADDRESS = os.getenv("ADR", "CC:36:16:00:00:00")
RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# =======================
# Control events
# =======================

stop_event = threading.Event()
eeg_queue = queue.Queue()

# =======================
# Music control (biofeedback)
# =======================

MED_ON = 70
MED_OFF = 60

_music_proc = None
_music_lock = threading.Lock()

def start_music():
    global _music_proc
    if _music_proc is None or _music_proc.poll() is not None:
        _music_proc = subprocess.Popen(
            [
                "mpg123",
                "-a", "hw:2,0",
                os.path.expanduser("~/Music/Luminote_Meditation_Music1.mp3")
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("🎵 MUSIC START")

def stop_music():
    global _music_proc
    if _music_proc and _music_proc.poll() is None:
        _music_proc.terminate()
        _music_proc = None
        print("🛑 MUSIC STOP")

# =======================
# EEG callback
# =======================

def onEEG(d):
    eeg_queue.put((time.time(), d.attention, d.meditation))

    with _music_lock:
        if d.meditation >= MED_ON:
            start_music()
        elif d.meditation <= MED_OFF:
            stop_music()

parser = BrainLinkParser(eeg_callback=onEEG)

def handle(_, data: bytearray):
    parser.parse(bytes(data))

# =======================
# BLE loop (async, stoppable)
# =======================

async def ble_loop():
    async with BleakClient(ADDRESS) as client:
        print("BLE connected:", client.is_connected)
        await client.start_notify(RX_UUID, handle)

        while not stop_event.is_set():
            await asyncio.sleep(0.2)

        print("Stopping notify…")
        await client.stop_notify(RX_UUID)

    print("BLE disconnected cleanly")

def ble_thread():
    asyncio.run(ble_loop())

# =======================
# Plot
# =======================

WINDOW_SEC = 60

times = deque(maxlen=WINDOW_SEC * 10)
att = deque(maxlen=WINDOW_SEC * 10)
med = deque(maxlen=WINDOW_SEC * 10)

fig, ax = plt.subplots()
line_att, = ax.plot([], [], label="ATT", color="red")
line_med, = ax.plot([], [], label="MED", color="blue")

ax.set_ylim(0, 100)
ax.set_title("BrainLink ATT / MED (real-time)")
ax.set_xlabel("time (s)")
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

    if not times:
        return line_att, line_med

    t0 = max(0, times[-1] - WINDOW_SEC)
    ax.set_xlim(t0, t0 + WINDOW_SEC)

    line_att.set_data(times, att)
    line_med.set_data(times, med)

    return line_att, line_med

ani = animation.FuncAnimation(
    fig,
    update,
    interval=200,
    cache_frame_data=False
)

# =======================
# Clean shutdown
# =======================

def on_close(event):
    print("Window closed → stopping everything")
    stop_event.set()
    stop_music()

fig.canvas.mpl_connect("close_event", on_close)

# =======================
# Start
# =======================

if __name__ == "__main__":
    threading.Thread(target=ble_thread, daemon=False).start()
    plt.show()

    # гарантируем финальный стоп
    stop_event.set()
    stop_music()
    print("Exit complete")
