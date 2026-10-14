#!/usr/bin/env python3
"""Phase A & B Environment Verification Script for Gemma 4 Vietnamese STT."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

import httpx

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

# Ensure src/ is importable when running scripts/check_env.py directly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from gemma_stt.config_schema import GemmaSTTConfig  # noqa: E402


def check_environment(config_path: str = "config.yaml") -> dict[str, Any]:
    cfg = GemmaSTTConfig.load(config_path)
    report: dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "c_free_gb": round(shutil.disk_usage("C:/").free / (1024**3), 2) if Path("C:/").exists() else None,
        "d_free_gb": round(shutil.disk_usage("D:/").free / (1024**3), 2) if Path("D:/").exists() else None,
        "hf_cache_dir": os.environ.get("HF_HOME", ""),
        "hf_token_present": False,
        "cuda_available": False,
        "torch_version": None,
        "gpu_name": None,
        "vram_total_gb": None,
        "transformers_version": None,
        "has_multimodal_auto_model": False,
        "input_devices_count": 0,
        "default_mic": None,
        "remote_v1_reachable": False,
        "remote_v1_models": [],
        "remote_v1_audio_transcriptions": False,
    }

    # Check HF token existence without reading/printing secret content
    token_path = Path.home() / ".cache" / "huggingface" / "token"
    report["hf_token_present"] = bool(
        token_path.is_file() or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    )

    # Check PyTorch & CUDA
    try:
        import torch

        report["torch_version"] = torch.__version__
        report["cuda_available"] = bool(torch.cuda.is_available())
        if report["cuda_available"]:
            report["gpu_name"] = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            report["vram_total_gb"] = round(vram, 2)
    except ImportError:
        pass

    # Check Transformers
    try:
        import transformers

        report["transformers_version"] = transformers.__version__
        report["has_multimodal_auto_model"] = hasattr(transformers, "AutoModelForMultimodalLM")
    except ImportError:
        pass

    # Check Microphones
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        input_devs = [d for d in devices if int(d.get("max_input_channels", 0)) > 0]
        report["input_devices_count"] = len(input_devs)
        try:
            default_in = sd.query_devices(kind="input")
            report["default_mic"] = default_in.get("name")
        except Exception:
            report["default_mic"] = input_devs[0].get("name") if input_devs else None
    except Exception:
        pass

    # Check Remote /v1 Server (Colab)
    base_url = cfg.remote_v1.base_url.rstrip("/")
    headers = dict(cfg.remote_v1.extra_headers)
    if cfg.remote_v1.api_key and cfg.remote_v1.api_key != "not-needed":
        headers["Authorization"] = f"Bearer {cfg.remote_v1.api_key}"

    try:
        with httpx.Client(headers=headers, timeout=5.0, follow_redirects=True) as client:
            resp = client.get(f"{base_url}/models")
            if resp.status_code == 200:
                report["remote_v1_reachable"] = True
                data = resp.json()
                report["remote_v1_models"] = [
                    m.get("id") for m in data.get("data", []) if isinstance(m, dict)
                ]
            tr_resp = client.get(f"{base_url}/audio/transcriptions")
            report["remote_v1_audio_transcriptions"] = tr_resp.status_code not in (404, 501)
    except Exception:
        pass

    return report


def main() -> int:
    rep = check_environment()
    print("# Báo Cáo Khảo Sát Thiết Bị & Môi Trường (Giai đoạn A & B)\n")
    print("| Thuộc tính | Giá trị khảo sát |")
    print("|---|---|")
    print(f"| Windows version | `{rep['os']}` |")
    print(f"| Python | `{rep['python']}` (`{rep['python_executable']}`) |")
    print(f"| Dung lượng trống ổ C: / D: | C: `{rep['c_free_gb']} GB` / D: `{rep['d_free_gb']} GB` |")
    print(f"| Thư mục cache HF (`HF_HOME`) | `{rep['hf_cache_dir']}` |")
    print(f"| PyTorch & CUDA | `torch={rep['torch_version']}` · `CUDA={rep['cuda_available']}` |")
    print(f"| GPU NVIDIA | `{rep['gpu_name']}` |")
    print(f"| VRAM tổng | `{rep['vram_total_gb']} GB` |")
    print(
        f"| Transformers | `{rep['transformers_version']}` "
        f"(`AutoModelForMultimodalLM={rep['has_multimodal_auto_model']}`) |"
    )
    print(f"| Hugging Face Token | `{'Đã cấu hình' if rep['hf_token_present'] else 'Chưa đăng nhập'}` |")
    print(f"| Micro / thiết bị nhập | `{rep['default_mic']}` ({rep['input_devices_count']} thiết bị input) |")
    print(
        f"| Colab Server (`.../v1`) | Online=`{rep['remote_v1_reachable']}` · "
        f"Models=`{rep['remote_v1_models']}` · AudioEndpoint=`{rep['remote_v1_audio_transcriptions']}` |"
    )

    print("\n## Đánh giá Pass / Fail")
    mic_ok = rep["input_devices_count"] > 0
    local_cuda_ok = bool(rep["cuda_available"] and rep["has_multimodal_auto_model"])
    remote_ok = bool(rep["remote_v1_reachable"])

    print(f"- [{'PASS' if mic_ok else 'FAIL'}] Microphone thu âm hoạt động ({rep['input_devices_count']} thiết bị).")
    print(
        f"- [{'PASS' if rep['cuda_available'] else 'WARN'}] PyTorch CUDA trên môi trường Python hiện tại "
        f"(CUDA={rep['cuda_available']})."
    )
    print(
        f"- [{'PASS' if rep['has_multimodal_auto_model'] else 'WARN'}] Transformers hỗ trợ Gemma 4 Multimodal "
        f"(AutoModelForMultimodalLM={rep['has_multimodal_auto_model']})."
    )
    print(f"- [{'PASS' if remote_ok else 'WARN'}] Kết nối Colab Server `/v1` (Online={remote_ok}).")

    if not mic_ok:
        return 1
    if not (local_cuda_ok or remote_ok or rep["cuda_available"]):
        print(
            "\n[Gợi ý] Nếu chạy trong .venv chưa cài torch CUDA, hãy dùng Python 3.11 đã có torch+cu130 "
            "hoặc cài đặt torch CUDA + transformers>=5.19.0."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
