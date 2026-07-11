# PersonaPlex Local Hosting

## Short Answer for This Device

This machine is an Apple M1 Pro MacBook Pro with 16GB unified memory. That is not a good target for hosting the full official NVIDIA PersonaPlex realtime Moshi server.

Reasons:

- NVIDIA's published model page lists Linux and NVIDIA Ampere/Hopper GPUs as the supported hardware path.
- The official repo runs PersonaPlex through the Moshi server and supports `--cpu-offload` only as a memory workaround, with higher latency.
- PersonaPlex is a realtime full-duplex speech model, so latency matters as much as whether the model fits in memory.
- 16GB unified system memory is not the same as 16GB NVIDIA VRAM.

Use this Mac for the app server and the existing turn-based voice pipeline:

```text
VOICE_AUDIO_PROVIDER=openai
PERSONAPLEX_URL=
```

Host PersonaPlex separately on a Linux NVIDIA GPU machine, then point this app to it:

```text
PERSONAPLEX_URL=wss://<gpu-host>:8998
PERSONAPLEX_API_KEY=<server-api-key>
```

There are community MLX quantized builds that may run experimentally on Apple
Silicon. See [PERSONAPLEX_QUANTIZED_AUDIT.md](PERSONAPLEX_QUANTIZED_AUDIT.md)
before downloading or running them.

## Recommended Hosting Target

Recommended:

- Linux
- NVIDIA GPU
- At least 24GB VRAM for smoother realtime behavior
- CUDA/PyTorch environment
- Hugging Face token with access to `nvidia/personaplex-7b-v1`

Marginal/experimental:

- 12GB to 16GB NVIDIA VRAM with 4-bit quantized community builds or CPU offload
- Expect quality and latency tradeoffs

Not recommended:

- Apple Silicon 16GB unified memory
- CPU-only realtime serving
- Machines without CUDA

## Prerequisites

1. Accept the model license on Hugging Face:

```text
https://huggingface.co/nvidia/personaplex-7b-v1
```

2. Create a Hugging Face token and export it on the GPU host:

```bash
export HF_TOKEN=hf_...
```

3. Install system dependency on Linux:

```bash
sudo apt update
sudo apt install -y libopus-dev
```

## Basic Server Shape

On a suitable Linux NVIDIA GPU machine:

```bash
git clone https://github.com/NVIDIA/personaplex.git
cd personaplex
python3 -m venv .venv
source .venv/bin/activate
pip install moshi/.

SSL_DIR=$(mktemp -d)
python -m moshi.server --ssl "$SSL_DIR" --host 0.0.0.0 --port 8998
```

If GPU memory is insufficient:

```bash
pip install accelerate
SSL_DIR=$(mktemp -d)
python -m moshi.server --ssl "$SSL_DIR" --host 0.0.0.0 --port 8998 --cpu-offload
```

## Connect This App

Set these values in the repository-root `.env`:

```text
PERSONAPLEX_URL=wss://<gpu-host>:8998
PERSONAPLEX_API_KEY=<api-key-if-configured>
PERSONAPLEX_VOICE=NATF2.pt
PERSONAPLEX_TEXT_PROMPT=You are a warm financial voice assistant. Speak naturally and never expose internal implementation details.
```

Then run this app:

```bash
PYTHONPATH=user_interaction/src user_interaction/.venv/bin/python user_interaction/run_server.py
```

The PersonaPlex bridge endpoint is:

```text
ws://127.0.0.1:8088/interaction/voice/personaplex/ws
```

## Important App Architecture Note

PersonaPlex is only the realtime English voice surface. The agentic handoff still needs reliable user transcripts. Current docs for the LiveKit PersonaPlex integration say PersonaPlex does not provide user transcription or tool calling, so this app uses the turn-based voice pipeline for agentic handoff:

```text
ws://127.0.0.1:8088/interaction/voice/ws?user_id=<id>&language=en
```
