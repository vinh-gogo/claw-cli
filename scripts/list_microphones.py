#!/usr/bin/env python3
"""List available audio input microphones and verify 16 kHz mono compatibility."""

from __future__ import annotations

import sys

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    try:
        import sounddevice as sd
    except ImportError:
        print("Lỗi: Thư viện sounddevice chưa được cài đặt.")
        return 1

    devices = sd.query_devices()
    default_input_idx = sd.default.device[0]

    print("=== Danh Sách Thiết Bị Thu Âm (Microphones) ===")
    print(f"{'ID':>3} | {'Mặc định':^8} | {'Kênh In':>7} | {'Default SR':>10} | {'16kHz Native':^12} | Tên thiết bị")
    print("-" * 88)

    found = 0
    for idx, dev in enumerate(devices):
        max_in = int(dev.get("max_input_channels", 0))
        if max_in <= 0:
            continue
        found += 1
        is_def = "*" if idx == default_input_idx else ""
        default_sr = int(dev.get("default_samplerate", 0))

        supports_16k = False
        try:
            sd.check_input_settings(device=idx, channels=1, dtype="float32", samplerate=16000)
            supports_16k = True
        except Exception:
            supports_16k = False

        print(
            f"{idx:>3} | {is_def:^8} | {max_in:>7} | {default_sr:>8} Hz | "
            f"{'Có' if supports_16k else 'Resample':^12} | {dev.get('name')}"
        )

    if found == 0:
        print("Không tìm thấy thiết bị microphone nào có max_input_channels > 0!")
        return 1

    print(f"\nTổng cộng: {found} thiết bị thu âm khả dụng.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
