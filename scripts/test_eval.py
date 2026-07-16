from dotenv import load_dotenv
import os
from pathlib import Path
import sys
import json

# Load env
root = Path(__file__).resolve().parents[1]
load_dotenv(root / ".env.backend")

# Import evaluation/task.py
sys.path.append(str(root))
from evaluation.task import run_agent

if len(sys.argv) < 2:
    query = "Show my checking account balance"
else:
    query = sys.argv[1]

print(f"Running agent with query: {query}")
try:
    report = run_agent(query)
    print(json.dumps(report, ensure_ascii=True, indent=2))
except Exception as e:
    print(f"Error occurred: {e}")
