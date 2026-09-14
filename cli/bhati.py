#!/usr/bin/env python3
"""bhati - terminal client for Bhati AI Agent v2 (Claude-Code style REPL).

Usage:
    bhati "fix the failing tests and open a PR"
    bhati --auto "build a landing page and deploy it"
    bhati --profile coder "refactor the auth module"
    bhati                      # interactive REPL

Env:
    BHATI_API   backend base URL (default http://localhost:8000)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

import httpx

API = os.getenv("BHATI_API", "http://localhost:8000")
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def send(message: str, session_id: str, mode: str, profile: str) -> None:
    payload = {"message": message, "session_id": session_id, "mode": mode, "profile": profile}
    event = ""
    try:
        with httpx.stream("POST", f"{API}/api/chat/stream", json=payload, timeout=None) as response:
            for line in response.iter_lines():
                if line.startswith("event: "):
                    event = line[7:]
                    continue
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:]).get("data", {})
                except json.JSONDecodeError:
                    continue
                if event == "message_delta":
                    sys.stdout.write(data.get("text", ""))
                    sys.stdout.flush()
                elif event == "tool_call":
                    print(f"\n{DIM}> {data.get('name')} {str(data.get('arguments'))[:120]}{RESET}")
                elif event == "tool_result":
                    mark = f"{GREEN}ok{RESET}" if data.get("ok") else f"{RED}failed{RESET}"
                    print(f"{DIM}  {data.get('name')} -> {mark}{RESET}")
                elif event == "plan_created":
                    print(f"\n{CYAN}Plan:{RESET}")
                    for task in data.get("plan", {}).get("tasks", []):
                        deps = ",".join(task.get("depends_on", []))
                        print(f"  [{task['id']}] {task['title']} ({task['agent']}){f' after {deps}' if deps else ''}")
                elif event == "task_updated":
                    task = data.get("task", {})
                    print(f"{DIM}  [{task.get('id')}] {task.get('status')}{RESET}")
                elif event == "final":
                    print(f"\n{data.get('content', '')}")
                elif event == "error":
                    print(f"\n{RED}Error: {data.get('error')}{RESET}")
    except httpx.ConnectError:
        print(f"{RED}Cannot reach Bhati API at {API}. Is the backend running?{RESET}")
        sys.exit(1)
    print()


def repl(session_id: str, mode: str, profile: str) -> None:
    print(f"{CYAN}Bhati AI Agent v2{RESET} {DIM}({API} | mode={mode} | profile={profile}){RESET}")
    print(f"{DIM}Commands: /auto /chat /profile <name> /session /exit{RESET}\n")
    while True:
        try:
            line = input(f"{CYAN}bhati>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line in {"/exit", "/quit"}:
            return
        if line == "/auto":
            mode = "autonomous"
            print(f"{DIM}mode=autonomous{RESET}")
            continue
        if line == "/chat":
            mode = "chat"
            print(f"{DIM}mode=chat{RESET}")
            continue
        if line.startswith("/profile"):
            profile = line.split(maxsplit=1)[-1] or profile
            print(f"{DIM}profile={profile}{RESET}")
            continue
        if line == "/session":
            print(f"{DIM}session={session_id}{RESET}")
            continue
        send(line, session_id, mode, profile)


def main() -> None:
    parser = argparse.ArgumentParser(prog="bhati", description="Bhati AI Agent v2 CLI")
    parser.add_argument("prompt", nargs="*", help="task to run; omit for interactive REPL")
    parser.add_argument("--auto", action="store_true", help="autonomous multi-agent mode")
    parser.add_argument("--profile", default="general", help="general|coder|researcher|operator|reviewer")
    parser.add_argument("--session", default=uuid.uuid4().hex[:16], help="reuse an existing session id")
    args = parser.parse_args()

    mode = "autonomous" if args.auto else "chat"
    if args.prompt:
        send(" ".join(args.prompt), args.session, mode, args.profile)
    else:
        repl(args.session, mode, args.profile)


if __name__ == "__main__":
    main()
