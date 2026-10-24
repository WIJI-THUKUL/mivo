"""Plugin: termux_api - battery, clipboard, notifications, toast, vibrate.

Requires the Termux:API app and `pkg install termux-api`.
"""
import shutil
import subprocess


def register(api):
    def run(cmd, stdin=None):
        if not shutil.which(cmd[0]):
            return f"Error: {cmd[0]} not found. Install with: pkg install termux-api (and the Termux:API app)"
        r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=20)
        return (r.stdout + r.stderr).strip() or "ok"

    def termux_api(a):
        act = a["action"]
        if act == "battery":
            return run(["termux-battery-status"])
        if act == "clipboard_get":
            return run(["termux-clipboard-get"])
        if act == "clipboard_set":
            return run(["termux-clipboard-set"], stdin=a.get("text", ""))
        if act == "notify":
            return run(["termux-notification", "--title", a.get("title", "MIVO CODE"),
                        "--content", a.get("text", "")])
        if act == "toast":
            return run(["termux-toast", a.get("text", "")])
        if act == "vibrate":
            return run(["termux-vibrate", "-d", "200"])
        return "Error: unknown action"

    api.tool(
        "termux_api",
        "Android helpers via Termux:API. actions: battery, clipboard_get, clipboard_set, notify, toast, vibrate.",
        {"type": "object",
         "properties": {"action": {"type": "string",
                                   "enum": ["battery", "clipboard_get", "clipboard_set", "notify", "toast", "vibrate"]},
                        "text": {"type": "string"}, "title": {"type": "string"}},
         "required": ["action"]},
        termux_api,
        permission=lambda a: "safe" if a.get("action") in ("battery", "vibrate", "toast") else "ask",
    )
