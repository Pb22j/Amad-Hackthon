"""Check whether this machine is a reasonable PersonaPlex host."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess


def main() -> int:
    system = platform.system()
    machine = platform.machine()
    print(f"OS: {system}")
    print(f"Architecture: {machine}")
    print(f"System RAM: {_system_ram_gb():.1f} GB")

    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        print("NVIDIA GPU: not detected")
        print("")
        print("Result: not recommended for local PersonaPlex hosting.")
        print("Use this machine for the app server and host PersonaPlex on a Linux NVIDIA GPU box.")
        return 1

    print("NVIDIA GPU: detected")
    output = subprocess.check_output(
        [
            nvidia_smi,
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).strip()
    print(output)

    best_vram = _best_vram_gb(output)
    if best_vram >= 24:
        print("")
        print("Result: suitable target for PersonaPlex realtime hosting.")
        return 0
    if best_vram >= 12:
        print("")
        print("Result: marginal. Try CPU offload or a quantized build, but expect latency tradeoffs.")
        return 0

    print("")
    print("Result: not recommended. PersonaPlex realtime hosting likely needs more GPU memory.")
    return 1


def _system_ram_gb() -> float:
    if platform.system() == "Darwin":
        raw = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
        return int(raw) / (1024**3)
    if hasattr(os, "sysconf"):
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return pages * page_size / (1024**3)
    return 0.0


def _best_vram_gb(nvidia_smi_output: str) -> float:
    best = 0.0
    for line in nvidia_smi_output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            best = max(best, float(parts[-1]) / 1024)
        except ValueError:
            continue
    return best


if __name__ == "__main__":
    raise SystemExit(main())

