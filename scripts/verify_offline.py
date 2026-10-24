"""Reproduce offline checks and export portable evidence. Never starts or queries a live LLM."""

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "reports" / "public"


def publication_check():
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd=ROOT, capture_output=True, check=True)
    candidates = sorted(set(result.stdout.decode("utf-8").strip("\0").split("\0")))
    problems = []
    text_suffixes = {".py", ".md", ".json", ".toml", ".txt", ".yaml", ".yml", ".xml", ".cmd"}
    private_path = re.compile(r"[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][^\s\\/]+")
    secret = re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
    candidate_set = set(candidates)
    total = 0
    for relative in candidates:
        path = ROOT / relative
        if not path.is_file():
            continue
        total += path.stat().st_size
        if path.stat().st_size > 5 * 1024 * 1024:
            problems.append({"file": relative, "issue": "Publication file exceeds 5 MiB"})
        if path.suffix.lower() not in text_suffixes:
            continue
        content = path.read_text(encoding="utf-8-sig")
        if private_path.search(content):
            problems.append({"file": relative, "issue": "Personal Windows filesystem path"})
        if secret.search(content):
            problems.append({"file": relative, "issue": "Potential secret; manual review required"})
        if path.suffix == ".md":
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
                target = target.strip("<>").split("#", 1)[0]
                if not target or re.match(r"(?:https?://|mailto:)", target):
                    continue
                resolved = (path.parent / unquote(target)).resolve()
                try:
                    link = resolved.relative_to(ROOT).as_posix()
                except ValueError:
                    link = ""
                if not resolved.exists() or link not in candidate_set:
                    problems.append({"file": relative, "issue": "Missing or unpublished relative link", "target": target})
    for private in [".env", ".venv/Scripts/python.exe", "data/models/weights.onnx", "data/business.sqlite",
                    "data/ollama-models/model.gguf", "data/ollama-install/OllamaSetup.exe", "logs/backend.log",
                    "reports/ollama-e2e.json"]:
        ignored = subprocess.run(["git", "check-ignore", "-q", private], cwd=ROOT).returncode == 0
        if not ignored:
            problems.append({"file": private, "issue": "Private/runtime file is not ignored"})
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "passed" if not problems else "failed", "candidate_files": len(candidates),
              "candidate_bytes": total, "problems": problems,
              "scope": "Local paths, common secret signatures, file sizes, ignore rules and relative links. External URLs are not contacted; this is not an exhaustive secret/security audit.",
              "git_push_performed": False}
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "publication-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-only", action="store_true", help="Recheck documentation and publication candidates without repeating tests")
    if parser.parse_args().publication_only:
        report = publication_check()
        print(json.dumps(report, indent=2))
        return int(report["status"] != "passed")
    logdir = ROOT / "reports" / "offline-checks"
    logdir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "LLM_MODE": "offline", "CRM_MODE": "mock", "ERP_MODE": "mock",
           "AZURE_FOUNDRY_MODE": "mock", "HF_HUB_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
           "PYTHONUTF8": "1", "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}
    commands = [
        ("ruff", ["-m", "ruff", "check", "copilot", "tests", "scripts", "dashboard.py", "launch.py", "conftest.py"]),
        ("dependencies", ["-m", "pip", "check"]),
        ("pytest", ["-m", "pytest", "-q", "-rs", "--junitxml=reports/portfolio-pytest.xml"]),
        ("baseline_evaluation", ["-m", "copilot.evaluate"]),
        ("retrieval_evaluation", ["-m", "copilot.evaluate_phase2"]),
        ("approval_restart", ["scripts/check_persistent_approval.py"]),
        ("streamlit", ["scripts/smoke_ui.py"]),
    ]
    started = datetime.now(timezone.utc).isoformat()
    checks = []
    for name, args in commands:
        print("Checking " + name, flush=True)
        begin = time.perf_counter()
        try:
            process = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True,
                                     text=True, encoding="utf-8", errors="replace", timeout=600)
            code, output = process.returncode, process.stdout + process.stderr
        except subprocess.TimeoutExpired:
            code, output = 124, "Offline check exceeded its 600-second process timeout."
        (logdir / (name + ".log")).write_text(output, encoding="utf-8")
        checks.append({"name": name, "command": "python " + " ".join(args), "exit_code": code,
                       "status": "passed" if code == 0 else "failed", "seconds": round(time.perf_counter() - begin, 3)})
        print(name + ": " + checks[-1]["status"], flush=True)
    counts = None
    if next(c for c in checks if c["name"] == "pytest")["exit_code"] == 0:
        suite = ET.parse(ROOT / "reports" / "portfolio-pytest.xml").getroot().find("testsuite")
        counts = {k: int(suite.get(k, "0")) for k in ("tests", "failures", "errors", "skipped")}
        counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]

    def loaded(name):
        return json.loads((ROOT / "reports" / name).read_text(encoding="utf-8-sig"))

    evaluation = loaded("phase2-evaluation.json") if checks[4]["exit_code"] == 0 else None
    report = {"started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "passed" if all(c["exit_code"] == 0 for c in checks) else "failed",
              "environment": {"python": platform.python_version(), "os": platform.system()},
              "execution_mode": "Offline deterministic demo — no generative LLM inference.",
              "live_llm_inference_requested": False, "commercial_api_used": False,
              "external_integrations_tested": False, "checks": checks, "pytest": counts,
              "retrieval": evaluation["retrieval"] if evaluation else None,
              "baseline_evaluation": loaded("evaluation.json") if checks[3]["exit_code"] == 0 else None,
              "approval_restart": loaded("approval-restart.json") if checks[5]["exit_code"] == 0 else None,
              "streamlit": loaded("ui-smoke.json") if checks[6]["exit_code"] == 0 else None}
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "validation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    publication = publication_check()
    print(json.dumps({"validation": report["status"], "pytest": counts, "publication": publication["status"]}, indent=2))
    return int(report["status"] != "passed" or publication["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
