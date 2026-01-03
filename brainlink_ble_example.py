import asyncio
from bleak import BleakClient
from brainlink_parser_linux import BrainLinkParser
import signal
import os
from dotenv import load_dotenv

load_dotenv()

ADDRESS = os.getenv("ADR", "CC:36:16:00:00:00")
RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

stop_event = asyncio.Event()

def onEEG(d):
    print(
        f"ATT {d.attention:3d} | MED {d.meditation:3d} | "
        f"DELTA {d.delta} | THETA {d.theta}"
    )

def onEXT(e):
    print("EXT:", {
        "battery": e.battery,
        "temp": e.temperature,
        "heart": e.heart,
        "gyro": e.gyro,
        "unknown": list(e.unknown.keys()),
    })

parser = BrainLinkParser(
    eeg_callback=onEEG,
    eeg_extend_callback=onEXT,
)

def handle(_, data: bytearray):
    parser.parse(bytes(data))

async def main():
    loop = asyncio.get_running_loop()

    # аккуратно ловим Ctrl+C
    loop.add_signal_handler(signal.SIGINT, stop_event.set)
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)

    async with BleakClient(ADDRESS) as client:
        print("connected:", client.is_connected)
        await client.start_notify(RX_UUID, handle)

        # ждём сигнала остановки
        await stop_event.wait()

        # ВАЖНО: stop_notify до выхода из async with
        await client.stop_notify(RX_UUID)

    # <- ЗДЕСЬ __aexit__ гарантированно отработал
    print("Disconnected cleanly")

if __name__ == "__main__":
    asyncio.run(main())
