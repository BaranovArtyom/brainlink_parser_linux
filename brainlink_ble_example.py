import asyncio
from bleak import BleakClient
from brainlink_parser_linux import BrainLinkParser
import signal
import os
from dotenv import load_dotenv

# =======================
# Env
# =======================

load_dotenv()

ADDRESS = os.getenv("ADR", "CC:36:16:00:00:00")
RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

stop_event = asyncio.Event()

# =======================
# Callbacks
# =======================

def onEEG(d):
    """
    Всегда печатаем ПОЛНЫЙ EEG snapshot
    (агрегированное состояние)
    """
    print(
        f"ATT {d.attention:3d} | "
        f"MED {d.meditation:3d} | "
        f"DELTA {d.delta:8d} | "
        f"THETA {d.theta:8d} | "
        f"L-ALPHA {d.lowAlpha:8d} | "
        f"H-ALPHA {d.highAlpha:8d} | "
        f"L-BETA {d.lowBeta:8d} | "
        f"H-BETA {d.highBeta:8d} | "
        f"L-GAMMA {d.lowGamma:8d} | "
        f"H-GAMMA {d.highGamma:8d}"
    )


def onEXT(e):
    print("EXT:", {
        "battery": e.battery,
        "temp": e.temperature,
        "heart": e.heart,
        "gyro": e.gyro,
        "unknown": list(e.unknown.keys()),
    })


# =======================
# Parser
# =======================

parser = BrainLinkParser(
    eeg_callback=onEEG,
    eeg_extend_callback=onEXT,
)

def handle(_, data: bytearray):
    parser.parse(bytes(data))


# =======================
# Main loop
# =======================

async def main():
    loop = asyncio.get_running_loop()

    # корректное завершение по Ctrl+C
    loop.add_signal_handler(signal.SIGINT, stop_event.set)
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)

    async with BleakClient(ADDRESS) as client:
        print("connected:", client.is_connected)

        await client.start_notify(RX_UUID, handle)

        # ждём сигнала остановки
        await stop_event.wait()

        # обязательно останавливаем notify
        await client.stop_notify(RX_UUID)

    print("Disconnected cleanly")


# =======================
# Entry point
# =======================

if __name__ == "__main__":
    asyncio.run(main())
