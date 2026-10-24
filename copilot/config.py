import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DATA = Path(os.getenv("COPILOT_DATA_DIR", str(ROOT / "data"))).resolve()
AS_OF = "2026-10-21"  # Fixed synthetic snapshot; independent of the host clock.
OFFLINE_LABEL = "Offline deterministic demo — no generative LLM inference."


def approval_token() -> str:
    return os.getenv("APPROVAL_TOKEN", "local-demo-approver")
