from __future__ import annotations

from typing import Any


def list_audio_devices() -> dict[str, Any]:
    """List available input (microphone) and output (speaker) devices."""
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception as e:
        return {"inputs": [], "outputs": [], "error": str(e)}

    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []

    default_in = sd.default.device[0]
    default_out = sd.default.device[1]

    for idx, d in enumerate(devices):
        hostapi_name = hostapis[d["hostapi"]]["name"] if d["hostapi"] < len(hostapis) else "Unknown"
        dev_info = {
            "index": idx,
            "name": d["name"],
            "hostapi": hostapi_name,
            "max_input_channels": d["max_input_channels"],
            "max_output_channels": d["max_output_channels"],
            "default_samplerate": d["default_samplerate"],
        }
        if d["max_input_channels"] > 0:
            dev_info["is_default"] = (idx == default_in)
            inputs.append(dev_info)
        if d["max_output_channels"] > 0:
            dev_info["is_default"] = (idx == default_out)
            outputs.append(dev_info)

    return {"inputs": inputs, "outputs": outputs}
