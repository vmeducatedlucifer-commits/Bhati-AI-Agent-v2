"""Device control: Android over ADB and desktop OS control (optional deps)."""

from __future__ import annotations

import asyncio
import shutil

from app.tools.base import Permission, Tool, ToolContext, ToolResult, tool_schema


async def _run(command: str, timeout: int = 60) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        return 124, "", f"timeout after {timeout}s"
    return process.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


def _adb_available() -> bool:
    return shutil.which("adb") is not None


async def android_devices() -> ToolResult:
    if not _adb_available():
        return ToolResult.failure("adb not found on host. Install Android platform-tools.")
    code, out, err = await _run("adb devices -l")
    return ToolResult.success(out) if code == 0 else ToolResult.failure(err or out)


async def android_action(
    action: str, text: str = "", x: int = 0, y: int = 0, package: str = "", device: str = ""
) -> ToolResult:
    if not _adb_available():
        return ToolResult.failure("adb not found on host")
    prefix = f"adb {('-s ' + device) if device else ''}".strip()
    commands = {
        "tap": f"{prefix} shell input tap {x} {y}",
        "swipe": f"{prefix} shell input swipe {x} {y} {x} {max(y - 600, 0)} 300",
        "text": f"{prefix} shell input text '{text.replace(' ', '%s')}'",
        "back": f"{prefix} shell input keyevent 4",
        "home": f"{prefix} shell input keyevent 3",
        "open_app": f"{prefix} shell monkey -p {package} -c android.intent.category.LAUNCHER 1",
        "screenshot": f"{prefix} exec-out screencap -p > android_screen.png",
        "ui_dump": f"{prefix} shell uiautomator dump /sdcard/ui.xml && {prefix} shell cat /sdcard/ui.xml",
    }
    command = commands.get(action)
    if not command:
        return ToolResult.failure(f"Unsupported action '{action}'. Options: {', '.join(commands)}")
    code, out, err = await _run(command, timeout=120)
    return ToolResult.success(out or f"{action} ok") if code == 0 else ToolResult.failure(err or out)


async def desktop_action(action: str, x: int = 0, y: int = 0, text: str = "", keys: str = "") -> ToolResult:
    try:
        import pyautogui  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        return ToolResult.failure(f"Desktop control unavailable ({exc}). pip install pyautogui")
    pyautogui.FAILSAFE = True
    if action == "move":
        pyautogui.moveTo(x, y, duration=0.2)
    elif action == "click":
        pyautogui.click(x, y)
    elif action == "double_click":
        pyautogui.doubleClick(x, y)
    elif action == "type":
        pyautogui.typewrite(text, interval=0.02)
    elif action == "hotkey":
        pyautogui.hotkey(*[part.strip() for part in keys.split("+") if part.strip()])
    elif action == "screenshot":
        pyautogui.screenshot("desktop.png")
    else:
        return ToolResult.failure(f"Unsupported desktop action: {action}")
    return ToolResult.success(f"desktop {action} done")


DEVICE_TOOLS = [
    Tool(
        name="android_devices",
        description="List connected Android devices over ADB.",
        parameters=tool_schema(),
        handler=android_devices,
        permission=Permission.SYSTEM,
        tags=["device", "android"],
    ),
    Tool(
        name="android_action",
        description="Control an Android device: tap, swipe, text, back, home, open_app, screenshot, ui_dump.",
        parameters=tool_schema(
            action={"type": "string", "required": True},
            text={"type": "string"},
            x={"type": "integer", "default": 0},
            y={"type": "integer", "default": 0},
            package={"type": "string"},
            device={"type": "string"},
        ),
        handler=android_action,
        permission=Permission.SYSTEM,
        tags=["device", "android"],
    ),
    Tool(
        name="desktop_action",
        description="Control the host desktop: move, click, double_click, type, hotkey, screenshot.",
        parameters=tool_schema(
            action={"type": "string", "required": True},
            x={"type": "integer", "default": 0},
            y={"type": "integer", "default": 0},
            text={"type": "string"},
            keys={"type": "string", "description": "Hotkey combo like 'ctrl+shift+t'"},
        ),
        handler=desktop_action,
        permission=Permission.SYSTEM,
        tags=["device", "desktop"],
    ),
]
