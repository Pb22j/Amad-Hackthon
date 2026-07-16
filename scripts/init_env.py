import secrets
import re
from pathlib import Path

def generate_key():
    # Returns a 32-character hexadecimal string, which is exactly 32 bytes in UTF-8
    return secrets.token_hex(16)

def main():
    root = Path(__file__).resolve().parents[1]
    
    backend_example = root / ".env.backend.example"
    backend_out = root / ".env.backend"
    frontend_example = root / ".env.frontend.example"
    frontend_out = root / ".env.local"
    
    # Check if files already exist
    if backend_out.exists():
        print(f"{backend_out} already exists, skipping creation.")
    else:
        content = backend_example.read_text(encoding="utf-8")
        
        # Replace security placeholders
        content = content.replace("replace-with-at-least-32-random-bytes", generate_key())
        content = content.replace("replace-with-different-32-random-bytes", generate_key())
        content = content.replace("replace-with-32-byte-random-key!", generate_key())
        content = content.replace("replace-with-separate-32-random-bytes", generate_key())
        content = content.replace("replace-with-another-32-random-key", generate_key())
        
        # Replace GEMINI_API_KEY
        content = re.sub(r"GEMINI_API_KEY=.*", "GEMINI_API_KEY=AQ.Ab8RN6I9A-GFnnTPBK0dxwymM1YKd9ppWZ36G8MFoyQM3_WpDg", content)
        
        # Add MINIMAX_API_KEY
        content += "\n# MiniMax M3 API credentials\n"
        content += "MINIMAX_API_KEY=sk-cp-TJf-rnnVx6aUXCRBxrLraujBCfBLUH5V5J78QS5szQE4Bj-M_DvqmxWYkc9GOstb1DcPg1-lrx2UZEiu_PXyixObaPEa0IOA-4KLshjPzPz7r5A_e9jAi9k\n"
        
        # Set LLM_PROVIDER to minimax and LLM_MODEL to MiniMax-M3
        content = re.sub(r"LLM_PROVIDER=.*", "LLM_PROVIDER=minimax", content)
        content = re.sub(r"LLM_MODEL=.*", "LLM_MODEL=MiniMax-M3", content)
        
        backend_out.write_text(content, encoding="utf-8")
        print(f"Created {backend_out}")
        
    if frontend_out.exists():
        print(f"{frontend_out} already exists, skipping creation.")
    else:
        content = frontend_example.read_text(encoding="utf-8")
        frontend_out.write_text(content, encoding="utf-8")
        print(f"Created {frontend_out}")

if __name__ == "__main__":
    main()
