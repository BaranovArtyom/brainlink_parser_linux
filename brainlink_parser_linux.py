from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any, Tuple
import struct
import time
from collections import defaultdict


# =======================
# Public API data objects
# =======================

@dataclass
class BrainLinkData:
    signal: int = 0
    attention: int = 0
    meditation: int = 0

    delta: int = 0
    theta: int = 0
    lowAlpha: int = 0
    highAlpha: int = 0
    lowBeta: int = 0
    highBeta: int = 0
    lowGamma: int = 0
    highGamma: int = 0


@dataclass
class BrainLinkExtendData:
    battery: Optional[int] = None          # %
    temperature: Optional[float] = None    # °C
    heart: Optional[int] = None             # bpm

    gyro: Optional[Tuple[int, int, int]] = None
    rr: Optional[Tuple[int, int, int]] = None
    version: Optional[str] = None

    unknown: Dict[str, Any] = field(default_factory=dict)


# =======================
# BrainLinkParser
# =======================

class BrainLinkParser:
    def __init__(
        self,
        eeg_callback: Optional[Callable[[BrainLinkData], None]] = None,
        eeg_extend_callback: Optional[Callable[[BrainLinkExtendData], None]] = None,
        gyro_callback: Optional[Callable[[int, int, int], None]] = None,
        rr_callback: Optional[Callable[[int, int, int], None]] = None,
        raw_callback: Optional[Callable[[int], None]] = None,
        debug: bool = False,
    ):
        self.eeg_callback = eeg_callback
        self.eeg_extend_callback = eeg_extend_callback
        self.gyro_callback = gyro_callback
        self.rr_callback = rr_callback
        self.raw_callback = raw_callback
        self.debug = debug

        self._buf = bytearray()
        self._eeg = BrainLinkData()
        self._ext = BrainLinkExtendData()

        self._last_eeg_snapshot = None
        self._last_ext_snapshot = None

        # EXT throttling
        self._last_ext_emit_time = 0.0
        self._ext_emit_interval = 3.0  # seconds

        self._unknown_stats = defaultdict(lambda: {"count": 0, "lens": set(), "last": None})

    # =========
    # Public
    # =========

    def parse(self, data: bytes):
        if not data:
            return
        self._buf.extend(data)

        while True:
            payload = self._extract_packet()
            if payload is None:
                break
            self._parse_payload(payload)

    # =========
    # Packet framing (AA AA)
    # =========

    def _extract_packet(self) -> Optional[bytes]:
        b = self._buf

        while len(b) >= 2 and not (b[0] == 0xAA and b[1] == 0xAA):
            del b[0]

        if len(b) < 4:
            return None

        length = b[2]
        total = 3 + length + 1
        if len(b) < total:
            return None

        payload = bytes(b[3:3 + length])
        checksum = b[3 + length]

        if ((sum(payload) & 0xFF) + checksum) & 0xFF != 0xFF:
            del b[0]
            return None

        del b[:total]
        return payload

    # =========
    # Payload parsing
    # =========

    def _parse_payload(self, payload: bytes):
        i = 0
        eeg_updated = False
        ext_updated = False

        while i < len(payload):
            code = payload[i]
            i += 1

            if code < 0x80:
                if i >= len(payload):
                    break
                val = payload[i]
                i += 1
                eeg_updated |= self._handle_short(code, val)
            else:
                if i >= len(payload):
                    break
                size = payload[i]
                i += 1
                block = payload[i:i + size]
                i += size
                eeg_updated |= self._handle_long(code, block)
                ext_updated |= self._handle_extend(code, block)

        self._emit_eeg_if_changed(eeg_updated)
        self._emit_ext_if_changed(ext_updated)

    # =========
    # EEG decoding
    # =========

    def _handle_short(self, code: int, val: int) -> bool:
        if code == 0x02:
            self._eeg.signal = val
            return True
        if code == 0x04:
            self._eeg.attention = val
            return True
        if code == 0x05:
            self._eeg.meditation = val
            return True
        return False

    def _handle_long(self, code: int, data: bytes) -> bool:
        if code == 0x80 and len(data) == 2:
            raw = struct.unpack(">h", data)[0]
            if self.raw_callback:
                self.raw_callback(raw)
            return False

        if code == 0x83 and len(data) == 24:
            vals = [int.from_bytes(data[i:i+3], "big") for i in range(0, 24, 3)]
            (
                self._eeg.delta,
                self._eeg.theta,
                self._eeg.lowAlpha,
                self._eeg.highAlpha,
                self._eeg.lowBeta,
                self._eeg.highBeta,
                self._eeg.lowGamma,
                self._eeg.highGamma,
            ) = vals
            return True

        return False

    # =========
    # Extend decoding (clean)
    # =========

    def _handle_extend(self, code: int, data: bytes) -> bool:
        # EEG codes are NOT extend
        if code in (0x80, 0x83):
            return False

        # gyro: 3 x int16
        if len(data) == 6:
            x, y, z = struct.unpack(">hhh", data)
            self._ext.gyro = (x, y, z)
            if self.gyro_callback:
                self.gyro_callback(x, y, z)
            return True

        # heart rate
        if len(data) == 2:
            v = int.from_bytes(data, "big")
            if 40 <= v <= 200:
                self._ext.heart = v
                return True

        # battery
        if len(data) == 1 and data[0] <= 100:
            self._ext.battery = data[0]
            return True

        # temperature
        if len(data) == 2:
            t = int.from_bytes(data, "big") / 10.0
            if 20.0 <= t <= 45.0:
                self._ext.temperature = t
                return True

        # unknown (kept but not spammed)
        key = f"0x{code:02X}"
        stat = self._unknown_stats[key]
        stat["count"] += 1
        stat["lens"].add(len(data))
        stat["last"] = data.hex()
        self._ext.unknown[key] = dict(stat)

        return False

    # =========
    # Emit logic
    # =========

    def _emit_eeg_if_changed(self, updated: bool):
        if not updated or not self.eeg_callback:
            return
        snap = self._eeg.__dict__.copy()
        if snap != self._last_eeg_snapshot:
            self._last_eeg_snapshot = snap
            self.eeg_callback(self._eeg)

    def _emit_ext_if_changed(self, updated: bool):
        if not updated or not self.eeg_extend_callback:
            return

        now = time.time()
        if now - self._last_ext_emit_time < self._ext_emit_interval:
            return

        snap = {
            "battery": self._ext.battery,
            "temperature": self._ext.temperature,
            "heart": self._ext.heart,
            "gyro": self._ext.gyro,
            "rr": self._ext.rr,
            "version": self._ext.version,
        }

        if snap != self._last_ext_snapshot:
            self._last_ext_snapshot = snap
            self._last_ext_emit_time = now
            self.eeg_extend_callback(self._ext)
