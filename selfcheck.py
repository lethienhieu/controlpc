"""
selfcheck.py — autonomous end-to-end control self-check for CONTROLPC.

Drives the REAL agent (GPU LLM) through a few "control the computer" tasks,
verifies the target app actually launched (via tasklist), measures latency, and
loops the whole suite until every task passes (or MAX_ROUNDS is hit).

Round 1 runs "cold" (plan cache cleared -> exercises the LLM). Later rounds run
"warm" (skill-cache replay -> should be much faster). Run from the repo root:

    backend\\venv\\Scripts\\python selfcheck.py
"""
import os
import sys
import time
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "backend"))
sys.path.insert(0, os.path.join(BASE, "backend", "app"))

# Force "bypass" so the agent auto-executes without waiting for human approval —
# this is an automated test harness, not interactive use.
from policy import permissions  # noqa: E402
_orig_safety = permissions.get_safety_settings
permissions.get_safety_settings = lambda: {**_orig_safety(), "permission_mode": "bypass"}

from agent.executor import AgentExecutor  # noqa: E402
from agent.llm import LocalLLM  # noqa: E402
from agent.prompts import CHAT_REPLY_PROMPT  # noqa: E402
from database import memory  # noqa: E402

NO_WINDOW = 0x08000000

# Control tasks: goal -> a substring that must appear in `tasklist`, plus the
# image name(s) to kill for cleanup.
TASKS = [
    {"goal": "open notepad", "needle": "notepad", "kill": ["notepad.exe", "Notepad.exe"]},
    {"goal": "open calculator", "needle": "calc", "kill": ["calc.exe", "CalculatorApp.exe", "Calculator.exe"]},
]
MAX_ROUNDS = 3
LAUNCH_TIMEOUT = 18  # seconds to wait for the app window/process to appear


def tasklist_lower() -> str:
    try:
        return subprocess.run(["tasklist"], capture_output=True, text=True,
                              creationflags=NO_WINDOW, timeout=10).stdout.lower()
    except Exception:
        return ""


def wait_for_proc(needle: str, timeout: int) -> float:
    """Return seconds until the process appears, or -1 on timeout."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if needle.lower() in tasklist_lower():
            return time.time() - t0
        time.sleep(0.4)
    return -1.0


def kill_apps(names):
    for n in names:
        subprocess.run(["taskkill", "/f", "/im", n], capture_output=True, creationflags=NO_WINDOW)


def main() -> int:
    print("=" * 60)
    print(" CONTROLPC — end-to-end control self-check")
    print("=" * 60)

    agent = AgentExecutor()
    if not (agent.llm.model_path and os.path.exists(agent.llm.model_path)):
        print("[ABORT] No GGUF model found — cannot run GPU control tests.")
        return 2

    # Warm the GPU server once so the first task isn't penalised by cold start.
    print("[warmup] loading model into VRAM…")
    t0 = time.time()
    try:
        agent.llm.generate(prompt="ping", max_tokens=1, temperature=0.0)
    except Exception as e:
        print(f"[ABORT] LLM warmup failed: {e}")
        return 2
    print(f"[warmup] ready in {time.time() - t0:.1f}s")

    # Chat latency check (responsiveness for a plain question).
    t0 = time.time()
    reply = agent.llm.generate(prompt=CHAT_REPLY_PROMPT.format(message="hi"),
                               max_tokens=40, temperature=0.3)
    chat_dt = time.time() - t0
    print(f"[chat ] {chat_dt:.1f}s -> {reply[:60]!r}")

    final_round_ok = False
    for rnd in range(1, MAX_ROUNDS + 1):
        warm = rnd > 1
        print(f"\n----- Round {rnd} ({'replay/warm' if warm else 'cold/LLM'}) -----")
        all_ok = True
        for task in TASKS:
            goal, needle = task["goal"], task["needle"]
            kill_apps(task["kill"])           # ensure a clean baseline
            time.sleep(0.6)
            if not warm:
                memory.delete_task_plan(goal)  # force the LLM path on round 1

            t0 = time.time()
            try:
                agent.start(goal=goal, ai_mode="gemma4", safety_confirmation=False)
            except Exception as e:
                print(f"  [FAIL] '{goal}' raised: {e}")
                all_ok = False
                continue
            plan_dt = time.time() - t0
            appeared = wait_for_proc(needle, LAUNCH_TIMEOUT)
            ok = appeared >= 0 and agent.status == "finished"
            total = plan_dt + (appeared if appeared >= 0 else 0)
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] '{goal}': status={agent.status} plan={plan_dt:.1f}s "
                  f"launch={'%.1fs' % appeared if appeared >= 0 else 'TIMEOUT'} total={total:.1f}s")
            kill_apps(task["kill"])           # cleanup so the desktop isn't littered
            time.sleep(0.4)
            all_ok = all_ok and ok

        if all_ok:
            final_round_ok = True
            print(f"\n[OK] All control tasks passed on round {rnd}.")
            break
        else:
            print(f"[retry] round {rnd} had failures — retrying…")

    LocalLLM.stop_server()
    print("\n" + "=" * 60)
    print(f"RESULT: {'SUCCESS — agent controlled the PC' if final_round_ok else 'FAILURE — tasks did not pass'}")
    print(f"        chat latency ~{chat_dt:.1f}s")
    print("=" * 60)
    return 0 if final_round_ok else 1


if __name__ == "__main__":
    sys.exit(main())
