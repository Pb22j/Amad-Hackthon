# PersonaPlex Quantized Model Audit

## Summary

There are community quantized PersonaPlex variants on Hugging Face. Some may fit in this MacBook Pro's 16GB unified memory, but they are not all equally usable or safe.

Current hosting decision for this device:

```text
Do not host PersonaPlex locally on this MacBook Pro.
```

Reason:

- The best candidate is still a community conversion, not an official NVIDIA runtime artifact.
- The 8-bit MLX model is roughly 9GB of weights before runtime overhead, which is tight on a 16GB unified-memory machine.
- The 4-bit MLX model fits better but its own model card says quality degrades significantly for realtime/full-duplex use.
- The safer Homebrew runtime path (`speech` / `speech-server`) did not finish installing during local verification.
- This is a financial app, so "probably runnable" is not enough to satisfy the trust bar.

Best experimental Apple Silicon candidate:

```text
aufklarer/PersonaPlex-7B-MLX-8bit
```

Why:

- Built for Apple Silicon / MLX.
- Uses `.safetensors` files instead of Python pickle-style model weights.
- Model card reports about 9.1GB model component size.
- It is explicitly the recommended variant over the 4-bit MLX version for real-time/full-duplex quality.

Not production-approved:

- It is a community conversion, not an NVIDIA official release.
- It uses a different license label than NVIDIA's original model page.
- It requires the Swift/MLX runtime path, not the NVIDIA Moshi server path.
- We have not verified checksums, conversion scripts, or audio quality locally.

## Candidate Assessment

| Model | Runtime | Local Mac fit | Reliability | Security posture | Recommendation |
| --- | --- | --- | --- | --- | --- |
| `aufklarer/PersonaPlex-7B-MLX-8bit` | MLX / Swift | Possible, tight | Medium | Better: safetensors, no bundled Python package | Best experiment |
| `aufklarer/PersonaPlex-7B-MLX-4bit` | MLX / Swift | Likely fits | Low for real-time quality | Better: safetensors | Avoid except quick experiment |
| `brianmatzelle/personaplex-7b-v1-bnb-4bit` | CUDA / bitsandbytes | Not for this Mac | Medium on CUDA only | Riskier: includes modified `moshi/`, `.pt` weights | Do not use on this Mac |
| `cudabenchmarktest/personaplex-7b-nf4` | Custom | Unknown | Low | Riskier: custom scripts, low adoption | Avoid |
| `cudabenchmarktest/personaplex-7b-turbo2bit` | Custom | Unknown | Low | Riskier: custom scripts, low adoption | Avoid |
| `alvanalrakib/personaplex-7b-q8-GGUF` | GGUF | Unknown | Low/unknown for full-duplex | Medium: GGUF, but unclear runtime | Avoid for now |
| `idle-intelligence/personaplex-7b-v1-q4_k-webgpu` | WebGPU | Unknown | Low adoption | Unknown | Avoid for now |

## Important Compatibility Note

The current app has two voice paths:

1. `PERSONAPLEX_URL` bridge:
   - Expects a running NVIDIA/Moshi-compatible PersonaPlex WebSocket server.
   - Best suited to Linux NVIDIA GPU hosting.

2. Turn-based voice pipeline:
   - Uses STT/TTS provider and our agentic layer.
   - Works on this Mac today.

The MLX quantized models do not automatically provide the same PersonaPlex WebSocket server. To use `aufklarer/PersonaPlex-7B-MLX-8bit`, we need one more adapter layer:

```text
speech-swift / MLX local runner
  -> local HTTP/WebSocket wrapper
  -> user_interaction voice provider
```

## Security Rules Before Running Community Weights

Do:

- Prefer `.safetensors`, `.gguf`, or MLX tensor formats.
- Avoid `trust_remote_code=True`.
- Avoid installing model-repo-bundled Python packages unless audited.
- Pin exact commit hashes before testing.
- Download into a sandbox directory.
- Keep app secrets out of the model runtime environment.
- Run with network disabled if possible after download.

Do not:

- Run arbitrary `setup.py`, shell scripts, or bundled Python packages from a community model repo.
- Load `.pt` or pickle-like weights from untrusted users in a financial app runtime.
- Treat community quantization metadata as proof of correctness.
- Use the model in production without quality, privacy, and prompt-injection tests.

## Recommended Next Experiment

Use `aufklarer/PersonaPlex-7B-MLX-8bit` only as an isolated local experiment:

```bash
mkdir -p user_interaction/models/personaplex-mlx
user_interaction/.venv/bin/python -m pip install "huggingface_hub[hf_xet]"
user_interaction/.venv/bin/huggingface-cli download \
  --local-dir user_interaction/models/personaplex-mlx/PersonaPlex-7B-MLX-8bit \
  aufklarer/PersonaPlex-7B-MLX-8bit
```

Then test through `soniqo/speech-swift`, not through `python -m moshi.server`.
