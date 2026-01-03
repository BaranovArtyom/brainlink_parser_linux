import asyncio
from bleak import BleakClient
from brainlink_parser_linux import BrainLinkParser
import os

ADDRESS = os.getenv("ADR", "CC:36:16:00:00:00")
RX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


# =======================
# Callbacks
# =======================

def onEEG(d):
    print(
        f"EEG | "
        f"ATT {d.attention:3d} | "
        f"MED {d.meditation:3d} | "
        f"DELTA {d.delta:8d} | "
        f"THETA {d.theta:8d}"
    )


def onEXT(e):
    # EXT приходит редко (rate-limit в парсере)
    print(
        "EXT | "
        f"BAT {e.battery} | "
        f"TEMP {e.temperature}°C | "
        f"HEART {e.heart} bpm | "
        f"GYRO {e.gyro}"
    )


# =======================
# Parser
# =======================

parser = BrainLinkParser(
    eeg_callback=onEEG,
    eeg_extend_callback=onEXT,
    debug=False,
)


# =======================
# BLE notify handler
# =======================

def handle(_: int, data: bytearray):
    # Nordic UART RX -> ThinkGear stream
    parser.parse(bytes(data))


# =======================
# Main loop
# =======================

async def main():
    async with BleakClient(ADDRESS) as client:
        if not client.is_connected:
            raise RuntimeError("BLE connection failed")

        print("connected:", client.is_connected)

        await client.start_notify(RX_UUID, handle)

        try:
            # Работает сколько нужно
            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            print("\nStopping...")

        finally:
            await client.stop_notify(RX_UUID)
            print("Disconnected")


# =======================
# Entry point
# =======================

if __name__ == "__main__":
    asyncio.run(main())
