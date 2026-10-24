#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MIVO CODE - a terminal AI coding agent for Termux.

Turns any OpenAI-compatible chat model into a coding agent that can read,
edit and run code in your project.

Contributors: Wiji & Claude
"""
from __future__ import annotations

import argparse
import atexit
import difflib
import fnmatch
import importlib.util
import json
import os
import platform
import queue
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

try:
    import requests
    from prompt_toolkit import PromptSession
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from rich.console import Console
    from rich.markup import escape
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text
    from rich.theme import Theme
    from rich import box
except ImportError as e:  # pragma: no cover
    print(f"Missing dependency: {e.name}\nRun: pip install requests rich prompt_toolkit")
    sys.exit(1)

VERSION = "1.0"
MIVO_HOME = Path(os.environ.get("MIVO_HOME", str(Path.home() / ".mivo")))
CONFIG_FILE = MIVO_HOME / "config.json"
SESSION_DIR = MIVO_HOME / "sessions"
SKILL_DIR = MIVO_HOME / "skills"
PLUGIN_DIR = MIVO_HOME / "plugins"
HISTORY_FILE = MIVO_HOME / "input_history"

MAX_OUT = 12000
TOOL_TAG = "<tool_call>"
THINK_TAG, THINK_END = "<think>", "</think>"
DENIED = ("The user denied permission for this action. Do not retry the same "
          "action; ask the user how they would like to proceed.")

# --------------------------------------------------------------------------
# Themes and mascot
# --------------------------------------------------------------------------
THEMES = {
    "android": {"brand": "#3ddc84", "accent": "#4fc3f7", "muted": "grey58", "grad": ("#3ddc84", "#4fc3f7"),
                "mascot": {"G": "#3ddc84", "L": "#9cf5c3", "D": "#1f9d5b", "o": "#0b3d2e"}},
    "ocean":   {"brand": "#4fc3f7", "accent": "#80deea", "muted": "grey58", "grad": ("#4fc3f7", "#7c4dff"),
                "mascot": {"G": "#3fb7f0", "L": "#a8e6ff", "D": "#1b7db3", "o": "#0a3350"}},
    "sunset":  {"brand": "#ff9f5a", "accent": "#ff6b9d", "muted": "grey58", "grad": ("#ffd54f", "#ff4081"),
                "mascot": {"G": "#ff9f5a", "L": "#ffd0a8", "D": "#d9652b", "o": "#5a2310"}},
    "grape":   {"brand": "#b388ff", "accent": "#ff80ab", "muted": "grey58", "grad": ("#b388ff", "#ff80ab"),
                "mascot": {"G": "#a678f5", "L": "#d6c1ff", "D": "#6d3fc0", "o": "#2a1260"}},
    "mono":    {"brand": "#e0e0e0", "accent": "#9e9e9e", "muted": "grey50", "grad": ("#ffffff", "#8a8a8a"),
                "mascot": {"G": "#cfcfcf", "L": "#ffffff", "D": "#8a8a8a", "o": "#2b2b2b"}},
}
_theme_name = "android"


def theme_styles(name):
    t = THEMES.get(name, THEMES["android"])
    return {"brand": t["brand"], "accent": t["accent"], "ok": "#3ddc84", "muted": t["muted"],
            "warn": "#ffd54f", "err": "#ff5252"}


console = Console(highlight=False, theme=Theme(theme_styles("android")))


def apply_theme(name):
    global _theme_name
    _theme_name = name if name in THEMES else "android"
    console.push_theme(Theme(theme_styles(_theme_name)))
    return _theme_name


def pt_brand():
    c = THEMES[_theme_name]["brand"]
    return f"fg:{c} bold"


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def gradient(text, c1, c2):
    a, b, n, out = hex_to_rgb(c1), hex_to_rgb(c2), max(len(text) - 1, 1), ""
    for i, ch in enumerate(text):
        if ch == " ":
            out += " "
            continue
        col = "#%02x%02x%02x" % tuple(int(a[k] + (b[k] - a[k]) * i / n) for k in range(3))
        out += f"[bold {col}]{ch}[/]"
    return out


# 16x16 pixel mascot (shaded, outlined, with antenna lights, cheeks, smile and a glowing chest badge).
# Drawn with half-blocks, each pixel 2 columns wide -> 32 columns x 8 rows.
MASCOT = [
    "....R......R....",
    ".....G....G.....",
    "....oooooooo....",
    "...oLLGGGGGGo...",
    "..oLLGGGGGGGGo..",
    "..oGGWWGGWWGGo..",
    "..oGGWKGGWKGGo..",
    "..oGPGGGGGGPGo..",
    "..oDDGKKKKGDDo..",
    "...oooooooooo...",
    ".DD.oLGGGGGo.DD.",
    ".DD.oGGYYGGo.DD.",
    ".DD.oGGOOGGo.DD.",
    "....oDDDDDDo....",
    "....oGGooGGo....",
    "....oDDooDDo....",
]
MASCOT_BASE = {"W": "#ffffff", "K": "#0b2a3a", "P": "#ff8fa3", "Y": "#ffd54f", "O": "#ff9800", "R": "#ff5252"}
MASCOT_W = len(MASCOT[0]) * 2


def mascot_rows(frame=0):
    rows = [list(r) for r in MASCOT]
    if frame == 1:      # blink
        rows[5][3:13] = list("GGGGGGGGGG")
        rows[6][3:13] = list("GGooGGooGG")
    elif frame == 2:    # antenna lights flash
        rows[0] = [("Y" if c == "R" else c) for c in rows[0]]
    return rows


def render_mascot(frame=0):
    """Rich-markup lines of the mascot (8 rows of half-blocks)."""
    pal = dict(MASCOT_BASE)
    pal.update(THEMES[_theme_name]["mascot"])
    rows, lines = mascot_rows(frame), []
    for r in range(0, len(rows), 2):
        out = ""
        for top, bot in zip(rows[r], rows[r + 1]):
            tc, bc = pal.get(top), pal.get(bot)
            if tc and bc:
                cell = f"[{tc} on {bc}]▀[/]"
            elif tc:
                cell = f"[{tc}]▀[/]"
            elif bc:
                cell = f"[{bc}]▄[/]"
            else:
                cell = " "
            out += cell * 2
        lines.append(out)
    return lines


def describe_env():
    if os.environ.get("PREFIX", "").startswith("/data/data/com.termux"):
        return "Termux on Android"
    name = sys.platform
    try:
        m = re.search(r'PRETTY_NAME="?([^"\n]+)', Path("/etc/os-release").read_text())
        name = m.group(1) if m else name
    except OSError:
        pass
    root = " as root" if hasattr(os, "geteuid") and os.geteuid() == 0 else ""
    return f"{name}{root}"


DEFAULT_RULES = """You are MIVO CODE, an expert AI coding agent running in a terminal ({env}). You build, debug and run real projects by calling tools.

Working directory: {cwd}

HOW TO WORK
1. Understand: read the request, then look at the project map and the relevant files before changing anything.
2. Plan: for multi-step work make a short checklist with todo_write and keep it updated.
3. Build: write complete, working code. No placeholders, no "..." and no TODO stubs. Handle errors and edge cases.
4. Verify: run the code or tests with bash, read the output, and fix problems until it works.
5. Report: finish with a 1-3 line summary of what changed and how to run it.

ACT, DON'T NARRATE
- Say at most one short sentence, then CALL THE TOOLS. No long plans, no tutorials, no step-by-step essays before acting.
- Never tell the user to create folders, copy code or run commands: do it yourself with the tools.
- Never paste file contents in chat: write_file saves them.

TOOLS (call them, do not describe them)
- bash {"command": "..."}: run anything (mkdir -p, python x.py, npm run build, ./gradlew ...). Non-interactive: use -y flags. `cd` persists between calls.
- read_file {"path", "offset", "limit"} / list_dir {"path"} / glob {"pattern"} / grep {"pattern", "path"}: look before you change.
- write_file {"path", "content"}: whole new file. edit_file {"path", "old_string", "new_string"}: exact replacement that matches once. multi_edit {"path", "edits": [{"old_string", "new_string"}, ...]}: several changes to one file in ONE call.
- After write_file / edit_file / multi_edit you get a syntax check back: fix any warning immediately.
- todo_write, remember, use_skill, web_search (when available).

SAVING TOKENS
- Look before reading: use grep or the project map first, then read only the lines you need (read_file offset/limit, default 400 lines). Never re-read a file that did not change.
- Put independent tool calls in ONE response (for example read three files at once).
- Prefer edit_file / multi_edit over rewriting a whole file. Do not repeat code in chat. Keep replies short.

AUTONOMY
- Work on your own. Never ask for permission or confirmation; make sensible assumptions and continue until the task is done. Ask the user only if you are truly blocked.
- Creating, editing and saving files and folders is instant and needs no approval. Only gradle, git writes and package installs ask the user, so use them only when needed.

FILES
- New file: write_file (put "path" first, then "content"). It is saved to disk while you write.
- Existing file: edit_file with a small exact replacement. Read the file first if you did not just write it.
- If you show a COMPLETE file in your reply, label the code fence with its path (```python src/app.py) and it is saved automatically (overwriting). Never label a partial snippet with a path.
- Keep files focused and reasonably small; split big programs into modules.

MEMORY
- Every turn you receive a live PROJECT MAP, FILES YOU CHANGED and PROJECT NOTES. Trust them over your recollection and use the exact file and function names they list. Never invent names.
- Use remember to store decisions, conventions, architecture and what each file does.

STYLE
- Be concise. Do not paste files you just wrote. Explanations are plain text; code in replies goes in fenced blocks with a language tag.
- Reply in the user's language.
- Install system packages with the OS package manager (Termux: pkg, no sudo; Ubuntu/Debian: apt, sudo is optional when root). Prefer pure-Python or lightweight packages.
- If a script says "Permission denied" or the folder is mounted noexec, run it through the interpreter: `sh gradlew`, `bash run.sh`, `python3 tool.py`.
- Use web_search (when available) for current docs, versions and error messages. Use use_skill when a skill matches the task."""


ENV_MAP = {"api_key": "MIVO_API_KEY", "base_url": "MIVO_BASE_URL", "model": "MIVO_MODEL"}


class Config:
    def __init__(self, data=None, use_env=True):
        self.use_env = use_env
        self.data = {}
        if data is not None:
            self.data = dict(data)
        elif CONFIG_FILE.exists():
            try:
                self.data = json.loads(CONFIG_FILE.read_text("utf-8"))
            except Exception:
                self.data = {}

    def get(self, key, default=None):
        if self.use_env and key in ENV_MAP and os.environ.get(ENV_MAP[key]):
            return os.environ[ENV_MAP[key]]
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def complete(self):
        return all(self.get(k) for k in ("api_key", "base_url", "model"))

    def save(self):
        MIVO_HOME.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), "utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(CONFIG_FILE)


# --------------------------------------------------------------------------
# Providers: OpenAI-compatible, Anthropic, Google Gemini, Ollama, Azure OpenAI
# --------------------------------------------------------------------------
API_TYPES = ("openai", "anthropic", "gemini", "ollama", "azure")
API_LABELS = {"openai": "OpenAI-compatible", "anthropic": "Anthropic native", "gemini": "Google Gemini native",
              "ollama": "Ollama native", "azure": "Azure OpenAI"}
DYN_MARK = "\n\n<<<MIVO-DYNAMIC>>>\n\n"   # splits the stable system prompt from the per-turn part (prompt caching)


def detect_api_type(url):
    """Guess the protocol from the URL (override with "api_type" in config.json)."""
    u = re.sub(r"^https?://", "", (url or "").strip().lower())
    host, _, path = u.partition("/")
    path = "/" + path
    if "anthropic.com" in host:
        return "anthropic"
    if "generativelanguage.googleapis.com" in host and "/openai" not in path:
        return "gemini"
    if "openai.azure.com" in host or "cognitiveservices.azure.com" in host:
        return "azure"
    if (":11434" in host or "ollama" in host) and not re.search(r"/v\d", path):
        return "ollama"
    return "openai"


def normalize_base_url(url: str, api_type=None) -> str:
    """Return the API root for the protocol, never an endpoint like /chat/completions."""
    url = (url or "").strip().rstrip("/")
    if not re.match(r"^https?://", url):
        local = re.match(r"^(localhost|127\.|10\.|192\.168\.|\[::1\])", url)
        url = ("http://" if local else "https://") + url
    api_type = api_type if api_type in API_TYPES else detect_api_type(url)
    url = re.sub(r"/models/[^/]+:(?:stream)?[gG]enerateContent$", "", url)
    while True:  # strip endpoint paths if the user pasted a full URL
        new = re.sub(r"/(chat/completions|completions|models|messages|api/chat|api/generate|api/tags)/?$", "", url).rstrip("/")
        if new == url:
            break
        url = new
    if not re.sub(r"^https?://[^/]+", "", url):  # bare host -> add the protocol's usual root
        url += {"anthropic": "/v1", "gemini": "/v1beta", "ollama": "", "azure": "/openai/v1"}.get(api_type, "/v1")
    return url


def deep_update(a, b):
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            deep_update(a[k], v)
        else:
            a[k] = v
    return a


def clean_msgs(messages):
    """Copy of the history without MIVO-private keys (_thinking, _sig): other APIs would reject them."""
    out = []
    for m in messages:
        m2 = {k: v for k, v in m.items() if not k.startswith("_")}
        if m2.get("tool_calls"):
            m2["tool_calls"] = [{k: v for k, v in tc.items() if not k.startswith("_")} for tc in m2["tool_calls"]]
        if isinstance(m2.get("content"), str):
            m2["content"] = m2["content"].replace(DYN_MARK, "\n\n")
        out.append(m2)
    return out


def split_system(messages):
    text = "\n\n".join(m.get("content") or "" for m in messages if m["role"] == "system")
    static, _, dyn = text.partition(DYN_MARK)
    return static.strip(), dyn.strip(), [m for m in messages if m["role"] != "system"]


def to_anthropic_messages(msgs):
    out = []

    def push(role, blocks):
        out.append({"role": role, "content": blocks})
    for m in msgs:
        role = m["role"]
        if role == "assistant":
            blocks = list(m.get("_thinking") or [])   # thinking blocks must be passed back during tool loops
            if (m.get("content") or "").strip():
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls") or []:
                blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"],
                               "input": json_loads_safe(tc["function"]["arguments"]) or {}})
            push("assistant", blocks or [{"type": "text", "text": "..."}])
        elif role == "tool":
            blk = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m.get("content") or "(empty)"}
            last = out[-1] if out else None
            if last and last["role"] == "user" and last["content"] and last["content"][0].get("type") == "tool_result":
                last["content"].append(blk)
            else:
                push("user", [blk])
        else:
            push("user", [{"type": "text", "text": m.get("content") or "."}])
    return out


_SCHEMA_KEYS = {"type", "properties", "required", "items", "enum", "description"}


def clean_schema(s):
    if isinstance(s, dict):
        return {k: (clean_schema(v) if k != "properties" else {pk: clean_schema(pv) for pk, pv in v.items()})
                for k, v in s.items() if k in _SCHEMA_KEYS}
    return s


def to_gemini_contents(msgs):
    contents, names = [], {}
    for m in msgs:
        role = m["role"]
        if role == "assistant":
            parts = []
            if (m.get("content") or "").strip():
                parts.append({"text": m["content"]})
            for tc in m.get("tool_calls") or []:
                names[tc["id"]] = tc["function"]["name"]
                part = {"functionCall": {"name": tc["function"]["name"],
                                         "args": json_loads_safe(tc["function"]["arguments"]) or {}}}
                if tc.get("_sig"):
                    part["thoughtSignature"] = tc["_sig"]
                parts.append(part)
            contents.append({"role": "model", "parts": parts or [{"text": "..."}]})
        elif role == "tool":
            part = {"functionResponse": {"name": names.get(m["tool_call_id"], "tool"),
                                         "response": {"result": m.get("content") or ""}}}
            last = contents[-1] if contents else None
            if last and last["role"] == "user" and last["parts"] and "functionResponse" in last["parts"][0]:
                last["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part]})
        else:
            contents.append({"role": "user", "parts": [{"text": m.get("content") or "."}]})
    return contents


def to_ollama_messages(msgs):
    out, names = [], {}
    for m in msgs:
        if m["role"] == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                names[tc["id"]] = tc["function"]["name"]
            out.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": [
                {"function": {"name": tc["function"]["name"],
                              "arguments": json_loads_safe(tc["function"]["arguments"]) or {}}}
                for tc in m["tool_calls"]]})
        elif m["role"] == "tool":
            out.append({"role": "tool", "content": m.get("content") or "", "tool_name": names.get(m["tool_call_id"], "")})
        else:
            out.append({"role": m["role"], "content": m.get("content") or ""})
    return out


class ProviderError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body

    def _info(self):
        try:
            d = json.loads(self.body)
            err = d.get("error", d) if isinstance(d, dict) else {}
            if isinstance(err, str):
                err = {"message": err}
            return err if isinstance(err, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def friendly(self):
        info = self._info()
        msg = info.get("message") or self.body.strip()[:300] or "no details"
        code = info.get("code") or info.get("type") or ""
        tag = f"{self.status}" if self.status else str(code or "error")
        return f"Provider error ({tag}): {msg}"

    def transient(self):
        """Temporary failure worth retrying (overload, upstream down, rate limit)."""
        if self.status in (408, 429, 500, 502, 503, 504, 529):
            return True
        text = (str(self._info().get("code", "")) + " " + str(self._info().get("type", "")) + " "
                + str(self._info().get("message", ""))).lower()
        return any(k in text for k in ("unavailable", "overloaded", "rate limit", "rate_limit",
                                       "try again", "retry", "timeout", "server_error", "busy", "empty_response"))


class Provider:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.http = requests.Session()   # connection reuse = faster turns
        self.extra_body, self.last_usage = {}, None

    # ---- protocol / endpoints
    @property
    def api_type(self):
        t = str(self.cfg.get("api_type") or "auto").lower()
        return t if t in API_TYPES else detect_api_type(self.cfg.get("base_url") or "")

    @property
    def base(self):
        return normalize_base_url(self.cfg.get("base_url"), self.api_type)

    @property
    def label(self):
        return API_LABELS[self.api_type]

    def headers(self):
        key, t = self.cfg.get("api_key") or "", self.api_type
        h = {"Content-Type": "application/json"}
        if t == "anthropic":
            h.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
        elif t == "gemini":
            h["x-goog-api-key"] = key
        elif t == "azure":
            h["api-key"] = key
        elif key:
            h["Authorization"] = f"Bearer {key}"
        style = self.cfg.get("auth_style") or ""
        if style == "bearer" and key:
            h["Authorization"] = f"Bearer {key}"
        elif style == "x-api-key":
            h["x-api-key"] = key
        elif style == "api-key":
            h["api-key"] = key
        elif style == "none":
            for k in ("Authorization", "x-api-key", "api-key", "x-goog-api-key"):
                h.pop(k, None)
        h.update(self.cfg.get("extra_headers") or {})
        return h

    def _chat_url(self, stream=True):
        t, b = self.api_type, self.base
        if t == "anthropic":
            return b + "/messages"
        if t == "gemini":
            m = str(self.cfg.get("model"))
            m = m if m.startswith("models/") else "models/" + m
            return f"{b}/{m}:" + ("streamGenerateContent?alt=sse" if stream else "generateContent")
        if t == "ollama":
            return b + "/api/chat"
        if t == "azure" and "/deployments/" in b:
            return f"{b}/chat/completions?api-version={self.cfg.get('api_version') or '2024-10-21'}"
        return b + "/chat/completions"

    # ---- request bodies
    def _payload(self, messages, tools, stream):   # OpenAI-compatible
        p = {"model": self.cfg.get("model"), "messages": clean_msgs(messages), "stream": stream}
        if tools:
            p["tools"] = tools
        p.update(self.cfg.get("extra_params", {}) or {})
        p.update(self.extra_body or {})   # thinking settings
        return p

    def _anthropic_body(self, messages, tools, stream):
        static, dyn, rest = split_system(messages)
        body = {"model": self.cfg.get("model"), "max_tokens": int(self.cfg.get("max_tokens") or 8192),
                "stream": stream, "messages": to_anthropic_messages(clean_for_anthropic(rest))}
        if static or dyn:
            blocks = []
            if static:
                blocks.append({"type": "text", "text": static, "cache_control": {"type": "ephemeral"}})
            if dyn:
                blocks.append({"type": "text", "text": dyn})
            body["system"] = blocks
        if tools:
            body["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                              "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}}
                             for t in tools]
        body.update(self.cfg.get("extra_params", {}) or {})
        deep_update(body, self.extra_body)
        th = body.get("thinking") or {}
        if th.get("budget_tokens"):
            body["max_tokens"] = max(body["max_tokens"], th["budget_tokens"] + 4096)
        return body

    def _gemini_body(self, messages, tools):
        static, dyn, rest = split_system(messages)
        body = {"contents": to_gemini_contents(rest)}
        sys_text = (static + "\n\n" + dyn).strip()
        if sys_text:
            body["systemInstruction"] = {"parts": [{"text": sys_text}]}
        if tools:
            body["tools"] = [{"functionDeclarations": [
                {"name": t["function"]["name"], "description": t["function"].get("description", ""),
                 "parameters": clean_schema(t["function"].get("parameters") or {"type": "object", "properties": {}})}
                for t in tools]}]
        deep_update(body, self.cfg.get("extra_params", {}) or {})
        deep_update(body, self.extra_body)
        return body

    def _ollama_body(self, messages, tools, stream):
        body = {"model": self.cfg.get("model"), "messages": to_ollama_messages(clean_msgs(messages)), "stream": stream}
        if tools:
            body["tools"] = tools
        body.update(self.cfg.get("extra_params", {}) or {})
        body.update(self.extra_body or {})
        return body

    # ---- helpers
    def _post(self, url, body, stream):
        r = self.http.post(url, headers=self.headers(), json=body, stream=stream, timeout=(15, 300))
        if r.status_code != 200:
            text = r.text
            r.close()
            raise ProviderError(r.status_code, text)
        return r

    @staticmethod
    def _finalize(content, calls, extra=None):
        if not content and not calls:
            raise ProviderError(0, json.dumps({"message": "The provider returned an empty response.",
                                               "code": "empty_response"}))
        tool_calls = []
        for i in sorted(calls):
            c = calls[i]
            if not c["name"]:
                continue
            tc = {"id": c["id"] or "call_" + uuid.uuid4().hex[:12], "type": "function",
                  "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
            if c.get("sig"):
                tc["_sig"] = c["sig"]
            tool_calls.append(tc)
        out = {"content": "".join(content), "tool_calls": tool_calls}
        out.update(extra or {})
        return out

    # ---- verify / complete
    def verify(self):
        """Return (ok, message)."""
        t, model, started = self.api_type, self.cfg.get("model"), time.time()
        names = []
        try:
            if t == "ollama":
                r = self.http.get(self.base + "/api/tags", headers=self.headers(), timeout=20)
            elif t == "gemini":
                r = self.http.get(self.base + "/models?pageSize=200", headers=self.headers(), timeout=20)
            elif t == "anthropic":
                r = self.http.get(self.base + "/models?limit=100", headers=self.headers(), timeout=20)
            else:
                r = self.http.get(self.base + "/models", headers=self.headers(), timeout=20)
            if r.status_code == 200:
                try:
                    j = r.json()
                    names = [m.get("id") or m.get("name") or m.get("model") or "" for m in
                             (j.get("data") or j.get("models") or [])]
                    names = [n.split("/", 1)[-1] if t == "gemini" else n for n in names]
                except Exception:
                    names = []
                ms = int((time.time() - started) * 1000)
                if names and model and not any(n == model or n.startswith(str(model) + ":") for n in names):
                    return True, f"Connected · {self.label} · {ms} ms (note: '{model}' is not in the model list)"
                return True, f"Connected · {self.label} · {ms} ms"
            if r.status_code in (401, 403):
                return False, f"Invalid API key (HTTP {r.status_code})"
        except requests.RequestException as e:
            return False, f"Connection failed: {e}"
        # model list unavailable -> a minimal chat request proves key, URL and model
        try:
            self.complete([{"role": "user", "content": "hi"}])
            return True, f"Connected · {self.label} · {int((time.time() - started) * 1000)} ms (via chat)"
        except ProviderError as e:
            return False, e.friendly()[:240]
        except requests.RequestException as e:
            return False, f"Connection failed: {e}"

    def complete(self, messages):
        """Non-streaming call, returns text. Used for compaction and verification."""
        t = self.api_type
        if t == "anthropic":
            r = self._post(self._chat_url(False), self._anthropic_body(messages, None, False), False)
            return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        if t == "gemini":
            r = self._post(self._chat_url(False), self._gemini_body(messages, None), False)
            cands = r.json().get("candidates") or [{}]
            return "".join(p.get("text", "") for p in (cands[0].get("content") or {}).get("parts", [])
                           if not p.get("thought"))
        if t == "ollama":
            r = self._post(self._chat_url(False), self._ollama_body(messages, None, False), False)
            return (r.json().get("message") or {}).get("content") or ""
        r = self._post(self._chat_url(False), self._payload(messages, None, False), False)
        return r.json()["choices"][0]["message"].get("content") or ""

    # ---- streaming chat
    def chat(self, messages, tools, renderer):
        """Stream a reply. Returns {content, tool_calls}; reasoning goes to renderer.think_delta."""
        self.last_usage = None
        t = self.api_type
        if t == "anthropic":
            return self._chat_anthropic(messages, tools, renderer)
        if t == "gemini":
            return self._chat_gemini(messages, tools, renderer)
        if t == "ollama":
            return self._chat_ollama(messages, tools, renderer)
        return self._chat_openai(messages, tools, renderer)

    def _chat_openai(self, messages, tools, renderer):
        r = self._post(self._chat_url(True), self._payload(messages, tools, True), True)
        content, calls = [], {}
        ctype = r.headers.get("content-type", "").lower()
        try:
            if "event-stream" not in ctype and "json" in ctype:
                # Provider ignored stream=true and returned a full JSON body.
                rj = r.json()
                msg = rj["choices"][0]["message"]
                self.last_usage = rj.get("usage")
                rc = msg.get("reasoning_content") or msg.get("reasoning")
                if isinstance(rc, str) and rc:
                    renderer.think_delta(rc)
                if msg.get("content"):
                    content.append(msg["content"])
                    renderer.feed(msg["content"])
                for i, tc in enumerate(msg.get("tool_calls") or []):
                    fn = tc.get("function", {})
                    calls[i] = {"id": tc.get("id", ""), "name": fn.get("name", ""),
                                "arguments": fn.get("arguments", "")}
            else:
                for raw in r.iter_lines():
                    if not raw:
                        continue
                    line = raw.decode("utf-8", "replace")
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    top_level_err = ("message" in obj and "choices" not in obj
                                     and ("code" in obj or "type" in obj))
                    if (obj.get("error") or top_level_err) and not obj.get("choices"):
                        err = obj.get("error") or obj
                        code = err.get("code") if isinstance(err, dict) else None
                        status = code if isinstance(code, int) else (
                            503 if "unavailable" in str(code).lower() else 0)
                        raise ProviderError(status, json.dumps(err))
                    if obj.get("usage"):
                        self.last_usage = obj["usage"]
                    for ch in obj.get("choices") or []:
                        d = ch.get("delta") or {}
                        rt = d.get("reasoning_content") or d.get("reasoning") or d.get("thinking")
                        if isinstance(rt, str) and rt:
                            renderer.think_delta(rt)
                        tx = d.get("content")
                        if tx:
                            content.append(tx)
                            renderer.feed(tx)
                        for tc in d.get("tool_calls") or []:
                            slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                            if tc.get("id"):
                                slot["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                slot["name"] += fn["name"]
                            if fn.get("arguments"):
                                slot["arguments"] += fn["arguments"]
                            renderer.tool_delta(tc.get("index", 0), slot)
        finally:
            r.close()
        return self._finalize(content, calls)

    def _chat_anthropic(self, messages, tools, renderer):
        r = self._post(self._chat_url(True), self._anthropic_body(messages, tools, True), True)
        content, calls, blocks = [], {}, {}
        u_in = u_out = 0
        try:
            for raw in r.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", "replace")
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                kind = ev.get("type")
                if kind == "error":
                    err = ev.get("error") or {}
                    raise ProviderError(529 if err.get("type") == "overloaded_error" else 0, json.dumps(err))
                if kind == "message_start":
                    u = (ev.get("message") or {}).get("usage") or {}
                    u_in = sum(u.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens",
                                                       "cache_creation_input_tokens"))
                    u_out = u.get("output_tokens") or 0
                elif kind == "content_block_start":
                    cb, idx = ev.get("content_block") or {}, ev.get("index", 0)
                    if cb.get("type") == "tool_use":
                        calls[idx] = {"id": cb.get("id", ""), "name": cb.get("name", ""), "arguments": ""}
                        renderer.tool_delta(idx, calls[idx])
                    elif cb.get("type") == "thinking":
                        blocks[idx] = {"type": "thinking", "thinking": "", "signature": ""}
                    elif cb.get("type") == "redacted_thinking":
                        blocks[idx] = dict(cb)
                elif kind == "content_block_delta":
                    d, idx = ev.get("delta") or {}, ev.get("index", 0)
                    dt = d.get("type")
                    if dt == "text_delta":
                        content.append(d.get("text", ""))
                        renderer.feed(d.get("text", ""))
                    elif dt == "thinking_delta":
                        renderer.think_delta(d.get("thinking", ""))
                        if idx in blocks:
                            blocks[idx]["thinking"] += d.get("thinking", "")
                    elif dt == "signature_delta" and idx in blocks:
                        blocks[idx]["signature"] = d.get("signature", "")
                    elif dt == "input_json_delta" and idx in calls:
                        calls[idx]["arguments"] += d.get("partial_json", "")
                        renderer.tool_delta(idx, calls[idx])
                elif kind == "message_delta":
                    u_out = (ev.get("usage") or {}).get("output_tokens", u_out)
        finally:
            r.close()
        self.last_usage = {"prompt_tokens": u_in, "completion_tokens": u_out}
        return self._finalize(content, calls, {"thinking_blocks": [blocks[i] for i in sorted(blocks)]})

    def _chat_gemini(self, messages, tools, renderer):
        r = self._post(self._chat_url(True), self._gemini_body(messages, tools), True)
        content, calls = [], {}
        try:
            for raw in r.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", "replace")
                if not line.startswith("data:"):
                    continue
                try:
                    obj = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                if obj.get("error"):
                    err = obj["error"]
                    raise ProviderError(int(err.get("code") or 0), json.dumps(err))
                pf = obj.get("promptFeedback") or {}
                if pf.get("blockReason"):
                    raise ProviderError(400, json.dumps({"message": "Blocked by Gemini: " + pf["blockReason"]}))
                um = obj.get("usageMetadata")
                if um:
                    self.last_usage = {"prompt_tokens": um.get("promptTokenCount", 0),
                                       "completion_tokens": (um.get("candidatesTokenCount") or 0)
                                       + (um.get("thoughtsTokenCount") or 0)}
                for cand in obj.get("candidates") or []:
                    for part in (cand.get("content") or {}).get("parts") or []:
                        if part.get("thought") and part.get("text"):
                            renderer.think_delta(part["text"])
                        elif part.get("text"):
                            content.append(part["text"])
                            renderer.feed(part["text"])
                        fc = part.get("functionCall")
                        if fc:
                            idx = len(calls)
                            calls[idx] = {"id": "call_" + uuid.uuid4().hex[:12], "name": fc.get("name", ""),
                                          "arguments": json.dumps(fc.get("args") or {}),
                                          "sig": part.get("thoughtSignature")}
                            renderer.tool_delta(idx, calls[idx])
        finally:
            r.close()
        return self._finalize(content, calls)

    def _chat_ollama(self, messages, tools, renderer):
        r = self._post(self._chat_url(True), self._ollama_body(messages, tools, True), True)
        content, calls = [], {}
        try:
            for raw in r.iter_lines():
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if obj.get("error"):
                    raise ProviderError(500, json.dumps({"message": str(obj["error"])}))
                msg = obj.get("message") or {}
                if msg.get("thinking"):
                    renderer.think_delta(msg["thinking"])
                if msg.get("content"):
                    content.append(msg["content"])
                    renderer.feed(msg["content"])
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    args = fn.get("arguments")
                    idx = len(calls)
                    calls[idx] = {"id": "call_" + uuid.uuid4().hex[:12], "name": fn.get("name", ""),
                                  "arguments": args if isinstance(args, str) else json.dumps(args or {})}
                    renderer.tool_delta(idx, calls[idx])
                if obj.get("done"):
                    self.last_usage = {"prompt_tokens": obj.get("prompt_eval_count", 0),
                                       "completion_tokens": obj.get("eval_count", 0)}
        finally:
            r.close()
        return self._finalize(content, calls)


def clean_for_anthropic(msgs):
    """History for Anthropic: drop private keys except _thinking (needed) and strip the dynamic marker."""
    out = []
    for m in msgs:
        m2 = {k: v for k, v in m.items() if (not k.startswith("_")) or k == "_thinking"}
        if m2.get("tool_calls"):
            m2["tool_calls"] = [{k: v for k, v in tc.items() if not k.startswith("_")} for tc in m2["tool_calls"]]
        out.append(m2)
    return out


# --------------------------------------------------------------------------
# Streaming renderer: plain text vs. colored code blocks
# --------------------------------------------------------------------------
EXT_LANG = {"py": "python", "js": "javascript", "mjs": "javascript", "ts": "typescript", "sh": "bash",
            "md": "markdown", "yml": "yaml", "kt": "kotlin", "kts": "kotlin", "rs": "rust", "rb": "ruby",
            "h": "c", "hpp": "cpp", "htm": "html", "gradle": "groovy"}


def lang_for(path) -> str:
    ext = Path(path).suffix.lstrip(".").lower()
    return EXT_LANG.get(ext, ext or "text")


def print_code_line(line, lang):
    t = Text("│ ", style="brand")
    try:
        hl = Syntax(line, lang or "text", theme="monokai", background_color="default").highlight(line)
        hl.rstrip()
        t.append_text(hl)
    except Exception:
        t.append(line)
    console.print(t, soft_wrap=True)


_ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "/": "/", "\\": "\\", '"': '"'}


def json_str_after(text, key):
    """Decode the JSON string value for `key` from possibly incomplete JSON.
    Returns (value_so_far, closed) or None if that string has not started yet."""
    m = re.search(r'"%s"\s*:\s*"' % re.escape(key), text)
    if not m:
        return None
    i, n, out = m.end(), len(text), []
    while i < n:
        c = text[i]
        if c == '"':
            return "".join(out), True
        if c != "\\":
            out.append(c)
            i += 1
            continue
        if i + 1 >= n:
            break
        d = text[i + 1]
        if d != "u":
            out.append(_ESC.get(d, d))
            i += 2
            continue
        if i + 6 > n:
            break
        try:
            cp = int(text[i + 2:i + 6], 16)
        except ValueError:
            out.append("?")
            i += 6
            continue
        if 0xD800 <= cp < 0xDC00:  # high surrogate: wait for its pair
            if i + 12 > n:
                break
            try:
                lo = int(text[i + 8:i + 12], 16)
                cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                i += 6
            except ValueError:
                pass
        out.append(chr(cp))
        i += 6
    return "".join(out), False


class LiveWriter:
    """Shows write_file content as the model types it and saves it to disk as it arrives."""

    def __init__(self, on_open=None):
        self.on_open = on_open
        self.state = "wait"   # wait | live | done | off
        self.fh, self.path, self.lang = None, None, ""
        self.sent, self.buf = 0, ""

    def update(self, args):
        if self.state in ("off", "done"):
            return
        if self.state == "wait":
            r = json_str_after(args, "path")
            if not r or not r[1] or not r[0].strip():
                return
            p = resolve(r[0])
            if p.is_dir() or not path_ok_to_write(p):
                self.state = "off"   # outside the project: handled by the normal (permissioned) path
                return
            try:
                existed = p.exists()
                if self.on_open:
                    self.on_open(p, existed)
                p.parent.mkdir(parents=True, exist_ok=True)
                self.fh = open(p, "w", encoding="utf-8", newline="")
            except OSError:
                self.state = "off"
                return
            self.path, self.lang, self.state = p, lang_for(p), "live"
            console.print(f"[brand]●[/] [bold]write_file[/] [dim]{escape(rel(p))}[/]")
            console.print(Text(f"╭─ {self.lang} ", style="brand"))
        r = json_str_after(args, "content")
        if r is None:
            return
        text, closed = r
        new = text[self.sent:]
        if new:
            self.fh.write(new)
            self.fh.flush()           # auto-save while streaming
            self.sent = len(text)
            self.buf += new
            while "\n" in self.buf:
                line, self.buf = self.buf.split("\n", 1)
                print_code_line(line, self.lang)
        if closed:
            self.close()

    def close(self):
        if self.state == "live":
            if self.buf:
                print_code_line(self.buf, self.lang)
                self.buf = ""
            console.print(Text("╰─", style="brand"))
            try:
                self.fh.close()
            except OSError:
                pass
            self.state = "done"


# --------------------------------------------------------------------------
# Auto-save helpers: write permissions, code-fence file detection
# --------------------------------------------------------------------------
def path_ok_to_write(p: Path) -> bool:
    """Project files and normal user storage are fine; system and secret locations are not."""
    try:
        rp = str(p.resolve())
    except OSError:
        return False
    home = str(Path.home())
    protected = [home + "/.ssh", home + "/.gnupg", home + "/.termux", home + "/.bashrc", home + "/.profile",
                 home + "/.zshrc", str(CONFIG_FILE)]
    if any(rp == q or rp.startswith(q + os.sep) for q in protected):
        return False
    roots = {str(Path(os.getcwd()).resolve()), home, "/storage", "/sdcard", "/mnt/sdcard", "/tmp",
             os.environ.get("TMPDIR", "")}
    return any(r and (rp == r or rp.startswith(r.rstrip(os.sep) + os.sep)) for r in roots)


SHELL_LANGS = {"bash", "sh", "shell", "zsh", "console", "terminal", "cmd", "powershell", "bat", "fish"}
NOT_EXT = {"com", "org", "net", "io", "dev", "ai", "me", "co", "uk", "id"}
PATH_RX = re.compile(r"^[\w.~\-/\\]+\.\w{1,8}$")
LINE_PATH_RX = re.compile(
    r"^\s*(?:#{1,6}\s*|\*\*|\d+[.)]\s*|[-*]\s*)?(?:(?:file(?:name)?|path)\s*[:：]\s*)?"
    r"[`*_]*([\w.~\-/\\]+\.\w{1,8})[`*_]*\s*:?\s*\**\s*$", re.I)


def _looks_like_path(t):
    return bool(PATH_RX.match(t)) and t.rsplit(".", 1)[-1].lower() not in NOT_EXT


def parse_fence(info, prev_line=""):
    """(lang, path|None) from a code-fence info string, e.g. 'python src/app.py', 'js:app.js',
    'title="app.py"', or from a line directly above that contains only a file path."""
    toks = info.replace("{", " ").replace("}", " ").split()
    lang, path = "", None
    for i, tok in enumerate(toks):
        t = tok.strip("\"'`,")
        key, sep, val = t.partition("=")
        if sep and key.lower() in ("title", "file", "filename", "path"):
            t = val.strip("\"'`")
        elif ":" in t and i == 0:
            a, _, b = t.partition(":")
            if a and _looks_like_path(b):
                lang, t = a, b
        if _looks_like_path(t):
            path = path or t
        elif i == 0 and not lang:
            lang = t
    if path is None and lang.lower() not in SHELL_LANGS:
        m = LINE_PATH_RX.match(prev_line or "")
        if m and _looks_like_path(m.group(1)):
            path = m.group(1)
    return (lang or (lang_for(path) if path else "")), path


class FenceSaver:
    """Saves a labeled code block to disk line by line while it streams."""

    def __init__(self, path, on_open=None, on_done=None):
        self.p, self.fh, self.on_done = resolve(path), None, on_done
        if not path_ok_to_write(self.p) or self.p.is_dir():
            return
        try:
            existed = self.p.exists()
            if on_open:
                on_open(self.p, existed)
            self.p.parent.mkdir(parents=True, exist_ok=True)
            self.fh = open(self.p, "w", encoding="utf-8", newline="")
        except OSError:
            self.fh = None

    @property
    def ok(self):
        return self.fh is not None

    def write(self, line):
        if self.fh:
            self.fh.write(line + "\n")
            self.fh.flush()

    def close(self):
        if not self.fh:
            return False
        try:
            self.fh.close()
        finally:
            self.fh = None
        if self.on_done:
            self.on_done(self.p)
        return True


class StreamRenderer:
    """Prints tokens as they arrive. Plain text stays plain; fenced code is drawn as a colored block
    and, when labeled with a file path, saved to disk while it streams. Output is buffered per chunk."""

    def __init__(self, hide_tool_xml=False, on_first=None, on_live_open=None,
                 on_fence_open=None, on_fence_done=None, autosave=True, show_thinking=True):
        self.autosave, self.show_thinking = autosave, show_thinking
        self.tbuf, self.rbuf, self.rt_open, self.skip_nl = "", "", False, False
        self.hide_tool_xml, self.on_first = hide_tool_xml, on_first
        self.on_live_open, self.on_fence_open, self.on_fence_done = on_live_open, on_fence_open, on_fence_done
        self.mode = "text"          # text | code | hidden
        self.line, self.printed, self.codebuf, self.lang = "", 0, "", ""
        self.saver, self.started, self.last_char, self.prev_line = None, False, "\n", ""
        self.live, self._obuf = {}, []

    # -- buffered output
    def _flush(self):
        if self._obuf:
            console.out("".join(self._obuf), end="", highlight=False)
            self._obuf.clear()

    def _out(self, s):
        if s:
            self._obuf.append(s)
            self.last_char = s[-1]

    def _nl(self):
        if self.last_char != "\n":
            self._out("\n")

    # -- code blocks
    def _open_code(self, info):
        lang, path = parse_fence(info, self.prev_line)
        self._nl()
        self._flush()
        self.mode, self.lang, self.codebuf = "code", lang, ""
        self.saver = FenceSaver(path, self.on_fence_open, self.on_fence_done) if (path and self.autosave) else None
        title = f"╭─ {lang or 'code'} "
        if self.saver and self.saver.ok:
            title += f" {rel(self.saver.p)}"
        console.print(Text(title, style="brand"))

    def _code_line(self, line):
        if line.strip() == "```":
            saver, self.saver = self.saver, None
            tail = f"╰─ ✓ saved {rel(saver.p)}" if saver and saver.close() else "╰─"
            self._flush()
            console.print(Text(tail, style="brand"))
            self.mode, self.last_char = "text", "\n"
            return
        if self.saver:
            self.saver.write(line)
        self._flush()
        print_code_line(line, self.lang)

    # -- token input
    def feed(self, s):
        if not self.started:
            self.started = True
            if self.on_first:
                self.on_first()
        self._end_reasoning()
        for ch in s:
            self._char(ch)
        self._flush()

    def _char(self, ch):
        if self.mode == "hidden":
            return
        if self.mode == "think":   # <think>...</think> written as text by the model
            self.tbuf += ch
            if self.tbuf.endswith(THINK_END):
                body = self.tbuf[:-len(THINK_END)].rstrip("\n")
                if body.strip():
                    self._think_print(body)
                self.mode, self.tbuf, self.last_char, self.skip_nl = "text", "", "\n", True
            elif ch == "\n":
                self._think_print(self.tbuf.rstrip("\n"))
                self.tbuf = ""
            return
        if self.mode == "code":
            if ch == "\n":
                self._code_line(self.codebuf)
                self.codebuf = ""
            else:
                self.codebuf += ch
            return
        if ch == "\n":
            if self.skip_nl and not self.line:   # blank line right after </think>
                self.skip_nl = False
                return
            if self.line.lstrip().startswith("```"):
                self._open_code(self.line.lstrip()[3:].strip())
            else:
                self._out(self.line[self.printed:] + "\n")
                if self.line.strip():
                    self.prev_line = self.line
            self.line, self.printed = "", 0
            return
        self.line += ch
        self.skip_nl = False
        ln = self.line.lstrip()
        if ln == "" or ln.startswith("```") or ln in ("`", "``"):
            return  # could be an (indented) fence: hold until the line ends
        if ln.startswith(THINK_TAG):
            self.line, self.printed, self.mode, self.tbuf = "", 0, "think", ""
            self._think_header()
            return
        if len(ln) < len(THINK_TAG) and THINK_TAG.startswith(ln):
            return
        if self.hide_tool_xml:
            if ln.startswith(TOOL_TAG):
                self.mode = "hidden"
                return
            if len(ln) < len(TOOL_TAG) and TOOL_TAG.startswith(ln):
                return
        self._out(self.line[self.printed:])
        self.printed = len(self.line)

    # -- thinking display (provider reasoning stream or <think> text); never stored
    def _think_print(self, line):
        if self.show_thinking:
            self._flush()
            console.print(Text("  " + line, style="dim italic"), soft_wrap=True)

    def _think_header(self):
        if self.show_thinking:
            self._nl()
            self._flush()
            console.print(Text("✻ thinking", style="dim"))

    def think_delta(self, text):
        if not self.started:
            self.started = True
            if self.on_first:
                self.on_first()
        if not self.rt_open:
            if self.mode == "text":
                self._flush_text()
            self.rt_open = True
            self._think_header()
        self.rbuf += text
        while "\n" in self.rbuf:
            line, self.rbuf = self.rbuf.split("\n", 1)
            self._think_print(line)

    def _end_reasoning(self):
        if self.rt_open:
            if self.rbuf.strip():
                self._think_print(self.rbuf)
            self.rbuf, self.rt_open = "", False

    def _flush_text(self):
        if self.mode == "text" and self.line[self.printed:]:
            self._out(self.line[self.printed:])
            self.line, self.printed = "", 0
        self._nl()
        self._flush()

    def tool_delta(self, idx, slot):
        """Called for every streamed tool-call chunk; write_file is shown and saved live."""
        if not self.started:
            self.started = True
            if self.on_first:
                self.on_first()
        self._end_reasoning()
        if slot["name"] != "write_file" or not self.autosave:
            return
        w = self.live.get(idx)
        if w is None:
            self._flush_text()
            w = self.live[idx] = LiveWriter(self.on_live_open)
        w.update(slot["arguments"])

    def finish(self):
        self._end_reasoning()
        if self.mode == "think":
            if self.tbuf.strip():
                self._think_print(self.tbuf)
            self.mode, self.tbuf = "text", ""
        for w in self.live.values():
            w.close()
        if self.mode == "code":
            if self.codebuf:
                self._code_line(self.codebuf)
            if self.mode == "code":
                self._code_line("```")
        elif self.mode == "text" and self.line[self.printed:]:
            self._out(self.line[self.printed:])
        self._flush()
        if self.last_char != "\n" and self.started:
            console.out("")
            self.last_char = "\n"
        self.line, self.printed, self.codebuf = "", 0, ""


# --------------------------------------------------------------------------
# Permissions
# --------------------------------------------------------------------------
# Default is SAFE. Only these need a yes/no: gradle, git (write operations), installers.
SAFE_GIT = {"status", "log", "diff", "show", "branch", "remote", "rev-parse", "ls-files", "blame",
            "describe", "tag", "config", "add", "init", "help", "version", "grep", "shortlog",
            "reflog", "ls-tree"}
INSTALL_SUBS = {
    "npm": {"install", "i", "add", "ci", "update", "upgrade", "uninstall", "remove", "rm", "publish", "link"},
    "yarn": {"add", "install", "remove", "upgrade", "global", "publish"},
    "pnpm": {"add", "install", "i", "remove", "update", "up", "publish"},
    "bun": {"add", "install", "i", "remove", "update"},
    "pip": {"install", "uninstall"}, "pip3": {"install", "uninstall"},
    "pkg": {"install", "i", "remove", "uninstall", "upgrade", "update", "reinstall"},
    "cargo": {"install", "add", "publish"}, "gem": {"install", "uninstall"},
    "go": {"install", "get"}, "composer": {"install", "require", "update", "remove"},
}
ASK_ALWAYS = {"gradle", "gradlew", "npx", "pnpx", "bunx", "pipx", "uvx",
              "apt", "apt-get", "apk", "dpkg", "brew", "snap"}
DANGER_PATTERNS = [
    r"\bdd\b", r"\bmkfs", r"\bchmod\s+(-\S*R|--recursive)", r"\bchown\s+(-\S*R|--recursive)",
    r"\bsudo\b", r"(^|[;&|]\s*)su\b", r":\(\)\s*\{", r">\s*/dev/(sd|block|mmc)",
    r"(curl|wget)[^|;]*\|\s*(ba|z)?sh\b", r"\b(shutdown|reboot|poweroff)\b", r"\bkillall\b",
    r"\bgit\s+push\b.*(--force|\s-f\b)", r"\bgit\s+reset\s+--hard", r"\bgit\s+clean\s+-\S*f",
]


def strip_heredocs(cmd: str) -> str:
    """Drop heredoc bodies so their text is not mistaken for commands."""
    out, delim = [], None
    for line in cmd.split("\n"):
        if delim is not None:
            if line.strip() == delim:
                delim = None
            continue
        m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", line)
        if m:
            delim = m.group(1)
            line = line[:m.start()]
        out.append(line)
    return "\n".join(out)


def _rm_level(tokens):
    flags = [t for t in tokens[1:] if t.startswith("-")]
    targets = [t for t in tokens[1:] if not t.startswith("-")]
    recursive = any(re.match(r"^-\w*[rR]", f) or f == "--recursive" for f in flags)
    for t in targets:
        risky = t in ("/", "~", ".", "..", "*", "./", "/*", "~/") or t.startswith(("~", "$")) or ".." in t.split("/")
        if t.startswith("/") and not risky:
            risky = not inside_cwd(Path(t))
        if risky:
            return "danger" if recursive else "ask"
    return "safe"


def classify_command(cmd: str):
    """Return (level, keys). level: safe | ask | danger."""
    cmd = strip_heredocs(cmd)
    for p in DANGER_PATTERNS:
        if re.search(p, cmd):
            return "danger", None
    cleaned = re.sub(r"\d*>&\d+", "", cmd)
    keys = set()
    for seg in re.split(r"\|\||&&|;|\||\n|&", cleaned):
        seg = seg.strip()
        if not seg:
            continue
        try:
            tokens = shlex.split(seg)
        except ValueError:
            tokens = seg.split()
        while tokens and re.match(r"^\w+=", tokens[0]):
            tokens.pop(0)
        if not tokens:
            continue
        first = os.path.basename(tokens[0])
        if first in ("python", "python3") and tokens[1:3] == ["-m", "pip"]:
            first, tokens = "pip", tokens[2:]
        if first == "rm":
            lvl = _rm_level(tokens)
            if lvl == "danger":
                return "danger", None
            if lvl == "ask":
                keys.add("rm")
        elif first == "git":
            sub = next((t for t in tokens[1:] if not t.startswith("-")), "")
            if sub not in SAFE_GIT:
                keys.add("git")
        elif first in ASK_ALWAYS:
            keys.add("gradle" if first.startswith("gradle") else first)
        elif first in INSTALL_SUBS:
            sub = next((t for t in tokens[1:] if not t.startswith("-")), "")
            if sub in INSTALL_SUBS[first]:
                keys.add(first)
    return ("ask", sorted(keys)) if keys else ("safe", None)


READ_ONLY_CMDS = {"ls", "cat", "pwd", "head", "tail", "wc", "grep", "egrep", "fgrep", "rg", "find", "which",
                  "whoami", "date", "uname", "tree", "stat", "file", "du", "df", "sort", "uniq", "cut", "diff",
                  "cd", "echo", "printenv", "id", "basename", "dirname", "realpath", "true", "test", "[", "less"}
GIT_READ = {"status", "log", "diff", "show", "branch", "remote", "rev-parse", "ls-files", "blame", "describe"}


def _segments(cmd):
    cleaned = re.sub(r"\d*>&\d+", "", strip_heredocs(cmd))
    for seg in re.split(r"\|\||&&|;|\||\n|&", cleaned):
        seg = seg.strip()
        if not seg:
            continue
        try:
            tokens = shlex.split(seg)
        except ValueError:
            tokens = seg.split()
        while tokens and re.match(r"^\w+=", tokens[0]):
            tokens.pop(0)
        if tokens:
            yield tokens


def command_names(cmd):
    """First word of every command in a shell line (used for 'always allow' in ask mode)."""
    return sorted({os.path.basename(t[0]) for t in _segments(cmd)}) or ["shell"]


def is_read_only(cmd):
    """True for pure look-but-don't-touch commands (used by the strict 'ask' mode)."""
    if re.search(r">|`|\$\(", re.sub(r"\d*>&\d+|\d*>>?\s*/dev/null", "", strip_heredocs(cmd))):
        return False
    for tokens in _segments(cmd):
        first = os.path.basename(tokens[0])
        if first == "git":
            sub = next((t for t in tokens[1:] if not t.startswith("-")), "")
            if sub not in GIT_READ:
                return False
        elif first not in READ_ONLY_CMDS:
            return False
        elif first == "find" and any(t in ("-delete", "-exec", "-execdir", "-ok") for t in tokens):
            return False
    return True


MODES = {
    "auto": "Default. Files and normal commands run freely; only gradle, git writes and installs ask.",
    "ask": "Strict. Asks before every file write and every command except read-only ones.",
    "yolo": "Never asks (only truly dangerous commands still need a typed 'yes').",
}


def ask_choice(message, keys, default):
    """One keypress answer (no Enter needed). Returns the mapped value; Esc/Ctrl+C -> 'n'."""
    kb = KeyBindings()

    def bind(key, val):
        @kb.add(key, eager=True)
        def _(event, v=val):
            event.app.exit(result=v)
    for k, v in keys.items():
        bind(k, v)
    bind("enter", default)
    bind("escape", "n")

    @kb.add("<any>")
    def _(event):
        pass   # ignore other keys
    try:
        return pt_prompt(message, key_bindings=kb)
    except (KeyboardInterrupt, EOFError):
        return "n"


def extract_text_tool_calls(text, names):
    """Find tool calls a model wrote as TEXT: <tool_call>{..}</tool_call>, ```json {..}``` blocks,
    or a bare JSON object. Returns ([(name, args)], text_without_the_calls)."""
    dec = json.JSONDecoder()
    found, spans = [], []

    def to_call(d):
        if not isinstance(d, dict):
            return None
        name = d.get("name") or d.get("tool") or d.get("tool_name") or d.get("function")
        args = d.get("arguments", d.get("args", d.get("parameters", d.get("input", {}))))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                return None
        return (name, args) if name in names and isinstance(args, dict) else None

    def try_span(raw, start, end):
        try:
            d, _ = dec.raw_decode(raw.lstrip())
        except (json.JSONDecodeError, ValueError):
            return
        c = to_call(d)
        if c and not any(s <= start < e for s, e in spans):
            found.append((start, c))
            spans.append((start, end))

    for m in re.finditer(r"<tool_call>\s*(.*?)\s*(?:</tool_call>|$)", text, re.S):
        try_span(m.group(1), m.start(), m.end())
    for m in re.finditer(r"```(?:json|tool|tool_call|tool_code)?[ \t]*\n(.*?)```", text, re.S):
        try_span(m.group(1), m.start(), m.end())
    if not found and text.strip().startswith("{"):
        try_span(text.strip(), 0, len(text))
    found.sort(key=lambda x: x[0])
    clean = text
    for s, e in sorted(spans, reverse=True):
        clean = clean[:s] + clean[e:]
    return [c for _, c in found], clean.strip()


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------
class Tool:
    def __init__(self, name, description, parameters, func, perm="safe", preview=None):
        self.name, self.description, self.parameters, self.func = name, description, parameters, func
        if isinstance(perm, str):
            lvl = perm
            perm = lambda a, lvl=lvl, n=name: (lvl, [n] if lvl == "ask" else None, "")
        self.perm = perm
        self.preview = preview

    def schema(self):
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.parameters}}


def truncate(s, n=MAX_OUT):
    if len(s) <= n:
        return s
    h = int(n * 0.6)
    return s[:h] + f"\n... [{len(s) - n} chars truncated] ...\n" + s[-(n - h):]


def resolve(p) -> Path:
    p = Path(os.path.expanduser(str(p)))
    return p if p.is_absolute() else Path(os.getcwd()) / p


def inside_cwd(p: Path) -> bool:
    try:
        p.resolve().relative_to(Path(os.getcwd()).resolve())
        return True
    except ValueError:
        return False


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(os.getcwd()))
    except ValueError:
        return str(p)


SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".cache"}


def iter_files(root):
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            yield Path(dp) / f


def kill_proc(p):
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


PWD_MARK = "__MIVO_PWD__"


def t_bash(a):
    """Run a command. `cd` persists between calls; stdout goes to a temp file so a background
    process (npm start &) can never block us."""
    import tempfile
    cmd = a["command"]
    timeout = int(a.get("timeout", 120))
    sh = shutil.which("bash") or "/bin/sh"
    wrapped = f'{cmd}\n__mivo_rc=$?\nprintf "\\n{PWD_MARK}%s" "$PWD"\nexit $__mivo_rc'
    timed_out = False
    with tempfile.TemporaryFile() as tf:
        p = subprocess.Popen([sh, "-c", wrapped], cwd=os.getcwd(), stdin=subprocess.DEVNULL,
                             stdout=tf, stderr=subprocess.STDOUT, start_new_session=True)
        ACTIVE_PROCS.add(p)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_proc(p)
            p.wait()
            timed_out = True
        except KeyboardInterrupt:
            kill_proc(p)
            p.wait()
            raise
        ACTIVE_PROCS.discard(p)
        tf.seek(0)
        out = tf.read().decode("utf-8", "replace")
    note = ""
    i = out.rfind(PWD_MARK)
    if i != -1:
        newdir = out[i + len(PWD_MARK):].strip().splitlines()[0] if out[i + len(PWD_MARK):].strip() else ""
        out = out[:i].rstrip("\n")
        if newdir and os.path.isdir(newdir) and os.path.realpath(newdir) != os.path.realpath(os.getcwd()):
            try:
                os.chdir(newdir)
                note = f"\n[working directory is now {newdir}]"
            except OSError:
                pass
    out = truncate(out, 60000).rstrip() or "(no output)"
    if timed_out:
        out += f"\n[timed out after {timeout}s and was stopped]"
    elif p.returncode:
        out += f"\n[exit code {p.returncode}]"
    return out + note


def t_read_file(a):
    p = resolve(a["path"])
    if not p.exists():
        near = []
        if p.parent.is_dir():
            near = difflib.get_close_matches(p.name, [x.name for x in p.parent.iterdir()], n=3, cutoff=0.5)
        hint = f" Did you mean: {', '.join(near)}?" if near else (
            "" if p.parent.is_dir() else f" (folder {p.parent} does not exist; use list_dir or glob)")
        return f"Error: {p} does not exist.{hint}"
    if p.is_dir():
        return f"Error: {p} is a directory (use list_dir)"
    try:
        text = p.read_text("utf-8")
    except UnicodeDecodeError:
        return "Error: binary or non-UTF-8 file"
    if a.get("outline"):
        return outline_text(p, text)
    lines = text.splitlines()
    off = max(int(a.get("offset", 1)), 1)
    lim = int(a.get("limit", 400))
    chunk = lines[off - 1: off - 1 + lim]
    out = "\n".join(f"{i:>6}\t{l}" for i, l in enumerate(chunk, start=off))
    rest = len(lines) - (off - 1 + lim)
    if rest > 0:
        out += f"\n... [{rest} more lines, use offset]"
    return truncate(out) if out else "(empty file)"


def t_write_file(a):
    p = resolve(a["path"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(a["content"], "utf-8")
    chk = check_syntax(p)
    return f"Wrote {len(a['content'].splitlines())} lines to {p}" + (f"\n{chk}" if chk else "")


def _apply_edit(a):
    p = resolve(a["path"])
    if not p.is_file():
        return p, "", "", f"Error: {p} does not exist"
    old = p.read_text("utf-8")
    s = a["old_string"]
    if not s:
        return p, old, old, "Error: old_string is empty"
    n = old.count(s)
    if n == 0:
        first = s.strip().splitlines()[0] if s.strip() else ""
        near = difflib.get_close_matches(first, [l.strip() for l in old.splitlines()], n=3, cutoff=0.5)
        hint = ("\nSimilar lines in the file: " + " | ".join(near)) if near else ""
        return p, old, old, ("Error: old_string not found in the file (it may have changed: use read_file and "
                             "copy the exact text)." + hint)
    if n > 1 and not a.get("replace_all"):
        return p, old, old, f"Error: old_string found {n} times; add more context or set replace_all"
    new = old.replace(s, a["new_string"]) if a.get("replace_all") else old.replace(s, a["new_string"], 1)
    return p, old, new, None


def t_edit_file(a):
    p, old, new, err = _apply_edit(a)
    if err:
        return err
    p.write_text(new, "utf-8")
    chk = check_syntax(p)
    return f"Edited {p}" + (f"\n{chk}" if chk else "")


def make_diff(old, new, name):
    d = list(difflib.unified_diff(old.splitlines(), new.splitlines(), f"a/{name}", f"b/{name}",
                                  lineterm="", n=2))
    t = Text()
    for line in d[:80]:
        if line.startswith(("+++", "---")):
            style = "bold"
        elif line.startswith("+"):
            style = "green"
        elif line.startswith("-"):
            style = "red"
        elif line.startswith("@@"):
            style = "cyan"
        else:
            style = "dim"
        t.append(line + "\n", style=style)
    if len(d) > 80:
        t.append(f"... {len(d) - 80} more diff lines", style="dim")
    return t if d else Text("(no changes)", style="dim")


def preview_write(a):
    p = resolve(a["path"])
    old = p.read_text("utf-8") if p.is_file() else ""
    label = "new file" if not p.exists() else "overwrite"
    return f"Write {rel(p)} ({label})", make_diff(old, a["content"], p.name)


def preview_edit(a):
    p, old, new, err = _apply_edit(a)
    if err:
        return f"Edit {rel(p)}", Text(err, style="red")
    return f"Edit {rel(p)}", make_diff(old, new, p.name)


def perm_write(a):
    p = resolve(a.get("path", ""))
    if path_ok_to_write(p):
        return "safe", None, ""
    return "ask", None, "system or protected location"


def t_list_dir(a):
    p = resolve(a.get("path", "."))
    if not p.is_dir():
        return f"Error: {p} is not a directory"
    items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    out = []
    for x in items[:500]:
        if x.is_dir():
            out.append(x.name + "/")
        else:
            try:
                out.append(f"{x.name}  ({x.stat().st_size} B)")
            except OSError:
                out.append(x.name)
    return "\n".join(out) or "(empty directory)"


def t_grep(a):
    try:
        rx = re.compile(a["pattern"], re.I if a.get("ignore_case") else 0)
    except re.error as e:
        return f"Error: bad regex: {e}"
    root = resolve(a.get("path", "."))
    inc = a.get("include")
    res = []
    files = [root] if root.is_file() else iter_files(root)
    for f in files:
        if inc and not fnmatch.fnmatch(f.name, inc):
            continue
        try:
            if f.stat().st_size > 2_000_000:
                continue
            with open(f, "r", encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    if rx.search(line):
                        res.append(f"{rel(f)}:{n}:{line.rstrip()[:300]}")
                        if len(res) >= 100:
                            return "\n".join(res) + "\n... [limit 100 matches: narrow the pattern or path]"
        except (UnicodeDecodeError, OSError):
            continue
    return "\n".join(res) or "No matches"


def t_glob(a):
    base = Path(os.getcwd())
    out = []
    for p in sorted(base.glob(a["pattern"])):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.append(rel(p) + ("/" if p.is_dir() else ""))
        if len(out) >= 300:
            out.append("... [limit 300]")
            break
    return "\n".join(out) or "No matches"


RUNNABLE_EXT = {".py", ".js", ".mjs", ".sh"}
ARG_ALIASES = {
    "path": ["file_path", "filepath", "filename", "file", "dir", "directory"],
    "content": ["text", "contents", "code", "data", "body"],
    "old_string": ["old", "old_str", "oldString", "find", "search"],
    "new_string": ["new", "new_str", "newString", "replace", "replacement"],
    "command": ["cmd", "script", "shell"],
    "pattern": ["regex", "query"],
}


def normalize_args(tool, args):
    """Accept the usual wrong argument names weak models use (file_path -> path, cmd -> command...)."""
    props = tool.parameters.get("properties", {})
    out = dict(args)
    for canon, alts in ARG_ALIASES.items():
        if canon in props and canon not in out:
            for alt in alts:
                if alt in out and alt not in props:
                    out[canon] = out.pop(alt)
                    break
    return out


def check_syntax(p: Path) -> str:
    """Instant feedback after a write: the model sees a syntax error without running anything."""
    ext = p.suffix.lower()
    try:
        if ext == ".py":
            import ast
            ast.parse(p.read_text("utf-8"), str(p))
        elif ext == ".json":
            json.loads(p.read_text("utf-8"))
        elif ext in (".js", ".mjs", ".cjs") and shutil.which("node"):
            r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True, timeout=15)
            if r.returncode:
                return "⚠ JavaScript syntax error: " + " ".join((r.stderr or "").split())[:300]
        elif ext == ".sh" and shutil.which("bash"):
            r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True, timeout=10)
            if r.returncode:
                return "⚠ shell syntax error: " + " ".join((r.stderr or "").split())[:300]
        else:
            return ""
    except SyntaxError as e:
        return f"⚠ SyntaxError line {e.lineno}: {e.msg} (fix it now)"
    except json.JSONDecodeError as e:
        return f"⚠ Invalid JSON line {e.lineno}: {e.msg} (fix it now)"
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    return "✓ syntax ok"


def _apply_multi(a):
    p = resolve(a["path"])
    if not p.is_file():
        return p, "", "", f"Error: {p} does not exist"
    old = text = p.read_text("utf-8")
    edits = a.get("edits")
    if not isinstance(edits, list) or not edits:
        return p, old, old, 'Error: "edits" must be a non-empty list of {"old_string", "new_string"}'
    for i, e in enumerate(edits, 1):
        s = (e or {}).get("old_string", "")
        n = text.count(s) if s else 0
        if n == 0:
            return p, old, old, f"Error in edit #{i}: old_string not found (nothing was changed). Use read_file and copy the exact text."
        if n > 1 and not e.get("replace_all"):
            return p, old, old, f"Error in edit #{i}: old_string found {n} times; add context (nothing was changed)."
        text = text.replace(s, e.get("new_string", "")) if e.get("replace_all") else text.replace(s, e.get("new_string", ""), 1)
    return p, old, text, None


def t_multi_edit(a):
    p, old, new, err = _apply_multi(a)
    if err:
        return err
    p.write_text(new, "utf-8")
    chk = check_syntax(p)
    return f"Edited {p} ({len(a['edits'])} changes)" + (f"\n{chk}" if chk else "")


def preview_multi(a):
    p, old, new, err = _apply_multi(a)
    if err:
        return f"Edit {rel(p)}", Text(err, style="red")
    return f"Edit {rel(p)} ({len(a['edits'])} changes)", make_diff(old, new, p.name)


def perm_bash(a):
    level, keys = classify_command(a.get("command", ""))
    return level, keys, ""


def obj(props, required):
    return {"type": "object", "properties": props, "required": required}


def core_tools():
    S = lambda d: {"type": "string", "description": d}
    return [
        Tool("bash", "Run a shell command in the working directory (Termux/bash). Output is returned.",
             obj({"command": S("Command to run"),
                  "timeout": {"type": "integer", "description": "Seconds (default 120)"},
                  "raw": {"type": "boolean", "description": "Skip output compaction (rarely needed)"}}, ["command"]),
             t_bash, perm_bash, lambda a: ("Run command", Text(a.get("command", "")))),
        Tool("read_file", "Read a text file with line numbers (default 400 lines; use offset/limit for more).",
             obj({"path": S("File path"), "offset": {"type": "integer", "description": "Start line (1-based)"},
                  "limit": {"type": "integer", "description": "Max lines"},
                  "outline": {"type": "boolean", "description": "Signatures only: see a file's shape cheaply"}},
                 ["path"]), t_read_file),
        Tool("write_file", "Create or overwrite a file (parent folders are created automatically). Put \"path\" BEFORE \"content\". Saved live while you write.",
             obj({"path": S("File path"), "content": S("Full file content")}, ["path", "content"]),
             t_write_file, perm_write, preview_write),
        Tool("edit_file", "Replace an exact string in a file. old_string must be unique unless replace_all.",
             obj({"path": S("File path"), "old_string": S("Exact text to replace"),
                  "new_string": S("Replacement text"), "replace_all": {"type": "boolean"}},
                 ["path", "old_string", "new_string"]), t_edit_file, perm_write, preview_edit),
        Tool("multi_edit", "Apply several exact replacements to ONE file in a single call (each old_string must "
                           "match once). Cheaper and faster than many edit_file calls.",
             obj({"path": S("File path"), "edits": {"type": "array", "items": obj(
                 {"old_string": S("Exact text"), "new_string": S("Replacement"),
                  "replace_all": {"type": "boolean"}}, ["old_string", "new_string"])}},
                 ["path", "edits"]), t_multi_edit, perm_write, preview_multi),
        Tool("list_dir", "List files in a directory.", obj({"path": S("Directory (default .)")}, []), t_list_dir),
        Tool("grep", "Regex search in files (skips .git, node_modules, etc.).",
             obj({"pattern": S("Regex"), "path": S("File or dir (default .)"),
                  "include": S("Filename glob, e.g. *.py"), "ignore_case": {"type": "boolean"}}, ["pattern"]),
             t_grep),
        Tool("glob", "Find files by glob pattern relative to the working directory, e.g. **/*.py.",
             obj({"pattern": S("Glob pattern")}, ["pattern"]), t_glob),
    ]


# --------------------------------------------------------------------------
# Skills & plugins
# --------------------------------------------------------------------------
def parse_frontmatter(text):
    meta, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip("\"'")
            body = text[end + 4:].lstrip("\n")
    return meta, body


DEFAULT_TRIGGERS = {
    "tool-playbook": ["*"], "android-app": ["android", "aide", "apk", "kotlin", "manifest", "activity"],
    "termux-env": ["termux", "pkg", "storage", "sdcard"], "git-workflow": ["git", "commit", "branch", "merge", "github"],
    "debugging": ["error", "bug", "crash", "fix", "fail", "failing", "exception", "traceback", "broken"],
    "code-review": ["review", "audit"], "project-scaffold": ["scaffold", "bootstrap", "starter", "template"],
    "write-tests": ["test", "tests", "pytest", "coverage", "unittest"], "python-best-practices": ["python", "pip"],
    "javascript-node": ["javascript", "node", "npm", "typescript"],
    "web-frontend": ["html", "css", "website", "landing", "frontend"], "bash-scripting": ["bash", "shell"],
    "sqlite-database": ["sql", "sqlite", "database", "query"],
    "rest-api": ["api", "rest", "endpoint", "flask", "fastapi", "server"],
    "security-checklist": ["security", "secure", "vulnerability", "password", "login"],
    "error-handling": ["exception", "logging", "retry"], "refactoring": ["refactor", "cleanup", "simplify"],
    "documentation": ["readme", "docs", "documentation"], "performance": ["slow", "performance", "optimize"],
}


def load_skills():
    skills = {}
    for f in sorted(SKILL_DIR.glob("*/SKILL.md")):
        try:
            meta, body = parse_frontmatter(f.read_text("utf-8"))
        except OSError:
            continue
        name = meta.get("name") or f.parent.name
        triggers = [t.strip().lower() for t in meta.get("triggers", "").split(",") if t.strip()]
        triggers = triggers or DEFAULT_TRIGGERS.get(name, [])   # older installed skills have no triggers line
        skills[name] = {"description": meta.get("description", ""), "body": body, "path": f,
                        "triggers": triggers}
    return skills


class PluginAPI:
    """Passed to a plugin's register(api)."""

    def __init__(self, agent, name):
        self.agent, self.plugin_name, self.console = agent, name, console

    def tool(self, name, description, parameters, func, permission="ask", preview=None):
        """func(args: dict) -> str. permission: 'safe', 'ask' or callable(args)->'safe'|'ask'."""
        if callable(permission):
            fn = permission
            perm = lambda a, n=name, fn=fn: (fn(a), [n], "")
        else:
            perm = permission
        self.agent.tools[name] = Tool(name, description, parameters, func, perm, preview)

    def command(self, name, func, help=""):
        """func(arg: str) -> None."""
        self.agent.commands[name.lstrip("/")] = (lambda arg, f=func: f(arg), help)

    def cwd(self):
        return os.getcwd()

    @property
    def state(self):
        return self.agent.state


# --------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Project memory: live project map + notes
# --------------------------------------------------------------------------
_JS = re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\*?\s+|class\s+)(\w+)"
                 r"|^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>", re.M)
_JVM = re.compile(r"\b(?:class|interface|object|fun|func|enum)\s+(\w+)")
SYMBOL_RX = {
    "py": re.compile(r"^(?:async\s+)?(?:def|class)\s+(\w+)", re.M),
    "js": _JS, "jsx": _JS, "ts": _JS, "tsx": _JS, "mjs": _JS,
    "kt": _JVM, "java": _JVM, "dart": _JVM, "swift": _JVM,
    "go": re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)|^type\s+(\w+)", re.M),
    "rs": re.compile(r"^\s*(?:pub\s+)?(?:fn|struct|enum|trait)\s+(\w+)", re.M),
    "rb": re.compile(r"^\s*(?:def|class|module)\s+(\w+)", re.M),
    "php": re.compile(r"\b(?:function|class)\s+(\w+)"),
    "sh": re.compile(r"^(?:function\s+)?(\w+)\s*\(\)", re.M),
}
MAP_EXT = set(SYMBOL_RX) | {"html", "css", "json", "md", "txt", "yml", "yaml", "toml", "xml", "gradle",
                            "kts", "sql", "ini", "cfg", "c", "cpp", "h", "hpp", "vue", "svelte"}


def project_map(root, max_chars=5000, time_budget=0.4, hint="", focus=()):
    """Compact map of the project as it is on disk right now. Files you just changed or that the
    request mentions get full symbol lists; the rest are shorter, so big projects cost few tokens."""
    start, entries, cut = time.time(), [], False
    root, hint, focus = str(root), hint.lower(), set(focus)
    for dp, dn, fn in os.walk(root):
        depth = dp[len(root):].count(os.sep)
        dn[:] = sorted(d for d in dn if d not in SKIP_DIRS and not d.startswith(".")) if depth < 6 else []
        for f in sorted(fn):
            ext = f.rsplit(".", 1)[-1].lower() if "." in f else ""
            if f.startswith(".") or (ext not in MAP_EXT and f not in ("Makefile", "Dockerfile", "gradlew")):
                continue
            if time.time() - start > time_budget or len(entries) >= 600:
                cut = True
                break
            p = Path(dp) / f
            relp = os.path.relpath(p, root)
            try:
                if p.stat().st_size > 300_000:
                    entries.append((relp, None, []))
                    continue
                text = p.read_text("utf-8", "replace")
            except OSError:
                continue
            syms, rx = [], SYMBOL_RX.get(ext)
            if rx:
                for m in rx.findall(text):
                    s = m if isinstance(m, str) else next((x for x in m if x), "")
                    if s and s not in syms:
                        syms.append(s)
            entries.append((relp, text.count("\n") + 1, syms))
        if cut:
            break
    if not entries:
        return "(no source files yet)"
    n = len(entries)

    def is_focus(rp):
        b = os.path.basename(rp).lower()
        return rp in focus or (len(b) > 3 and b in hint)
    base_syms = 8 if n <= 40 else 3 if n <= 120 else 0
    ordered = [e for e in entries if is_focus(e[0])] + [e for e in entries if not is_focus(e[0])]
    out, size = [], 0
    for relp, nl, syms in ordered:
        k = 12 if is_focus(relp) else base_syms
        entry = relp + (f" ({nl}L)" if nl is not None else " (large file)")
        if syms and k:
            entry += ": " + ", ".join(syms[:k]) + (" ..." if len(syms) > k else "")
        if size + len(entry) > max_chars:
            out.append(f"... ({n - len(out)} more files; use list_dir/glob)")
            break
        out.append(entry)
        size += len(entry) + 1
    return "\n".join(out) + ("\n... (more files exist)" if cut else "")


def project_dir() -> Path:
    import hashlib
    key = hashlib.sha1(os.path.realpath(os.getcwd()).encode()).hexdigest()[:12]
    d = MIVO_HOME / "projects" / key
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_notes() -> str:
    f = project_dir() / "notes.md"
    try:
        return f.read_text("utf-8").strip() if f.exists() else ""
    except OSError:
        return ""


def t_remember(a):
    note = " ".join(str(a["note"]).split())
    if not note:
        return "Error: empty note"
    f = project_dir() / "notes.md"
    lines = (read_notes().splitlines() if f.exists() else []) + [f"- {note}"]
    while sum(len(l) + 1 for l in lines) > 6000 and len(lines) > 1:
        lines.pop(0)   # keep the newest notes
    f.write_text("\n".join(lines) + "\n", "utf-8")
    return "Saved to project notes."


# --------------------------------------------------------------------------
# Web search (/addweb): a browsing-capable, OpenAI-compatible model does the searching
# --------------------------------------------------------------------------
def web_search_run(ws, query):
    base = normalize_base_url(ws["base_url"], "openai")
    headers = {"Content-Type": "application/json"}
    if ws.get("api_key"):
        headers["Authorization"] = f"Bearer {ws['api_key']}"
    body = {"model": ws["model"], "stream": False, "messages": [
        {"role": "system", "content": "You are a web search assistant. Search the web, answer concisely "
                                      "with current and accurate facts, and include source URLs."},
        {"role": "user", "content": query}]}
    r = requests.post(base + "/chat/completions", headers=headers, json=body, timeout=(15, 180))
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    d = r.json()
    msg = (d.get("choices") or [{}])[0].get("message", {}) or {}
    text = (msg.get("content") or "").strip()
    urls = [u if isinstance(u, str) else (u or {}).get("url", "") for u in (d.get("citations") or [])]
    urls += [(i or {}).get("url", "") for i in (d.get("search_results") or [])]
    urls += [((a or {}).get("url_citation") or {}).get("url", "") for a in (msg.get("annotations") or [])]
    seen = []
    for u in urls:
        if u and u not in seen:
            seen.append(u)
    if seen:
        text += "\n\nSources:\n" + "\n".join(f"- {u}" for u in seen[:8])
    return text or "No results."


READ_ONLY = {"read_file", "list_dir", "grep", "glob", "use_skill", "remember", "todo_write",
             "web_search", "web_fetch", "recall", "lib_docs", "lib_search"}
C7_RULE = ("DOCS: before using a library or framework API you are not 100% sure about, use the Context7 docs tools "
           "(resolve-library-id then query-docs, or lib_docs) to get current, version-specific docs instead of "
           "guessing from memory. A library id such as /vercel/next.js skips the search.")
RTK_RULE = ("Long command output is compacted automatically to save tokens (marked [rtk: ...]). If you need the full "
            "raw output, call recall {id} (optionally with grep) instead of running the command again.")


def read_multiline(title):
    """Read pasted or typed text until a line that is exactly /done. Returns None on /cancel."""
    console.print(f"[dim]{title}\nType or paste, then finish with a line containing only /done (or /cancel).[/]")
    lines = []
    while True:
        try:
            line = input("› ")
        except (EOFError, KeyboardInterrupt):
            return None
        if line.strip() == "/cancel":
            return None
        if line.strip() == "/done":
            return "\n".join(lines).strip()
        lines.append(line)


def strip_think(text):
    """Thinking text is shown but never stored or sent back: it costs tokens and adds nothing."""
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.S)
    if "<think>" in text:
        text = re.sub(r"<think>.*\Z", "", text, flags=re.S)
    return text.strip()


def est_tokens(msgs):
    return sum(len(json.dumps(m, ensure_ascii=False)) for m in msgs) // 3


VERIFY_MSG = ("[MIVO] You wrote or changed runnable code but have not run or tested it yet. Run it now (or its "
              "tests) with bash and fix anything that fails, then give the final result. If it genuinely cannot "
              "be run here, say so in one line.")
LOOP_MSG = ("Blocked: you already made this exact call twice in a row. Change your approach: re-read the error, "
            "edit the code, or try a different command.")
THINK_ERR_RX = (r"reason|thinking|effort|budget|unknown (field|param)|unrecognized|unsupported|extra inputs|"
                r"not permitted|invalid (param|field)")


# --------------------------------------------------------------------------
# RTK-style output compaction (built in; the real `rtk` binary is used too when installed)
# Idea: https://github.com/rtk-ai/rtk - cut the noise of command output before the model reads it.
# --------------------------------------------------------------------------
ANSI_RX = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
NOISE_RX = re.compile(
    r"^\s*(?:\d{1,3}%\s|[#=>\-\.\s]{14,}$|Receiving objects|Resolving deltas|Counting objects|Compressing objects|"
    r"Writing objects|Enumerating objects|Delta compression|Total \d+ \(delta|remote: (?:Counting|Compressing|Total|"
    r"Enumerating)|Downloading |Collecting |Using cached |Requirement already satisfied|Get:\d+ |Hit:\d+ |Ign:\d+ |"
    r"Fetched \d|Reading package lists|Building dependency tree|Reading state information|Unpacking |"
    r"Selecting previously|Preparing to unpack|Setting up |Processing triggers|npm (?:warn deprecated|http fetch)|"
    r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏])", re.I)
RX_INSTALL = re.compile(r"\b(pip3?|npm|yarn|pnpm|bun|apt(?:-get)?|pkg|cargo|gem|composer|go)\s+(install|i|add|update|"
                        r"upgrade|get|ci|build|fetch)\b|\bpython3?\s+-m\s+pip\b")
RX_GITNET = re.compile(r"\bgit\s+(push|pull|fetch|clone)\b")
RX_TEST = re.compile(r"\b(pytest|py\.test|jest|vitest|mocha|phpunit|rspec|unittest|cargo\s+test|go\s+test|"
                     r"npm\s+(run\s+)?test|yarn\s+test|pnpm\s+(run\s+)?test|gradlew?\s+test|mvn\s+test)\b")
RX_GREP = re.compile(r"(^|[|;&]\s*)(grep|rg|ag|find)\b")
RX_LS = re.compile(r"^\s*(ls|tree)\b")
SUMMARY_RX = re.compile(r"(\d+\s+(passed|failed|skipped|errors?|warnings?)|tests?\s+(run|passed|failed)|Ran \d+|"
                        r"test result|\bPASS\b|\bOK\b|Tests:|Test Suites:|^Time:|^=+ .* =+$)", re.I)
FAIL_RX = re.compile(r"(FAIL|ERROR|Error|error:|assert|Assertion|Traceback|panic|Exception|✗|✖|Expected|Received|"
                     r"^E\s{2,}|failed)")


def _dedupe(lines):
    out, prev, n = [], None, 0
    for l in lines + [None]:
        if l is not None and l == prev:
            n += 1
            continue
        if prev is not None:
            out.append(prev if (n == 1 or not prev.strip()) else f"{prev}  (×{n})")
        prev, n = l, 1
    return out


def _compact_tests(lines, rc):
    if len(lines) <= 40:
        return lines
    if rc == 0:   # everything passed: header + summary lines + tail
        keep = lines[:2] + [l for l in lines if SUMMARY_RX.search(l)][:15] + lines[-5:]
    else:         # failures: the windows around failure markers + the tail
        idx = {i for i, l in enumerate(lines) if FAIL_RX.search(l)}
        win = sorted({j for i in idx for j in range(max(i - 2, 0), min(i + 3, len(lines)))})
        keep = [lines[j] for j in win][:150] + ["..."] + lines[-12:]
    seen, out = set(), []
    for l in keep:
        if l not in seen or l == "...":
            seen.add(l)
            out.append(l)
    return out


def _compact_grep(lines):
    if len(lines) <= 40:
        return lines
    groups, order, loose = {}, [], []
    for l in lines:
        m = re.match(r"^([^\s:]+):(\d+):(.*)$", l)
        if m:
            if m.group(1) not in groups:
                groups[m.group(1)] = []
                order.append(m.group(1))
            groups[m.group(1)].append(l)
        else:
            loose.append(l)
    if not groups:   # plain list of paths
        return loose[:50] + ([f"... +{len(loose) - 50} more"] if len(loose) > 50 else [])
    out = []
    for f in order[:25]:
        out += groups[f][:3]
        if len(groups[f]) > 3:
            out.append(f"  ... +{len(groups[f]) - 3} more in {f}")
    if len(order) > 25:
        out.append(f"... +{len(order) - 25} more files")
    return out + loose[:5]


def _git_log_oneline(lines):
    out, h = [], None
    for l in lines:
        if l.startswith("commit "):
            h = l.split()[1][:7]
        elif l.startswith("    ") and h:
            out.append(f"{h} {l.strip()}")
            h = None
    return out or lines


def rtk_compact(cmd, text, rc=0):
    """Shrink command output without hiding what matters: noise, duplicates, passing tests, grep floods."""
    lines = [ANSI_RX.sub("", l).split("\r")[-1] for l in text.split("\n")]
    if RX_INSTALL.search(cmd) or RX_GITNET.search(cmd):
        lines = [l for l in lines if not NOISE_RX.match(l)]
    if re.search(r"\bgit\s+status\b", cmd):
        lines = [l for l in lines if not l.strip().startswith('(use "git')]
    if re.search(r"\bgit\s+(diff|show)\b", cmd):
        lines = [l for l in lines if not l.startswith(("index ", "\\ No newline"))]
    if re.search(r"\bgit\s+log\b", cmd) and text.startswith("commit ") and len(lines) > 30:
        lines = _git_log_oneline(lines)
    lines = _dedupe(lines)
    if RX_TEST.search(cmd):
        lines = _compact_tests(lines, rc)
    elif RX_GREP.search(cmd):
        lines = _compact_grep(lines)
    elif RX_LS.search(cmd) and len(lines) > 60:
        lines = lines[:50] + [f"... {len(lines) - 50} more entries"]
    lines = [(l[:240] + f"…[+{len(l) - 240}]") if len(l) > 240 else l.rstrip() for l in lines]
    out = []
    for l in lines:   # collapse runs of blank lines
        if not l.strip() and out and not out[-1].strip():
            continue
        out.append(l)
    return "\n".join(out).strip("\n")


def split_trailer(out):
    lines, trail = out.split("\n"), []
    while lines and re.match(r"^\[(exit code|working directory|timed out)", lines[-1]):
        trail.insert(0, lines.pop())
    return "\n".join(lines), trail


RTK_SIMPLE = {"git": {"status", "log", "diff", "add", "commit", "push", "pull"}, "cargo": {"test", "build", "clippy"},
              "go": {"test"}, "docker": {"ps", "images"}, "pip": {"list", "outdated"}, "pip3": {"list", "outdated"}}
RTK_DIRECT = {"pytest", "jest", "vitest", "tsc"}
_RTK_OK = {}


def rtk_binary():
    """Path of the genuine rtk (Rust Token Killer) binary, or None. Another tool is also called rtk."""
    own = bin_dir() / "rtk"
    p = str(own) if own.is_file() else shutil.which("rtk")
    if not p:
        return None
    if p not in _RTK_OK:
        try:
            r = subprocess.run([p, "--help"], capture_output=True, text=True, timeout=5)
            txt = (r.stdout + r.stderr).lower()
            _RTK_OK[p] = ("gain" in txt and "git" in txt) or ("token" in txt and "rtk" in txt)
        except (OSError, subprocess.SubprocessError):
            _RTK_OK[p] = False
    return p if _RTK_OK[p] else None


def rtk_rewrite(cmd):
    """`git status` -> `rtk git status` for simple single commands (no pipes, redirects or chaining)."""
    if re.search(r"[|&;<>`$()\n]", cmd):
        return None
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return None
    if not tokens:
        return None
    first = os.path.basename(tokens[0])
    sub = tokens[1] if len(tokens) > 1 else ""
    if first in RTK_SIMPLE and sub in RTK_SIMPLE[first]:
        return "rtk " + shlex.join([first] + tokens[1:])
    if first in RTK_DIRECT or (first == "ruff" and sub == "check"):
        return "rtk " + shlex.join(tokens)
    if first in ("npm", "yarn", "pnpm") and sub == "test":
        return "rtk test " + shlex.join(tokens)
    return None


OUTLINE_RX = {
    "py": re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+\w+"),
    "js": re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\*?\s+\w+|class\s+\w+)|"
                     r"^\s*(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>"),
}
OUTLINE_RX.update({e: OUTLINE_RX["js"] for e in ("jsx", "ts", "tsx", "mjs")})
OUTLINE_GENERIC = re.compile(r"^\s*(?:pub\s+|public\s+|private\s+|protected\s+|static\s+|export\s+)*"
                             r"(?:class|interface|object|fun|func|def|fn|struct|enum|trait|function)\s+\w+")


def outline_text(p, text):
    """Signatures only (like `rtk read -l aggressive`): see a file's shape for a fraction of the tokens."""
    rx = OUTLINE_RX.get(p.suffix.lstrip(".").lower(), OUTLINE_GENERIC)
    lines = text.splitlines()
    out = [f"{i:>5}  {l.rstrip()[:130]}" for i, l in enumerate(lines, 1) if rx.search(l)][:250]
    head = f"{len(lines)} lines · outline only (read_file with offset/limit for bodies)"
    return head + ("\n" + "\n".join(out) if out else "\n(no definitions found; read the file normally)")


# --------------------------------------------------------------------------
# Ponytail (minimal-code persona) and Caveman (terse replies) - ideas from
# https://github.com/DietrichGebert/ponytail and https://github.com/JuliusBrussee/caveman
# --------------------------------------------------------------------------
PONYTAIL_RULES = {
    "lite": "PONYTAIL (lite): prefer the simplest solution. Avoid needless abstraction, extra files and speculative "
            "options. If the standard library or an installed dependency already does it, use that.",
    "full": ("PONYTAIL MODE (lazy senior developer: the best code is the code you do not write). Before writing ANY code "
             "ask, in order, and stop at the first yes: 1) Is it needed at all? If the user did not ask for it, do not "
             "build it. 2) Does the language standard library, the platform (browser, OS, shell) or an already "
             "installed dependency do it? Use that. 3) Can one line, one function or one existing file do it? Write "
             "exactly that. No speculative abstractions, no config nobody asked for, no wrapper classes for one use, "
             "no extra files, no future-proofing, no comments that restate code. Prefer deleting code to adding it. "
             "When a shortcut has a real limit, mark it in the code with a comment `ponytail: <what would need to "
             "change to upgrade it>`."),
    "ultra": ("PONYTAIL MODE (ultra): write the absolute minimum that works. One file if possible. A one-liner beats a "
              "function; a built-in beats a library; nothing beats not writing it. Refuse scope creep: do exactly "
              "what was asked. Delete dead code you touch. Mark every real shortcut with `ponytail: <upgrade path>`. "
              "Replies are one or two lines."),
}
PONYTAIL_REVIEW = ("Review the diff below as a ponytail (lazy senior dev) reviewer. Find what to DELETE or REPLACE: code "
                   "the standard library, the platform or an existing dependency already provides; abstractions used "
                   "once; speculative options and features nobody asked for; needless files. For each finding give "
                   "file:line, what to remove or replace, and the smaller version. Do not edit files. End with one "
                   "line: the verdict and roughly how many lines could go.")
PONYTAIL_AUDIT = ("Audit this whole project as a ponytail (lazy senior dev) reviewer using grep/read_file/glob. List the "
                  "top 10 over-engineering hotspots (needless abstractions, reinvented standard-library features, "
                  "dead code, speculative options), each with file:line and the simpler alternative. Do not edit "
                  "files; end with a one-line verdict.")
CAVEMAN_RULES = {
    "lite": "Reply tersely: no filler, pleasantries or hedging; keep full sentences and normal grammar.",
    "full": "Reply like a caveman: drop articles and filler, use short fragments and short words. Example: "
            "'Bug in auth middleware. Expiry check use < not <=. Fix:'",
    "ultra": "Maximum compression: telegraphic fragments, abbreviations (fn, cfg, req, res, impl, dep), arrows for "
             "cause and effect (X -> Y), no articles, no filler.",
    "wenyan": "Reply in terse classical-Chinese style (wenyan) where natural; keep technical terms and code exact.",
}
CAVEMAN_COMMON = ("This style applies ONLY to your prose. Code, commands, file paths, error messages and quoted text stay "
                  "exact. Keep the style every reply until the user says 'stop caveman' or 'normal mode'. Drop it for "
                  "security warnings, confirmations of irreversible actions and multi-step instructions where "
                  "fragments could be misread. Still reply in the user's language.")


# --------------------------------------------------------------------------
# Context7 (up-to-date library docs): https://github.com/upstash/context7 (REST API)
# --------------------------------------------------------------------------
C7_BASE = "https://context7.com/api/v2"
_C7_CACHE = {}


def _c7_get(path, params, key, text=False):
    h = {"Accept": "application/json", "User-Agent": "MIVO-CODE"}
    if key:
        h["Authorization"] = f"Bearer {key}"
    r = requests.get(C7_BASE + path, params=params, headers=h, timeout=25)
    if r.status_code in (401, 403):
        raise RuntimeError("Context7 rejected the API key. Set a valid one with /context7 key")
    if r.status_code == 429:
        raise RuntimeError("Context7 rate limit reached. A free API key raises it: /context7 key")
    if r.status_code != 200:
        raise RuntimeError(f"Context7 HTTP {r.status_code}: {r.text[:160]}")
    return r.text if text else r.json()


def c7_search(library, query, key):
    data = _c7_get("/libs/search", {"libraryName": library, "query": query or library}, key)
    res = data.get("results") if isinstance(data, dict) else data
    return res if isinstance(res, list) else []


def c7_lib_docs(library, query, key, library_id=None, max_chars=6000):
    """Resolve a library name to a Context7 id (unless given) and return its current docs for the query."""
    ck = (library_id or library, query, max_chars)
    if ck in _C7_CACHE:
        return _C7_CACHE[ck]
    note = ""
    if not library_id:
        res = c7_search(library, query, key)
        if not res:
            return f"No Context7 library found for '{library}'. Try another name or pass library_id like /org/project."
        library_id = res[0].get("id") or ""
        others = ", ".join(f"{r.get('id')}" for r in res[1:4] if r.get("id"))
        note = f"[Context7 library: {library_id} ({res[0].get('title') or res[0].get('name') or ''})" + \
               (f"; others: {others}" if others else "") + "]\n"
    doc = _c7_get("/context", {"libraryId": library_id, "query": query, "type": "txt"}, key, text=True).strip()
    if not doc:
        return note + "No documentation returned for that query. Try different words."
    if len(doc) > max_chars:
        doc = doc[:max_chars] + f"\n... [truncated; pass max_chars for more or narrow the query]"
    _C7_CACHE[ck] = note + doc
    return _C7_CACHE[ck]


# --------------------------------------------------------------------------
# MCP (Model Context Protocol) client: stdio and Streamable-HTTP servers become ordinary tools.
# Servers live in ~/.mivo/mcp.json ({"mcpServers": {...}}, same shape other agents use).
# Context7 is registered by default (remote, no Node.js needed).
# --------------------------------------------------------------------------
MCP_PROTOCOL = "2025-03-26"
MCP_DEFAULTS = {"context7": {"url": "https://mcp.context7.com/mcp", "trust": True}}


def mcp_config_path():
    return MIVO_HOME / "mcp.json"


def expand_env(v):
    if isinstance(v, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), v)
    if isinstance(v, list):
        return [expand_env(x) for x in v]
    if isinstance(v, dict):
        return {k: expand_env(x) for k, x in v.items()}
    return v


def read_mcp_file():
    try:
        d = json.loads(mcp_config_path().read_text("utf-8"))
        return d.get("mcpServers", {}) if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_mcp_file(servers):
    MIVO_HOME.mkdir(parents=True, exist_ok=True)
    mcp_config_path().write_text(json.dumps({"mcpServers": servers}, indent=2) + "\n", "utf-8")


def ensure_mcp_config():
    """First run: write the default servers so the file is visible and editable (like REA's setup does)."""
    if not mcp_config_path().exists():
        write_mcp_file({k: dict(v) for k, v in MCP_DEFAULTS.items()})


def load_mcp_servers(c7_key=""):
    """Built-in defaults overlaid with ~/.mivo/mcp.json. A user entry replaces the default of the same name."""
    servers = {k: dict(v) for k, v in MCP_DEFAULTS.items()}
    servers.update(read_mcp_file())
    out = {}
    for name, spec in servers.items():
        if not isinstance(spec, dict) or spec.get("disabled"):
            continue
        spec = dict(spec)
        if name == "context7" and spec.get("url") and c7_key:
            headers = dict(spec.get("headers") or {})
            if not any(k.lower() == "context7_api_key" for k in headers):
                headers["CONTEXT7_API_KEY"] = c7_key
            spec["headers"] = headers
        out[name] = spec
    return out


def mcp_tool_name(server, tool):
    name = re.sub(r"[^A-Za-z0-9_-]", "_", f"mcp__{server}__{tool}")
    if len(name) > 64:
        import hashlib
        name = name[:55] + "_" + hashlib.sha1(name.encode()).hexdigest()[:8]
    return name


def slim_schema(s, depth=0):
    """MCP schemas can be wordy: keep them, but cap descriptions so every request costs fewer tokens."""
    if isinstance(s, dict):
        out = {}
        for k, v in s.items():
            if k in ("$schema", "additionalProperties", "$id"):
                continue
            if k == "description" and isinstance(v, str):
                out[k] = v if len(v) <= 240 else v[:237] + "..."
            else:
                out[k] = slim_schema(v, depth + 1)
        return out
    if isinstance(s, list):
        return [slim_schema(x, depth + 1) for x in s]
    return s


class McpClient:
    def __init__(self, name, spec):
        self.name, self.spec = name, spec
        self.tools, self.status, self.error = [], "starting", ""
        self.proc, self.http, self.session_id, self.protocol = None, None, None, None
        self._id, self._lock, self._pending = 0, threading.Lock(), {}

    @property
    def kind(self):
        return "stdio" if "command" in self.spec else "http"

    @property
    def trusted(self):
        return bool(self.spec.get("trust"))

    # ---- lifecycle
    def connect(self, timeout=60):
        try:
            if self.kind == "stdio":
                self._start_stdio()
            elif self.spec.get("url"):
                self.http = requests.Session()
            else:
                raise RuntimeError("server needs a 'command' or a 'url'")
            res = self.request("initialize", {"protocolVersion": MCP_PROTOCOL, "capabilities": {},
                                              "clientInfo": {"name": "mivo-code", "version": VERSION}}, timeout)
            self.protocol = res.get("protocolVersion") or MCP_PROTOCOL
            self.notify("notifications/initialized")
            cursor, tools = None, []
            for _ in range(20):
                r = self.request("tools/list", {"cursor": cursor} if cursor else {}, timeout)
                tools += r.get("tools") or []
                cursor = r.get("nextCursor")
                if not cursor:
                    break
            self.tools, self.status = tools, "ready"
        except requests.RequestException:
            self.status, self.error = "failed", "cannot reach the server (offline?)"
            self.close()
        except Exception as e:
            self.status, self.error = "failed", str(e)[:200] or type(e).__name__
            self.close()

    def close(self):
        p, self.proc = self.proc, None
        if p:
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        if self.http:
            try:
                self.http.close()
            except Exception:
                pass

    # ---- stdio transport
    def _start_stdio(self):
        cmd = [expand_env(self.spec["command"])] + [expand_env(a) for a in self.spec.get("args", [])]
        if not shutil.which(cmd[0]):
            hint = " (install Node.js: Termux 'pkg install nodejs', Ubuntu 'apt install nodejs npm')" \
                if cmd[0] in ("npx", "node", "npm") else ""
            raise RuntimeError(f"'{cmd[0]}' not found{hint}")
        env = dict(os.environ)
        env.update(expand_env(self.spec.get("env") or {}))
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     env=env, cwd=self.spec.get("cwd") or os.getcwd())
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def _send(self, msg):
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        self.proc.stdin.flush()

    def _reader(self, proc):
        try:
            for raw in proc.stdout:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if "id" in msg and ("result" in msg or "error" in msg):
                    slot = self._pending.pop(msg["id"], None)
                    if slot:
                        slot["msg"] = msg
                        slot["ev"].set()
                elif "method" in msg and "id" in msg:   # the server asks us something
                    m = msg["method"]
                    if m == "ping":
                        reply = {"result": {}}
                    elif m == "roots/list":
                        reply = {"result": {"roots": [{"uri": "file://" + os.getcwd(), "name": "project"}]}}
                    else:
                        reply = {"error": {"code": -32601, "message": "Method not supported"}}
                    try:
                        self._send({"jsonrpc": "2.0", "id": msg["id"], **reply})
                    except Exception:
                        pass
        finally:
            for slot in list(self._pending.values()):   # server went away: release anyone waiting
                slot["ev"].set()

    # ---- http transport (Streamable HTTP)
    def _http_headers(self):
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
             "User-Agent": "MIVO-CODE"}
        h.update(expand_env(self.spec.get("headers") or {}))
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        if self.protocol:
            h["MCP-Protocol-Version"] = self.protocol
        return h

    def _http_request(self, msg, rid, timeout):
        r = self.http.post(self.spec["url"], json=msg, headers=self._http_headers(),
                           timeout=(15, timeout), stream=True)
        sid = r.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid
        if r.status_code >= 400:
            text = r.text[:150]
            r.close()
            raise RuntimeError(f"HTTP {r.status_code}: {text}")
        try:
            if "text/event-stream" in r.headers.get("content-type", ""):
                for raw in r.iter_lines():
                    if raw and raw.startswith(b"data:"):
                        try:
                            m = json.loads(raw[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        if m.get("id") == rid and ("result" in m or "error" in m):
                            return m
                return None
            data = r.json()
            if isinstance(data, list):
                data = next((m for m in data if m.get("id") == rid), None)
            return data
        finally:
            r.close()

    # ---- JSON-RPC
    def request(self, method, params=None, timeout=60):
        with self._lock:
            self._id += 1
            rid = self._id
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        if self.kind == "stdio":
            if not self.proc:
                raise RuntimeError("server is not running")
            slot = {"ev": threading.Event(), "msg": None}
            self._pending[rid] = slot
            self._send(msg)
            if not slot["ev"].wait(timeout):
                self._pending.pop(rid, None)
                raise TimeoutError(f"'{self.name}' did not answer {method} in {timeout}s")
            resp = slot["msg"]
        else:
            resp = self._http_request(msg, rid, timeout)
        if resp is None:
            raise RuntimeError("the server closed the connection")
        if "error" in resp:
            err = resp["error"] or {}
            raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")
        return resp.get("result") or {}

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        try:
            if self.kind == "stdio":
                self._send(msg)
            else:
                self.http.post(self.spec["url"], json=msg, headers=self._http_headers(), timeout=20).close()
        except Exception:
            pass

    def call(self, tool, args, timeout=120):
        res = self.request("tools/call", {"name": tool, "arguments": args or {}}, timeout)
        parts = []
        for c in res.get("content") or []:
            t = c.get("type")
            if t == "text":
                parts.append(c.get("text", ""))
            elif t == "image":
                parts.append("[image omitted]")
            elif t == "resource":
                r = c.get("resource") or {}
                parts.append(r.get("text") or f"[resource {r.get('uri')}]")
            else:
                parts.append(json.dumps(c)[:500])
        if not parts and res.get("structuredContent"):
            parts.append(json.dumps(res["structuredContent"])[:6000])
        text = "\n".join(parts).strip() or "(empty result)"
        return ("Error: " + text) if res.get("isError") else text


# --------------------------------------------------------------------------
# Components: one command provisions everything (modeled on `npx rea-agents setup`, `rea update`)
#   mivo setup    install/refresh RTK, MCP servers, then show a readiness table
#   mivo doctor   check readiness (also tests the API and every MCP server)
#   mivo update   git pull the source folder and re-run the installer
# --------------------------------------------------------------------------
RTK_REPO = os.environ.get("MIVO_RTK_REPO_URL", "https://github.com/rtk-ai/rtk")   # tests point this at a local server


def bin_dir():
    return MIVO_HOME / "bin"


def is_android():
    return is_termux() or os.path.exists("/system/bin/app_process") or "android" in platform.release().lower()


def glibc_present():
    """A real glibc userland (Ubuntu/Debian/Fedora, also inside proot on Android). Termux itself has none."""
    for p in ("/lib/ld-linux-aarch64.so.1", "/lib64/ld-linux-x86-64.so.2", "/lib/aarch64-linux-gnu/libc.so.6",
              "/lib/x86_64-linux-gnu/libc.so.6", "/usr/lib/aarch64-linux-gnu/libc.so.6",
              "/usr/lib/x86_64-linux-gnu/libc.so.6", "/lib64/libc.so.6"):
        if os.path.exists(p):
            return True
    try:
        r = subprocess.run(["ldd", "--version"], capture_output=True, text=True, timeout=5)
        return bool(re.search(r"GLIBC|GNU libc", r.stdout + r.stderr))
    except (OSError, subprocess.SubprocessError):
        return False


def rtk_target():
    """(release target triple or None, reason). Same targets as the official install.sh."""
    sysname, mach = platform.system(), platform.machine().lower()
    if sysname == "Darwin":
        return f"{'aarch64' if mach in ('arm64', 'aarch64') else 'x86_64'}-apple-darwin", ""
    if sysname == "Linux":
        if mach in ("x86_64", "amd64"):
            return "x86_64-unknown-linux-musl", ""      # static: runs anywhere
        if mach in ("aarch64", "arm64"):
            return "aarch64-unknown-linux-gnu", ""      # needs glibc (native, or Termux via glibc-runner)
    return None, f"no official binary for {sysname}/{mach}"


def rtk_asset():
    t, why = rtk_target()
    return (f"rtk-{t}.tar.gz" if t else None), why


def _net_error(e, url):
    if isinstance(e, requests.exceptions.SSLError):
        return f"TLS error for {url} (check the phone's date/time and CA certificates)"
    if isinstance(e, requests.exceptions.Timeout):
        return f"timed out reaching {url}"
    return f"cannot reach {url} (offline, DNS or proxy?)"


def rtk_release_bases():
    """Where to download from: the pinned or latest tag (like install.sh), then /releases/latest/download."""
    tag = os.environ.get("RTK_VERSION", "")
    if not tag:
        try:   # the 302 of /releases/latest carries the tag and costs no API quota
            r = requests.head(f"{RTK_REPO}/releases/latest", allow_redirects=False, timeout=15)
            m = re.search(r"/tag/([^/\s]+)\s*$", r.headers.get("location", ""))
            tag = m.group(1) if m else ""
        except requests.RequestException:
            tag = ""
    bases = [f"{RTK_REPO}/releases/download/{tag}"] if tag else []
    return bases + [f"{RTK_REPO}/releases/latest/download"]


def _termux_glibc_runner():
    """Termux has no glibc: set up glibc-runner (`grun`), the official way to run glibc binaries there."""
    if shutil.which("grun"):
        return True, ""
    for cmd in (["pkg", "install", "-y", "glibc-repo"], ["pkg", "install", "-y", "glibc", "glibc-runner"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except (OSError, subprocess.SubprocessError) as e:
            return False, f"{' '.join(cmd)} failed: {e}"
        if r.returncode != 0:
            return False, f"'{' '.join(cmd)}' failed: {(r.stderr or r.stdout).strip()[-120:]}"
    return (True, "") if shutil.which("grun") else (False, "glibc-runner installed but `grun` was not found")


def install_rtk():
    """Download the official rtk binary into ~/.mivo/bin (never PATH, never `rtk init`).
    Returns (ok, message). Messages name the exact URL / reason so failures can be diagnosed."""
    import hashlib
    import tarfile
    import tempfile
    existing = rtk_binary()
    if existing:
        return True, f"binary ready ({existing})"
    target, why = rtk_target()
    if not target:
        return False, why
    asset = f"rtk-{target}.tar.gz"
    needs_grun = target.endswith("linux-gnu") and not glibc_present()
    if needs_grun:
        if not is_termux():
            return False, "this system has no glibc (Alpine?). Build from source: cargo install --git https://github.com/rtk-ai/rtk"
        ok, msg = _termux_glibc_runner()
        if not ok:
            return False, f"Termux needs glibc-runner for the official binary: {msg}"
    last = "download failed"
    try:
        with tempfile.TemporaryDirectory() as td:
            tgz = Path(td) / asset
            data = None
            for base in rtk_release_bases():
                url = f"{base}/{asset}"
                try:
                    r = requests.get(url, stream=True, timeout=(15, 120), allow_redirects=True,
                                     headers={"User-Agent": "MIVO-CODE"})
                except requests.RequestException as e:
                    last = _net_error(e, url)
                    continue
                if r.status_code != 200:
                    last = f"HTTP {r.status_code} for {url}"
                    continue
                h = hashlib.sha256()
                with open(tgz, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
                        h.update(chunk)
                data = (base, h.hexdigest())
                break
            if not data:
                return False, last
            base, digest = data
            note = " (checksum not published)"
            try:   # the release publishes checksums.txt; refuse a mismatch
                cs = requests.get(f"{base}/checksums.txt", timeout=20, headers={"User-Agent": "MIVO-CODE"})
                if cs.status_code == 200:
                    want = next((l.split()[0] for l in cs.text.splitlines() if l.strip().endswith(asset)), None)
                    if want and want.lower() != digest:
                        return False, "checksum mismatch: refusing to install"
                    note = " (checksum verified)" if want else " (not listed in checksums.txt)"
            except requests.RequestException:
                note = " (checksum unavailable)"
            with tarfile.open(tgz) as tf:
                names = tf.getnames()
                if any(n.startswith("/") or ".." in Path(n).parts for n in names):
                    return False, "archive has unsafe paths: refusing to extract"
                member = next((m for m in tf.getmembers() if m.isfile() and os.path.basename(m.name) == "rtk"), None)
                if not member:
                    return False, "archive has no rtk binary"
                bin_dir().mkdir(parents=True, exist_ok=True)
                dest = bin_dir() / ("rtk.real" if needs_grun else "rtk")
                with open(dest, "wb") as out:
                    shutil.copyfileobj(tf.extractfile(member), out)
            os.chmod(dest, 0o755)
            if needs_grun:   # a tiny launcher: Termux's LD_PRELOAD shim must not reach the glibc loader
                sh = shutil.which("sh") or "/bin/sh"
                wrapper = bin_dir() / "rtk"
                wrapper.write_text(f'#!{sh}\nunset LD_PRELOAD\nexec grun "{dest}" "$@"\n', "utf-8")
                os.chmod(wrapper, 0o755)
    except requests.RequestException as e:
        return False, _net_error(e, RTK_REPO)
    except (tarfile.TarError, OSError) as e:
        return False, f"{type(e).__name__}: {str(e)[:100]}"
    _RTK_OK.clear()
    if rtk_binary():
        return True, f"installed to {bin_dir() / 'rtk'}{' via glibc-runner' if needs_grun else ''}{note}"
    for f in ("rtk", "rtk.real"):
        try:
            (bin_dir() / f).unlink()
        except OSError:
            pass
    return False, "the downloaded file did not run (or is not Rust Token Killer)"


def component_rows(cfg, install=False, connect=False, api=False):
    """[(name, state, detail)] with state ok | warn | fail."""
    rows = []
    ensure_mcp_config()
    if install:
        ok, msg = install_rtk()
    else:
        b = rtk_binary()
        ok, msg = (True, f"binary ready ({b})") if b else (False, "official binary not installed")
    rows.append(("RTK output compaction", "ok" if ok else "warn",
                 msg if ok else f"built-in engine active · {msg}"))
    c7key = (cfg.data.get("context7") or {}).get("api_key") or os.environ.get("CONTEXT7_API_KEY", "")
    for name, spec in load_mcp_servers(c7key).items():
        kind = "stdio" if "command" in spec else "remote"
        if connect:
            cl = McpClient(name, spec)
            cl.connect(timeout=25)
            cl.close()
            rows.append((f"MCP · {name}", "ok" if cl.status == "ready" else "warn",
                         f"{kind} · {len(cl.tools)} tools" if cl.status == "ready" else f"{kind} · {cl.error} (retries at start)"))
        else:
            rows.append((f"MCP · {name}", "ok", f"{kind} · registered in {mcp_config_path()}"))
    rows.append(("Docs fallback (Context7 REST)", "ok", "built in"))
    tgc = tg_cfg(cfg)
    if tgc.get("token"):
        pid = bot_running()
        rows.append(("Telegram bot", "ok" if pid else "warn",
                     f"@{tgc.get('username', '')} · " + (f"running (pid {pid})" if pid else "stopped: /addbot start")))
    rows.append(("Caveman · Ponytail", "ok", f"caveman {cfg.get('caveman', 'lite')} · ponytail {cfg.get('ponytail', 'lite')} (on by default)"))
    node = shutil.which("npx")
    rows.append(("Node.js (stdio MCP servers)", "ok" if node else "warn",
                 "available" if node else "not installed: only needed for stdio servers (apt install nodejs npm / pkg install nodejs)"))
    rows.append(("git", "ok" if shutil.which("git") else "warn",
                 "available" if shutil.which("git") else "not installed (needed by /ponytail-review and `mivo update`)"))
    if api:
        if cfg.complete():
            ok, msg = Provider(cfg).verify()
            rows.append(("API connection", "ok" if ok else "fail", msg))
        else:
            rows.append(("API connection", "fail", "not configured: run mivo --setup"))
    return rows


def print_components(rows, title="MIVO components"):
    icon = {"ok": "[ok]✓[/]", "warn": "[warn]●[/]", "fail": "[err]✗[/]"}
    body = "\n".join(f"{icon[s]} [bold]{escape(n)}[/]\n   [muted]{escape(d)}[/]" for n, s, d in rows)
    console.print(Panel(body, title=f"[brand]◆ {title}[/]", title_align="left", border_style="brand",
                        box=box.ROUNDED, padding=(0, 1)))


def run_cli_command(args, cfg):
    cmd = args.command
    if cmd == "bot":
        return run_bot_foreground(cfg)
    if cmd == "setup":
        if args.show:
            try:
                data = json.loads((MIVO_HOME / "components.json").read_text("utf-8"))
                print_components([tuple(r) for r in data["rows"]], "Installed components")
            except (OSError, json.JSONDecodeError, KeyError):
                console.print("[muted]Nothing recorded yet. Run: mivo setup[/]")
            return 0
        rows = component_rows(cfg, install=True, connect=True)
        try:
            (MIVO_HOME / "components.json").write_text(
                json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "rows": rows}), "utf-8")
        except OSError:
            pass
        if not args.quiet:
            print_components(rows, "MIVO setup")
        return 0
    if cmd == "doctor":
        console.print()
        with console.status("[brand]Checking everything...[/]"):
            rows = component_rows(cfg, install=False, connect=True, api=True)
        print_components(rows, "MIVO doctor")
        return 1 if any(s == "fail" for _, s, _ in rows) else 0
    if cmd == "update":
        try:
            src = Path((MIVO_HOME / "source").read_text("utf-8").strip())
        except OSError:
            src = None
        if not src or not (src / "mivo.sh").exists():
            console.print("[warn]Source folder unknown. Go to your MIVO folder and run: git pull && bash mivo.sh[/]")
            return 1
        if (src / ".git").exists() and shutil.which("git"):
            r = subprocess.run(["git", "-C", str(src), "pull", "--ff-only"], capture_output=True, text=True)
            if r.returncode != 0:
                console.print("[warn]git pull did not work (offline or no upstream): reinstalling the files already "
                              f"in {escape(str(src))}.[/]")
                console.print(f"[muted]{escape((r.stderr or r.stdout).strip().splitlines()[0] if (r.stderr or r.stdout).strip() else '')}[/]")
            else:
                console.print(f"[ok]✓[/] {escape((r.stdout.strip().splitlines() or ['up to date'])[-1])}")
        else:
            console.print("[muted]Not a git checkout: re-installing from the current files.[/]")
        return subprocess.run(["bash", str(src / "mivo.sh")]).returncode
    return 0


# --------------------------------------------------------------------------
# Telegram gateway (/addbot): talk to the AI from Telegram and let it run commands on this device.
# Runs as its own background process (`mivo bot`) so chat sessions never disturb the terminal session.
# Safety: only paired Telegram accounts are served, private chats only, risky actions need a button press.
# --------------------------------------------------------------------------
TG_MAX = 3800
ACTIVE_PROCS = set()


class TgError(Exception):
    def __init__(self, code, desc):
        super().__init__(desc)
        self.code, self.desc = code, desc


class TgClient:
    def __init__(self, token, base="https://api.telegram.org"):
        self.token, self.base, self.http = token, (base or "https://api.telegram.org").rstrip("/"), requests.Session()

    def call(self, method, timeout=60, files=None, **params):
        url = f"{self.base}/bot{self.token}/{method}"
        try:
            if files:
                r = self.http.post(url, data=params, files=files, timeout=timeout)
            else:
                r = self.http.post(url, json=params, timeout=timeout)
        except requests.RequestException as e:   # never include the exception text: it contains the URL (token)
            raise TgError(0, f"cannot reach Telegram ({type(e).__name__})")
        try:
            d = r.json()
        except ValueError:
            raise TgError(r.status_code, f"unexpected reply (HTTP {r.status_code})")
        if not d.get("ok"):
            raise TgError(d.get("error_code", r.status_code), d.get("description", "error"))
        return d["result"]

    def get_updates(self, offset, timeout=30):
        url = f"{self.base}/bot{self.token}/getUpdates"
        try:
            r = self.http.post(url, json={"offset": offset, "timeout": timeout,
                                          "allowed_updates": ["message", "callback_query"]},
                               timeout=(15, timeout + 20))
            d = r.json()
        except requests.RequestException as e:
            raise TgError(0, f"cannot reach Telegram ({type(e).__name__})")
        except ValueError:
            raise TgError(0, "unexpected reply")
        if not d.get("ok"):
            raise TgError(d.get("error_code", r.status_code), d.get("description", "error"))
        return d.get("result", [])

    def download(self, file_path, dest, limit=20_000_000):
        r = self.http.get(f"{self.base}/file/bot{self.token}/{file_path}", stream=True, timeout=(15, 120))
        if r.status_code != 200:
            raise TgError(r.status_code, "download failed")
        n = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                n += len(chunk)
                if n > limit:
                    raise TgError(0, "file too large")
                f.write(chunk)


def tg_verify(token, base=None):
    """(True, {'id','first_name','username'}) or (False, message)."""
    token = (token or "").strip()
    if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", token):
        return False, "That does not look like a BotFather token (format 123456789:AAH...)."
    try:
        me = TgClient(token, base).call("getMe", timeout=20)
    except TgError as e:
        if e.code in (401, 404):
            return False, "Invalid token: Telegram rejected it."
        return False, f"{e.desc}"
    return True, me


def tg_cfg(cfg):
    return cfg.data.get("telegram") or {}


def bot_pid_file():
    return MIVO_HOME / "bot.pid"


def bot_running():
    try:
        pid = int(bot_pid_file().read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return 0


def start_bot(wait=8.0):
    """Start the gateway in the background (detached). Returns (ok, message)."""
    if bot_running():
        return True, "already running"
    log = MIVO_HOME / "bot.log"
    try:
        if log.exists() and log.stat().st_size > 1_000_000:
            log.write_text("")
        out = open(log, "a")
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "bot"], stdin=subprocess.DEVNULL, stdout=out,
                         stderr=out, start_new_session=True, env={**os.environ, "MIVO_NO_ANIM": "1"})
    except OSError as e:
        return False, f"could not start: {e}"
    end = time.time() + wait
    while time.time() < end:
        if (MIVO_HOME / "bot.ready").exists() and bot_running():
            return True, "running"
        time.sleep(0.2)
    tail = log.read_text("utf-8", "replace").strip().splitlines()[-1:] if log.exists() else []
    return False, (tail[0][:120] if tail else "did not start in time (see /addbot log)")


def stop_bot():
    pid = bot_running()
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            time.sleep(0.1)
            if not bot_running():
                break
    except OSError:
        pass
    return True


def tg_html(text):
    """Chat text -> Telegram HTML: fenced code becomes <pre>, `code` becomes <code>, **bold** becomes <b>."""
    import html

    def inline(seg):
        e = html.escape(seg, quote=False)
        e = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", e)
        return re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", e)
    out, pos = [], 0
    for m in re.finditer(r"```[^\n`]*\n(.*?)```", text, re.S):
        out.append(inline(text[pos:m.start()]))
        out.append("<pre>" + html.escape(m.group(1).rstrip("\n"), quote=False) + "</pre>")
        pos = m.end()
    out.append(inline(text[pos:]))
    return "".join(out)


def split_message(text, n=TG_MAX):
    """Chunks under Telegram's limit; an open code fence is closed and reopened across chunks."""
    if len(text) <= n:
        return [text]
    chunks, cur, fence = [], "", False
    for line in text.split("\n"):
        pieces = [line[i:i + n] for i in range(0, len(line), n)] or [""]
        for piece in pieces:
            add = piece + "\n"
            if len(cur) + len(add) > n and cur.strip():
                chunks.append(cur.rstrip("\n") + ("\n```" if fence else ""))
                cur = "```\n" if fence else ""
            cur += add
        if line.strip().startswith("```"):
            fence = not fence
    if cur.strip():
        chunks.append(cur.rstrip("\n"))
    return chunks


def arg_summary(args):
    s = args.get("command") or args.get("path") or args.get("pattern") or args.get("url") or args.get("query") \
        or args.get("name") or next((v for v in args.values() if isinstance(v, str)), "")
    return str(s).splitlines()[0][:90] if s else ""


class TgSession:
    """One Telegram chat = one agent with its own history and working folder."""

    def __init__(self, gw, chat_id):
        self.gw, self.chat_id = gw, chat_id
        self.cwd = gw.default_cwd()
        self.agent = gw.make_agent(chat_id)
        self.status_mid, self.lines, self.last_edit = None, [], 0.0
        self.busy = False

    def progress(self, kind, name, args):
        self.lines.append(f"⚙ {name} {arg_summary(args)}".strip())
        self.lines = self.lines[-6:]
        now = time.time()
        text = "\n".join(self.lines)
        try:
            if self.status_mid is None:
                self.status_mid = self.gw.tg.call("sendMessage", chat_id=self.chat_id, text=text[:900])["message_id"]
                self.last_edit = now
            elif now - self.last_edit > 2.5:
                self.gw.tg.call("editMessageText", chat_id=self.chat_id, message_id=self.status_mid, text=text[:900])
                self.last_edit = now
        except TgError:
            pass

    def clear_status(self):
        if self.status_mid:
            try:
                self.gw.tg.call("deleteMessage", chat_id=self.chat_id, message_id=self.status_mid)
            except TgError:
                pass
        self.status_mid, self.lines = None, []


class TelegramGateway:
    def __init__(self, cfg):
        self.cfg = cfg
        t = tg_cfg(cfg)
        self.tg = TgClient(t["token"], cfg.data.get("telegram_api"))
        self.sessions, self.jobs, self.pending = {}, queue.Queue(), {}
        self.offset, self.running, self.started = 0, True, time.time()
        self.warned, self.bad_pair = {}, {}
        self.base_agent = None

    # ---- small helpers
    def log(self, msg):
        msg = msg.replace(self.tg.token, "<token>")
        print(f"{datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)

    def settings(self):
        """Fresh view of the telegram settings: /addbot changes apply without a restart."""
        try:
            return tg_cfg(Config(use_env=False))
        except Exception:
            return tg_cfg(self.cfg)

    def update_settings(self, **changes):
        c = Config(use_env=False)
        c.data.setdefault("telegram", {}).update(changes)
        c.save()

    def default_cwd(self):
        p = Path(os.path.expanduser(self.settings().get("cwd") or self.cfg.get("root_dir") or str(Path.home())))
        return str(p) if p.is_dir() else str(Path.home())

    def make_agent(self, chat_id):
        import copy
        data = copy.deepcopy(self.cfg.data)
        data["mode"] = self.settings().get("mode", "auto")
        c = Config(data=data)
        c.save = lambda: None            # a chat session must never rewrite your config file
        ag = Agent(c, mcp=False)
        ag.session_id = f"tg{chat_id}-" + ag.session_id
        ag.extra_system = ("You are answering through Telegram on the owner's phone. Keep replies compact (the chat "
                           "limit is small), put code in fenced blocks, avoid wide tables. You can run commands on "
                           "this device with your tools. Use the telegram_send tool to send a file you created.")
        ag.events = lambda kind, name, args, s=None: self.sessions[chat_id].progress(kind, name, args)
        ag.confirm_hook = lambda tool, args, level, keys, note, ag=ag: self.approve(chat_id, ag, tool, args, level, keys, note)
        S = lambda d: {"type": "string", "description": d}

        def send_file(a):
            p = resolve(a["path"])
            if not p.is_file():
                return f"Error: {p} is not a file"
            if p.stat().st_size > 49_000_000:
                return "Error: file is larger than Telegram's 50 MB bot limit"
            with open(p, "rb") as f:
                self.tg.call("sendDocument", timeout=180, files={"document": (p.name, f)}, chat_id=chat_id,
                             caption=str(a.get("caption", ""))[:900])
            return f"Sent {p.name} to the chat"
        ag.tools["telegram_send"] = Tool(
            "telegram_send", "Send a file from this device to the Telegram chat (up to 50 MB).",
            obj({"path": S("File path"), "caption": S("Optional caption")}, ["path"]), send_file,
            lambda a: ("safe", None, "") if path_ok_to_write(resolve(a.get("path", ""))) else ("ask", None, "outside your storage"))
        return ag

    # ---- sending
    def send(self, chat_id, text, markup=None):
        for chunk in split_message(text or "(empty)"):
            params = {"chat_id": chat_id, "text": tg_html(chunk), "parse_mode": "HTML", "disable_web_page_preview": True}
            if markup:
                params["reply_markup"] = markup
            try:
                self.tg.call("sendMessage", **params)
            except TgError as e:
                if e.code == 400:          # formatting problem: send it as plain text
                    params.pop("parse_mode"); params["text"] = chunk
                    try:
                        self.tg.call("sendMessage", **params)
                    except TgError as e2:
                        self.log(f"send failed: {e2.desc}")
                else:
                    self.log(f"send failed: {e.desc}")
            markup = None

    # ---- approvals (inline buttons)
    def approve(self, chat_id, ag, tool, args, level, keys, note):
        try:
            title, body = tool.preview(args) if tool.preview else (f"Run {tool.name}", Text(json.dumps(args)[:900]))
        except Exception:
            title, body = f"Run {tool.name}", Text(json.dumps(args)[:900])
        aid = uuid.uuid4().hex[:8]
        danger = level == "danger"
        text = (("🚨 DANGEROUS: " if danger else "⚠ ") + f"{title}" + (f" [{note}]" if note else "") +
                "\n```\n" + str(body.plain if hasattr(body, "plain") else body)[:1500] + "\n```")
        row = [{"text": "✅ Yes, run it" if danger else "✅ Allow", "callback_data": f"ap|{aid}|y"}]
        if keys and not danger:
            row.append({"text": "♾ Always", "callback_data": f"ap|{aid}|a"})
        row.append({"text": "🚫 Cancel" if danger else "🚫 Deny", "callback_data": f"ap|{aid}|n"})
        ev = threading.Event()
        self.pending[aid] = {"ev": ev, "res": "n", "chat": chat_id}
        self.send(chat_id, text, markup={"inline_keyboard": [row]})
        got = ev.wait(300)
        res = self.pending.pop(aid, {}).get("res", "n") if got else "n"
        if not got:
            self.send(chat_id, "⏱ No answer in 5 minutes: denied.")
        if res == "a" and keys:
            ag.allowed.update(keys)     # remembered while the gateway runs (not written to your config)
        return res in ("y", "a"), ("" if res != "n" else "denied from Telegram")

    # ---- authorization / pairing
    def is_allowed(self, uid):
        return uid in (self.settings().get("allowed_users") or [])

    def try_pair(self, uid, code, chat_id):
        now = time.time()
        b = self.bad_pair.get(uid, (0, 0))
        if b[0] >= 5 and now - b[1] < 600:
            return
        s = self.settings()
        good = (s.get("pair_code") and secrets.compare_digest(str(s["pair_code"]), str(code).strip())
                and s.get("pair_expires", 0) > now)
        if not good:
            self.bad_pair[uid] = (b[0] + 1, now)
            self.send(chat_id, "❌ Wrong or expired pairing code. In MIVO run /addbot pair for a new one.")
            self.log(f"pairing failed for user {uid}")
            return
        users = list(dict.fromkeys((s.get("allowed_users") or []) + [uid]))
        self.update_settings(allowed_users=users, pair_code="", pair_expires=0)
        self.bad_pair.pop(uid, None)
        self.log(f"paired user {uid}")
        self.send(chat_id, "✅ Paired. You can now talk to your AI here. Try: *what's in my home folder?*\n"
                           "/help shows the commands.")

    # ---- updates
    def handle_update(self, u):
        if "callback_query" in u:
            return self.handle_callback(u["callback_query"])
        msg = u.get("message")
        if not msg:
            return
        chat, frm = msg.get("chat", {}), msg.get("from", {})
        if chat.get("type") != "private" or not frm.get("id"):
            return
        if msg.get("date", time.time()) < self.started - 120:   # never run stale commands queued while offline
            return
        uid, cid = frm["id"], chat["id"]
        text = (msg.get("text") or msg.get("caption") or "").strip()
        m = re.match(r"^/(?:pair|start)(?:@\w+)?\s+(\S+)$", text)
        if not self.is_allowed(uid):
            if m:
                return self.try_pair(uid, m.group(1), cid)
            if time.time() - self.warned.get(uid, 0) > 600:
                self.warned[uid] = time.time()
                self.send(cid, "🔒 This bot is private.\nOwner: run /addbot pair in MIVO, then send /pair CODE here.")
            return
        if re.match(r"^/(start|help)(@\w+)?$", text):
            return self.send(cid, "🤖 MIVO CODE on Telegram\nJust write what you want done; I can read, write and run things here.\n"
                                  "/new fresh chat · /cd <folder> · /pwd · /stop cancel the task · /mode auto|ask|yolo · /status · /id")
        if text == "/id":
            return self.send(cid, f"Your Telegram id: {uid}")
        if text.startswith("/new"):
            self.sessions.pop(cid, None)
            return self.send(cid, "🆕 New conversation.")
        if text.startswith("/stop"):
            s = self.sessions.get(cid)
            if s and s.busy:
                s.agent.cancel = True
                for p in list(ACTIVE_PROCS):
                    kill_proc(p)
                for a in [a for a in self.pending.values() if a["chat"] == cid]:
                    a["res"] = "n"; a["ev"].set()
                return self.send(cid, "🛑 Stopping...")
            return self.send(cid, "Nothing is running.")
        if text.startswith("/cd"):
            s = self.session(cid)
            p = Path(os.path.expanduser(text[3:].strip() or "~"))
            p = p if p.is_absolute() else Path(s.cwd) / p
            if p.is_dir():
                s.cwd = str(p.resolve())
                return self.send(cid, f"📁 {s.cwd}")
            return self.send(cid, f"Not a folder: {p}")
        if text == "/pwd":
            return self.send(cid, f"📁 {self.session(cid).cwd}")
        if text.startswith("/mode"):
            arg = text[5:].strip().lower()
            if arg in MODES:
                self.update_settings(mode=arg)
                s = self.sessions.get(cid)
                if s:
                    s.agent.cfg.set("mode", arg)
                return self.send(cid, f"Mode: {arg}. {MODES[arg]}")
            return self.send(cid, f"Mode: {self.settings().get('mode', 'auto')}. /mode auto|ask|yolo")
        if text == "/status":
            s = self.session(cid)
            return self.send(cid, f"📁 {s.cwd}\nmodel: {self.cfg.get('model')}\nmode: {self.settings().get('mode', 'auto')}\n"
                                  f"messages in this chat: {len(s.agent.messages)}")
        extra = self.fetch_attachment(msg, cid)
        if not text and not extra:
            return
        self.jobs.put((cid, (text + "\n" + extra).strip()))
        s = self.sessions.get(cid)
        if s and s.busy:
            self.send(cid, "⏳ Queued after the current task.")

    def fetch_attachment(self, msg, cid):
        """Documents/photos are saved to <folder>/telegram_inbox and handed to the AI as a path."""
        fid = name = None
        if msg.get("document"):
            fid, name = msg["document"]["file_id"], msg["document"].get("file_name") or "file"
        elif msg.get("photo"):
            fid, name = msg["photo"][-1]["file_id"], f"photo_{msg.get('message_id', 0)}.jpg"
        if not fid:
            return ""
        try:
            info = self.tg.call("getFile", file_id=fid)
            inbox = Path(self.session(cid).cwd) / "telegram_inbox"
            inbox.mkdir(exist_ok=True)
            dest = inbox / re.sub(r"[^\w.\- ]", "_", name)
            self.tg.download(info["file_path"], dest)
            return f"[The user sent a file, saved at: {dest}]"
        except (TgError, OSError) as e:
            self.send(cid, f"⚠ Could not receive the file: {getattr(e, 'desc', e)}")
            return ""

    def handle_callback(self, cb):
        data, uid = cb.get("data", ""), (cb.get("from") or {}).get("id")
        m = re.match(r"^ap\|(\w+)\|([yan])$", data)
        try:
            self.tg.call("answerCallbackQuery", callback_query_id=cb["id"])
        except TgError:
            pass
        if not m or not self.is_allowed(uid):
            return
        item = self.pending.get(m.group(1))
        if item:
            item["res"] = m.group(2)
            item["ev"].set()
            mid, cid = (cb.get("message") or {}).get("message_id"), ((cb.get("message") or {}).get("chat") or {}).get("id")
            label = {"y": "✅ Allowed", "a": "♾ Allowed (always)", "n": "🚫 Denied"}[m.group(2)]
            try:
                self.tg.call("editMessageText", chat_id=cid, message_id=mid, text=label)
            except TgError:
                pass

    # ---- jobs
    def session(self, cid):
        if cid not in self.sessions:
            self.sessions[cid] = TgSession(self, cid)
        return self.sessions[cid]

    def worker(self):
        while self.running:
            try:
                cid, text = self.jobs.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self.run_job(cid, text)
            except Exception as e:
                self.log(f"job error: {type(e).__name__}")
                self.send(cid, f"⚠ Internal error: {type(e).__name__}")

    def run_job(self, cid, text):
        s = self.session(cid)
        s.busy, s.agent.cancel = True, False
        if self.base_agent:   # MCP tools live on one shared agent
            mcp = {k: v for k, v in self.base_agent.tools.items() if k.startswith("mcp__")}
            s.agent.tools = {**s.agent.tools, **mcp}
            if any(k.startswith("mcp__context7__") for k in mcp):
                s.agent.tools.pop("lib_docs", None)
                s.agent.tools.pop("lib_search", None)
        try:
            os.chdir(s.cwd if os.path.isdir(s.cwd) else str(Path.home()))
        except OSError:
            pass
        done = threading.Event()

        def typing():
            while not done.is_set():
                try:
                    self.tg.call("sendChatAction", chat_id=cid, action="typing", timeout=10)
                except TgError:
                    pass
                done.wait(4)
        threading.Thread(target=typing, daemon=True).start()
        self.log(f"chat {cid}: {text[:60]!r}")
        reply = None
        try:
            s.agent.run_turn(text)
            last = s.agent.messages[-1] if s.agent.messages else {}
            reply = (last.get("content") or "").strip() if last.get("role") == "assistant" else ""
        except KeyboardInterrupt:
            reply = "🛑 Stopped."
        except ProviderError as e:
            reply = "⚠ " + e.friendly()[:600]
        except requests.RequestException:
            reply = "⚠ Network problem reaching the AI provider."
        finally:
            done.set()
            s.cwd = os.getcwd()
            s.busy = False
            s.clear_status()
        if s.agent.cancel:   # /stop ends the tool loop quietly, so say it explicitly
            reply = "🛑 Stopped."
        self.send(cid, reply or "✓ Done.")

    # ---- main loop
    def run(self):
        try:
            me = self.tg.call("getMe", timeout=20)
        except TgError as e:
            self.log("cannot start: " + ("Telegram rejected the token (revoked?). Run /addbot with a new token"
                                         if e.code in (401, 404) else e.desc))
            return
        try:
            self.tg.call("deleteWebhook", timeout=20)   # a webhook would block getUpdates
        except TgError:
            pass
        self.log(f"connected as @{me.get('username')}")
        self.base_agent = Agent(Config(data=dict(self.cfg.data)), mcp=True)
        if os.environ.get("TERMUX_VERSION") or is_termux():
            try:
                subprocess.run(["termux-wake-lock"], timeout=5, capture_output=True)   # keep the phone awake for the bot
            except (OSError, subprocess.SubprocessError):
                pass
        threading.Thread(target=self.worker, daemon=True).start()
        (MIVO_HOME / "bot.ready").write_text(str(os.getpid()))
        backoff = 1
        while self.running:
            try:
                updates = self.tg.get_updates(self.offset)
                for u in updates:
                    self.offset = u["update_id"] + 1
                    try:
                        self.handle_update(u)
                    except Exception as e:
                        self.log(f"update error: {type(e).__name__}")
                backoff = 1
            except TgError as e:
                self.log(f"telegram: {e.desc}")
                if e.code == 401:
                    self.log("the token was revoked: stopping")
                    break
                time.sleep(min(backoff, 30) + (5 if e.code == 409 else 0))
                backoff *= 2
            except requests.RequestException:
                self.log("network problem, retrying")
                time.sleep(min(backoff, 30))
                backoff *= 2
            except ValueError:
                time.sleep(2)
        self.running = False


def run_bot_foreground(cfg):
    t = tg_cfg(cfg)
    if not t.get("token"):
        print("No bot configured. In MIVO run /addbot")
        return 1
    if bot_running() and bot_running() != os.getpid():
        print("The bot is already running (pid %s). Stop it with /addbot stop" % bot_running())
        return 1
    MIVO_HOME.mkdir(parents=True, exist_ok=True)
    bot_pid_file().write_text(str(os.getpid()))
    for f in ("bot.ready",):
        try:
            (MIVO_HOME / f).unlink()
        except OSError:
            pass
    gw = TelegramGateway(cfg)

    def stop(*_):
        gw.running = False
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        gw.run()
    finally:
        for f in ("bot.pid", "bot.ready"):
            try:
                (MIVO_HOME / f).unlink()
            except OSError:
                pass
        if gw.base_agent:
            gw.base_agent.close_mcp()
    return 0


def new_session_id():
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


def json_loads_safe(s):
    try:
        v = json.loads(s or "{}")
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        return None


def is_context_error(body):
    b = body.lower()
    return bool(re.search(r"context|maximum.*length|too long|too many tokens|token limit|max_tokens", b))


class Agent:
    def __init__(self, cfg: Config, mcp=True):
        self.cfg = cfg
        self.provider = Provider(cfg)
        self.messages = []
        self.session_id = new_session_id()
        self.created = datetime.now().isoformat(timespec="seconds")
        self.allowed = set(cfg.get("always_allow", []) or [])
        self.tools = {t.name: t for t in core_tools()}
        self.commands = {}
        self.skills = load_skills()
        self.plugins = []
        self.state = {"todos": []}
        self.ledger, self.undo_stack, self.live_info = [], [], {}
        self.fence_existed, self._map = {}, None
        self.usage, self.ctx_tokens, self.read_cache = {"calls": 0, "prompt": 0, "completion": 0, "reported": False}, 0, {}
        self.turn_wrote_code, self.turn_ran, self._sigs = False, False, []
        self.tools["use_skill"] = Tool(
            "use_skill", "Load the full instructions of a skill by name.",
            obj({"name": {"type": "string", "description": "Skill name"}}, ["name"]), self._use_skill)
        self.tools["remember"] = Tool(
            "remember", "Save a durable note about this project (decisions, conventions, architecture, what each "
            "file does, TODOs). Notes are shown to you at the start of every turn, even after a restart.",
            obj({"note": {"type": "string", "description": "One concise fact"}}, ["note"]), t_remember)
        self.recall_store, self.rtk_stats = {}, {"calls": 0, "before": 0, "after": 0}
        self.mcp, self._tools_lock = {}, threading.Lock()
        self.events = self.confirm_hook = None   # set by the Telegram gateway
        self.cancel, self.extra_system = False, ""

        def _recall(a):
            txt = self.recall_store.get(str(a.get("id", "")).strip())
            if txt is None:
                return "Error: unknown recall id (only the last 20 compacted outputs are kept)"
            if a.get("grep"):
                try:
                    rx = re.compile(a["grep"], re.I)
                except re.error as e:
                    return f"Error: bad regex: {e}"
                ls = txt.split("\n")
                keep = sorted({j for i, l in enumerate(ls) if rx.search(l) for j in range(max(i - 1, 0), min(i + 2, len(ls)))})
                return "\n".join(ls[j] for j in keep) or "No matching lines"
            return txt
        self.tools["recall"] = Tool(
            "recall", "Get the full raw output of an earlier compacted command (id from its [rtk: ...] note). "
            "Optional grep regex returns only matching lines.",
            obj({"id": {"type": "string"}, "grep": {"type": "string", "description": "Regex filter (optional)"}},
                ["id"]), _recall)
        self.apply_web_tool()
        self.apply_c7_tools()
        self._register_commands()
        self.load_plugins()
        if mcp:
            self.start_mcp()

    # ---- skills / plugins
    def _use_skill(self, a):
        s = self.skills.get(a["name"])
        if not s:
            return f"Unknown skill. Available: {', '.join(self.skills) or 'none'}"
        return s["body"]

    def load_plugins(self):
        disabled = set(self.cfg.get("disabled_plugins", []) or [])
        for f in sorted(PLUGIN_DIR.glob("*.py")):
            if f.name.startswith("_") or f.stem in disabled:
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"mivo_plugin_{f.stem}", f)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.register(PluginAPI(self, f.stem))
                self.plugins.append(f.stem)
            except Exception as e:
                console.print(f"[red]Plugin {f.name} failed to load: {escape(str(e))}[/]")

    # ---- prompts
    def native(self):
        return self.cfg.get("tool_mode", "native") == "native"

    def caveman_prompt(self):
        lv = self.cfg.get("caveman", "lite")
        return f"CAVEMAN ({lv}): {CAVEMAN_RULES[lv]} {CAVEMAN_COMMON}" if lv in CAVEMAN_RULES else ""

    def ponytail_prompt(self):
        return PONYTAIL_RULES.get(self.cfg.get("ponytail", "lite"), "")

    def system_prompt(self):
        env = describe_env()
        base = (self.cfg.get("system_prompt") or DEFAULT_RULES)
        parts = [base.replace("{env}", env).replace("{cwd}", os.getcwd())]
        inst = (self.cfg.get("instructions") or "").strip()
        if inst:
            parts.append("USER PREFERENCES (set by the user; follow them, they take priority over the "
                         "defaults above):\n" + inst)
        for extra in (self.thinking_prompt(), self.caveman_prompt(), self.ponytail_prompt(), self.extra_system):
            if extra:
                parts.append(extra)
        for name in ("MIVO.md", "AGENTS.md", "CLAUDE.md"):
            f = Path(os.getcwd()) / name
            if f.is_file():
                parts.append(f"Project instructions ({name}):\n{truncate(f.read_text('utf-8', 'replace'), 8000)}")
                break
        if self.skills:
            lst = "\n".join(f"- {n}: {s['description']}" for n, s in self.skills.items())
            parts.append("Skills available (call use_skill with the name when relevant):\n" + lst)
        if self.c7_enabled():
            parts.append(C7_RULE)
        if self.cfg.get("rtk", "auto") != "off":
            parts.append(RTK_RULE)
        if not self.native():
            tl = "\n".join(f"- {t.name}: {t.description}\n  parameters (JSON schema): {json.dumps(t.parameters)}"
                           for t in self.tools.values())
            parts.append(
                "You can call tools. To call one, output a block on its own line:\n"
                f'{TOOL_TAG}{{"name": "TOOL_NAME", "arguments": {{...}}}}</tool_call>\n'
                "Then stop and wait: the result arrives in a message starting with <tool_result>. "
                "Call one tool at a time.\nTools:\n" + tl)
        dyn = []
        act = self.active_skills()
        if act:
            dyn.append("ACTIVE SKILLS (apply them to this request):\n" + "\n\n".join(
                f"### {n}\n{truncate(self.skills[n]['body'], 3500)}" for n in act))
        dyn.extend(self.memory_context())
        # the marker lets Anthropic cache the stable part; other providers just see a blank line
        return "\n\n".join(parts) + DYN_MARK + "\n\n".join(dyn)

    def active_skills(self):
        """Skills whose trigger words appear in the user's latest request (plus always-on ones)."""
        last = next((m["content"] for m in reversed(self.messages) if m["role"] == "user"
                     and m.get("content") and not m["content"].startswith("[MIVO]")), "").lower()
        always = [n for n, s in self.skills.items() if "*" in s["triggers"]]
        scored = []
        for n, s in self.skills.items():
            hits = sum(1 for t in s["triggers"] if t != "*" and re.search(r"\b" + re.escape(t) + r"\b", last))
            if hits:
                scored.append((hits, n))
        scored.sort(key=lambda x: -x[0])
        return always + [n for _, n in scored[:2]]

    def _slim(self, msgs, keep=8):
        """Old bulky tool output and old file contents are shrunk in what is SENT (storage is untouched):
        the files are on disk and in the project map, so this saves tokens and time."""
        cut, out = max(len(msgs) - keep, 0), []
        for i, m in enumerate(msgs):
            if i < cut:
                if m["role"] == "tool" and len(m["content"]) > 1200:
                    m = {**m, "content": truncate(m["content"], 1200)}
                elif m["role"] == "assistant" and m.get("tool_calls"):
                    tcs = []
                    for tc in m["tool_calls"]:
                        fn = tc["function"]
                        if fn["name"] in ("write_file", "edit_file") and len(fn["arguments"]) > 600:
                            a = json_loads_safe(fn["arguments"]) or {}
                            for k in ("content", "old_string", "new_string"):
                                if isinstance(a.get(k), str) and len(a[k]) > 300:
                                    a[k] = f"[{len(a[k])} chars, already applied: see the file on disk]"
                            tc = {**tc, "function": {**fn, "arguments": json.dumps(a)}}
                        tcs.append(tc)
                    m = {**m, "tool_calls": tcs}
            out.append(m)
        return out

    def build_messages(self):
        out = [{"role": "system", "content": self.system_prompt()}]
        msgs = self._slim(self.messages)
        if self.native():
            return out + msgs
        for m in msgs:
            if m["role"] == "assistant" and m.get("tool_calls"):
                txt = m.get("content") or ""
                for tc in m["tool_calls"]:
                    call = {"name": tc["function"]["name"],
                            "arguments": json_loads_safe(tc["function"]["arguments"]) or {}}
                    txt += f"\n{TOOL_TAG}{json.dumps(call)}</tool_call>"
                out.append({"role": "assistant", "content": txt.strip()})
            elif m["role"] == "tool":
                out.append({"role": "user", "content": f"<tool_result>\n{m['content']}\n</tool_result>"})
            else:
                out.append({"role": m["role"], "content": m.get("content") or ""})
        return out

    # ---- persistence
    def save(self):
        if not self.messages:
            return
        if len(self.messages) > 60:   # very old bulky output is shrunk on disk too (files live on disk)
            self.messages = self._slim(self.messages, keep=40)
        first = next((m["content"] for m in self.messages if m["role"] == "user"), "")
        data = {"id": self.session_id, "title": (first or "Untitled").strip().replace("\n", " ")[:70],
                "cwd": os.getcwd(), "created": self.created,
                "updated": datetime.now().isoformat(timespec="seconds"),
                "model": self.cfg.get("model"), "ledger": self.ledger, "messages": self.messages}
        try:
            SESSION_DIR.mkdir(parents=True, exist_ok=True)
            (SESSION_DIR / f"{self.session_id}.json").write_text(
                json.dumps(data, ensure_ascii=False), "utf-8")
        except OSError as e:
            console.print(f"[red]Could not save session: {e}[/]")

    # ---- model call
    # ---- thinking (reasoning) support
    def thinking_level(self):
        lv = self.cfg.get("thinking", "off")
        return lv if lv in ("low", "medium", "high") else "off"

    def thinking_params(self):
        """Provider-native reasoning switch (only when the user set a level and style allows it)."""
        lv = self.thinking_level()
        if lv == "off" or self.cfg.get("thinking_style", "auto") == "prompt":
            return {}
        t, base = self.provider.api_type, (self.cfg.get("base_url") or "").lower()
        budget = {"low": 1024, "medium": 4096, "high": 12000}[lv]
        if t == "anthropic":
            return {"thinking": {"type": "enabled", "budget_tokens": budget}}
        if t == "gemini":
            return {"generationConfig": {"thinkingConfig": {"thinkingBudget": budget, "includeThoughts": True}}}
        if t == "ollama":
            return {"think": lv if "gpt-oss" in str(self.cfg.get("model")).lower() else True}
        if "openrouter" in base:
            return {"reasoning": {"effort": lv}}
        return {"reasoning_effort": lv}

    def thinking_prompt(self):
        """Self-thinking for ANY model: short private notes in <think> tags before acting."""
        lv = self.thinking_level()
        style = self.cfg.get("thinking_style", "auto")
        if lv == "off" or style == "native" or (style == "auto" and self.thinking_params()):
            return ""
        words = {"low": 60, "medium": 150, "high": 400}[lv]
        return (f"THINKING ({lv}): before you act, think inside <think>...</think> (private notes, at most {words} "
                "words): what is asked, what the project map already tells you, the next concrete step, and what "
                "could go wrong. Then act (call tools). Never put code in the thinking block.")

    def _maybe_auto_compact(self):
        limit = int(self.cfg.get("auto_compact_tokens", 50000) or 0)
        if not limit or len(self.messages) < 14:
            return
        if est_tokens(self._slim(self.messages)) > limit:
            console.print("[dim]Context is large: summarising older history to save tokens...[/]")
            try:
                self.compact()
            except Exception as e:
                console.print(f"[dim]Auto-compact skipped: {escape(str(e)[:100])}[/]")

    def _record_usage(self):
        u = self.provider.last_usage or {}
        self.usage["calls"] += 1
        self.usage["prompt"] += int(u.get("prompt_tokens") or self.ctx_tokens)
        self.usage["completion"] += int(u.get("completion_tokens") or 0)
        self.usage["reported"] = self.usage["reported"] or bool(u)

    def call_model(self):
        compacted, retries = False, 0
        self._maybe_auto_compact()
        while True:
            native = self.native()
            tools = [t.schema() for t in self.tools.values()] if native else None
            self.provider.extra_body = self.thinking_params()
            status = console.status("[yellow]Thinking...[/]", spinner="dots")
            renderer = StreamRenderer(hide_tool_xml=not native, on_first=status.stop,
                                      on_live_open=self._live_open,
                                      on_fence_open=self._fence_open, on_fence_done=self._fence_done,
                                      autosave=self.cfg.get("mode", "auto") != "ask",
                                      show_thinking=self.cfg.get("show_thinking", True))
            status.start()
            try:
                msgs = self.build_messages()
                self.ctx_tokens = est_tokens(msgs)
                resp = self.provider.chat(msgs, tools, renderer)
                renderer.finish()
            except ProviderError as e:
                status.stop()
                renderer.finish()
                body = e.body.lower()
                if self.provider.extra_body and e.status in (400, 422) and re.search(THINK_ERR_RX, body):
                    console.print("[yellow]This provider does not accept the thinking setting. "
                                  "Using prompt-based thinking instead.[/]")
                    self.cfg.set("thinking_style", "prompt")
                    self.cfg.save()
                    continue
                if native and e.status in (400, 422) and ("tool" in body or "function" in body):
                    console.print("[yellow]This model does not support native tool calling. "
                                  "Switching to prompt-based tools.[/]")
                    self.cfg.set("tool_mode", "prompt")
                    self.cfg.save()
                    continue
                if e.transient() and not renderer.started and retries < 3:
                    wait = (2, 5, 10)[retries]
                    retries += 1
                    console.print(f"[yellow]Provider is busy or unavailable. Retrying in {wait}s ({retries}/3)...[/]")
                    time.sleep(wait)
                    continue
                if not compacted and e.status in (400, 413, 422, 0) and is_context_error(e.body):
                    console.print("[yellow]Context too long. Compacting history...[/]")
                    compacted = True
                    self.compact()
                    continue
                raise
            finally:
                status.stop()
            self._record_usage()
            resp["content"] = strip_think(resp["content"])
            if not resp["tool_calls"]:
                resp = self._text_calls(resp)
            return resp

    def _text_calls(self, resp):
        """Weak models often write the tool call as text; recognise it and run it anyway."""
        text = resp["content"]
        if not text or ("{" not in text):
            return resp
        calls, clean = extract_text_tool_calls(text, set(self.tools))
        if not calls:
            return resp
        tcs = [{"id": "call_" + uuid.uuid4().hex[:12], "type": "function",
                "function": {"name": n, "arguments": json.dumps(a)}} for n, a in calls]
        return {**resp, "content": clean, "tool_calls": tcs}

    def compact(self, manual=False, keep=6):
        """Summarise old history, keep the most recent messages untouched. Files, notes and the project
        map are re-injected every turn, so the summary only needs goals, decisions and state."""
        msgs = self.messages
        cut = len(msgs) - keep
        while cut > 0 and msgs[cut]["role"] == "tool":   # never separate a tool result from its call
            cut -= 1
        if cut <= 1:
            for m in msgs:
                if m["role"] == "tool" and len(m["content"]) > 2000:
                    m["content"] = truncate(m["content"], 2000)
            self.save()
            if manual:
                console.print("[dim]Nothing to summarize yet (trimmed long tool outputs).[/]")
            return
        lines = []
        for m in msgs[:cut]:
            c = m.get("content") or ""
            if m["role"] == "assistant" and m.get("tool_calls"):
                c += " [tools: " + ", ".join(f"{t['function']['name']}({t['function']['arguments'][:160]})"
                                             for t in m["tool_calls"]) + "]"
            lines.append(f"{m['role'].upper()}: {truncate(c, 1200)}")
        last_req = next((m["content"] for m in reversed(msgs) if m["role"] == "user"
                         and m.get("content") and not m["content"].startswith("[MIVO]")), "")
        prompt = ("Summarize this coding session in under 350 words so work can continue seamlessly: goals, "
                  "decisions, conventions, what each file does, current state, open problems, next steps. "
                  "End with a line 'CURRENT REQUEST:' that copies the user's latest request word for word.\n"
                  f"(Latest request: {truncate(last_req, 600)})\n\n" + "\n".join(lines))
        saved, self.provider.extra_body = self.provider.extra_body, {}
        try:
            with console.status("[yellow]Compacting...[/]"):
                summary = strip_think(self.provider.complete([{"role": "user", "content": prompt}]))
        finally:
            self.provider.extra_body = saved
        self.messages = ([{"role": "user", "content": "[Summary of the earlier conversation]\n" + summary},
                          {"role": "assistant", "content": "Understood. I have the context and will continue."}]
                         + msgs[cut:])
        self.read_cache.clear()
        self.save()
        console.print(f"[dim]History compacted ({cut} messages summarised).[/]")

    # ---- tool execution
    def show_call(self, name, args):
        if self.events:
            self.events("tool", name, args)
        s = args.get("command") or args.get("path") or args.get("pattern") or args.get("url") \
            or args.get("name") or args.get("action") or args.get("query") or args.get("note") \
            or next((v for v in args.values() if isinstance(v, str)), "") or ""
        console.print(f"[brand]●[/] [bold]{escape(name)}[/] [dim]{escape(str(s).splitlines()[0][:100] if s else '')}[/]")

    def show_result(self, out):
        lines = out.splitlines() or [""]
        for i, l in enumerate(lines[:5]):
            console.print(Text(("  ⎿ " if i == 0 else "    ") + l[:160], style="dim"))
        if len(lines) > 5:
            console.print(Text(f"    … +{len(lines) - 5} lines", style="dim"))

    def confirm(self, tool, args, level, keys, note):
        """Ask the user. Returns (allowed, reason). One keypress, Enter = yes."""
        if self.confirm_hook:   # remote approval (Telegram buttons)
            return self.confirm_hook(tool, args, level, keys, note)
        title, body = (tool.preview(args) if tool.preview else
                       (f"Run {tool.name}", Text(json.dumps(args, ensure_ascii=False, indent=2)[:1500])))
        if level == "danger":
            console.print(Panel(body, title="[bold red]⚠ DANGEROUS — " + escape(title) + "[/]", border_style="red"))
            try:
                return input("Type 'yes' to run, anything else cancels: ").strip().lower() == "yes", ""
            except (EOFError, KeyboardInterrupt):
                return False, ""
        sub = f" [{note}]" if note else ""
        console.print(Panel(body, title=escape(title) + sub, border_style="brand"))
        choices = {"y": "y", "Y": "y", "1": "y", "n": "n", "N": "n", "t": "n", "T": "n"}
        if keys:
            choices.update({"a": "a", "A": "a", "2": "a", "3": "n"})
            legend = "[Y]es / [A]lways / [N]o"
        else:
            choices.update({"2": "n"})
            legend = "[Y]es / [N]o"
        ans = ask_choice([("ansiyellow bold", "Allow? "), ("", legend + " ")], choices, "y")
        if ans == "n":
            console.print("[red]✗ no[/]")
            try:
                return False, input("Instead (optional): ").strip()
            except (EOFError, KeyboardInterrupt):
                return False, ""
        if ans == "a" and keys:
            self.allowed.update(keys)
            self.cfg.data["always_allow"] = sorted(self.allowed)   # remembered next time too
            self.cfg.save()
        console.print("[green]✓ yes[/]" if ans == "y" else "[green]✓ always[/]")
        return True, ""

    def snapshot(self, p):
        """Back up a file before it changes so /undo can restore it."""
        bk = None
        if p.is_file():
            d = MIVO_HOME / "backups" / self.session_id
            try:
                d.mkdir(parents=True, exist_ok=True)
                bk = d / f"{len(self.undo_stack)}_{p.name}"
                shutil.copy2(p, bk)
            except OSError:
                bk = None
        self.undo_stack.append((str(p), str(bk) if bk else None))

    def _live_open(self, p, existed):
        if p.suffix.lower() in RUNNABLE_EXT:
            self.turn_wrote_code, self.turn_ran = True, False
        self.snapshot(p)
        self.live_info[str(p)] = existed
        self._map = None

    def _fence_open(self, p, existed):
        if p.suffix.lower() in RUNNABLE_EXT:
            self.turn_wrote_code, self.turn_ran = True, False
        self.snapshot(p)
        self.fence_existed[str(p)] = existed
        self._map = None

    def _fence_done(self, p):
        self.record_change("rewrote" if self.fence_existed.pop(str(p), True) else "created", p)
        self._map = None

    def record_change(self, op, p):
        try:
            n = len(p.read_text("utf-8", "replace").splitlines())
        except OSError:
            n = 0
        self.ledger = [e for e in self.ledger if e["path"] != rel(p)]
        self.ledger.append({"op": op, "path": rel(p), "lines": n, "t": datetime.now().strftime("%H:%M")})
        self.ledger = self.ledger[-60:]

    def memory_context(self):
        parts = []
        notes = read_notes()
        if notes:
            parts.append("PROJECT NOTES (saved earlier with `remember`):\n" + notes)
        if self.ledger:
            rows = "\n".join(f"- {e['op']} {e['path']} ({e['lines']} lines, {e['t']})"
                             for e in reversed(self.ledger[-25:]))
            parts.append("FILES YOU CHANGED this session (newest first):\n" + rows)
        cwd = os.getcwd()
        if not self._map or self._map[0] != cwd or time.time() - self._map[1] > 30:
            hint = next((m["content"] for m in reversed(self.messages) if m["role"] == "user"
                         and m.get("content") and not m["content"].startswith("[MIVO]")), "")
            focus = {e["path"] for e in self.ledger[-10:]}
            self._map = (cwd, time.time(), project_map(cwd, hint=hint, focus=focus))   # rescanned only after a change
        parts.append("PROJECT MAP (live from disk, right now):\n" + self._map[2])
        return parts

    def exec_tool(self, name, args):
        if self.cancel:
            raise KeyboardInterrupt
        tool = self.tools.get(name)
        if not tool:
            return f"Error: unknown tool '{name}'"
        if args is None:
            return "Error: arguments were not valid JSON (if you were writing a file, it may be incomplete: resend it)"
        args = normalize_args(tool, args)
        p, live, existed = None, False, None
        if name in ("write_file", "edit_file", "multi_edit") and isinstance(args.get("path"), str):
            p = resolve(args["path"])
            if name == "write_file" and str(p) in self.live_info:
                live, existed = True, self.live_info.pop(str(p))
            else:
                existed = p.exists()
        if not live:
            self.show_call(name, args)
        try:
            level, keys, note = tool.perm(args)
        except Exception as e:
            return f"Error: {e}"
        mode = self.cfg.get("mode", "auto")
        if mode == "yolo" and level == "ask":
            level = "safe"
        elif mode == "ask" and level == "safe":
            if name == "bash" and not is_read_only(args.get("command", "")):
                level, keys = "ask", command_names(args.get("command", ""))
            elif name in ("write_file", "edit_file"):
                level, keys = "ask", ["write"]
        if level == "danger" or (level == "ask" and not (keys and all(k in self.allowed for k in keys))):
            ok, why = self.confirm(tool, args, level, keys, note)
            if not ok:
                return DENIED + (f" The user says: {why}" if why else "")
        diff = None
        if name in ("edit_file", "multi_edit"):
            try:
                diff = (preview_edit if name == "edit_file" else preview_multi)(args)[1]
            except Exception:
                diff = None
        mark = len(self.undo_stack)
        if p is not None and not live:
            self.snapshot(p)
        rkey, out = None, None
        if name == "read_file":   # an unchanged file that is still in recent context is not sent again
            try:
                rp = resolve(args["path"])
                rkey = (str(rp), rp.stat().st_mtime_ns, int(args.get("offset", 1)), int(args.get("limit", 400)))
                if len(self.messages) - self.read_cache.get(rkey, -99) <= 7:
                    out = "[unchanged since your last read a moment ago; its content is already in the conversation above]"
            except (OSError, KeyError, ValueError):
                rkey = None
        used_bin = False
        if name == "bash" and out is None and self.cfg.get("rtk", "auto") == "auto" and rtk_binary():
            rew = rtk_rewrite(args.get("command", ""))
            if rew:
                rew = shlex.quote(rtk_binary()) + rew[3:]
                try:
                    cand = t_bash({**args, "command": rew})
                    if not re.search(r"\[exit code 127\]|unrecognized subcommand|Usage: rtk|rtk: error", cand[-500:]):
                        out, used_bin = cand, True
                except KeyboardInterrupt:
                    raise
                except Exception:
                    out = None
        if out is None:
            try:
                out = tool.func(args)
            except KeyboardInterrupt:
                raise
            except KeyError as e:
                req = ", ".join(tool.parameters.get("required", []))
                out = f"Error: missing argument {e}. Usage: {name} {{{req}}}"
            except Exception as e:
                out = f"Error: {type(e).__name__}: {e}"
            if rkey and not str(out).startswith("Error"):
                self.read_cache[rkey] = len(self.messages)
        out = str(out)
        if name == "bash":
            self.turn_ran = True
            if not used_bin and not args.get("raw"):
                out = self.rtk_filter(args.get("command", ""), out)
        out = truncate(out)
        if name not in READ_ONLY:
            self._map = None
        ok = out.startswith(("Wrote", "Edited"))
        if p is not None and not live and not ok:
            del self.undo_stack[mark:]   # nothing changed
        if p is not None and ok and p.suffix.lower() in RUNNABLE_EXT:
            self.turn_wrote_code, self.turn_ran = True, False
        if p is not None and ok:
            self.record_change("rewrote" if existed else "created" if name == "write_file" else "edited", p)
        self.show_result(out)
        if diff is not None and out.startswith("Edited"):
            console.print(diff)
        return out

    # ---- main loop
    def run_turn(self, text):
        self.messages.append({"role": "user", "content": text})
        for old in self.messages[:-1]:
            old.pop("_thinking", None)   # thinking blocks are only needed inside the current tool loop
        self._map = None
        self.turn_wrote_code, self.turn_ran, self._sigs = False, False, []
        self.cancel = False
        base_len = len(self.messages)
        try:
            steps, nudges, max_steps = 0, 0, int(self.cfg.get("max_steps", 80))
            while True:
                steps += 1
                if steps > max_steps:
                    console.print("[yellow]Step limit reached. Say 'continue' to keep going.[/]")
                    break
                resp = self.call_model()
                if self.cancel:
                    raise KeyboardInterrupt
                msg = {"role": "assistant", "content": resp["content"] or ""}
                if resp["tool_calls"]:
                    msg["tool_calls"] = resp["tool_calls"]
                if resp.get("thinking_blocks"):
                    msg["_thinking"] = resp["thinking_blocks"]
                self.messages.append(msg)
                self.save()
                if not resp["tool_calls"]:
                    if (self.cfg.get("verify_nudge", True) and nudges < 1
                            and self.turn_wrote_code and not self.turn_ran):
                        nudges += 1   # once: make the AI actually run what it wrote
                        console.print("[dim]↻ checking that the code runs...[/]")
                        self.messages.append({"role": "user", "content": VERIFY_MSG})
                        continue
                    break
                interrupted = False
                for tc in resp["tool_calls"]:
                    if interrupted:
                        result = "[skipped: interrupted by user]"
                    else:
                        name, raw = tc["function"]["name"], tc["function"]["arguments"]
                        sig = name + "|" + raw
                        if self._sigs[-2:] == [sig, sig]:   # same call three times in a row = a loop
                            result = LOOP_MSG
                            console.print("[dim]⟳ blocked a repeated identical call[/]")
                        else:
                            self._sigs.append(sig)
                            try:
                                result = self.exec_tool(name, json_loads_safe(raw))
                            except KeyboardInterrupt:
                                interrupted = True
                                result = "[interrupted by user]"
                                console.print("\n[dim]Interrupted.[/]")
                    self.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                self.save()
                if interrupted:
                    break
        except BaseException:
            if len(self.messages) == base_len:  # failed before any reply: drop dangling prompt
                self.messages.pop()
            self.save()
            raise
        console.print()

    # ---- slash commands
    def _register_commands(self):
        c = self.commands
        c["help"] = (self.cmd_help, "Show this help")
        c["riwayat"] = (self.cmd_history, "Browse and restore previous chats (alias: /history)")
        c["history"] = (self.cmd_history, "")
        c["new"] = (self.cmd_new, "Start a fresh chat (memory cleared, old chat stays in /riwayat)")
        c["clear"] = (lambda a: console.clear(), "Clear the screen")
        c["compact"] = (lambda a: self.compact(manual=True), "Summarize history to free context")
        c["cd"] = (self.cmd_cd, "Change working directory")
        c["model"] = (self.cmd_model, "Show or change the model id")
        c["config"] = (self.cmd_config, "Re-run API setup")
        c["addweb"] = (self.cmd_addweb, "Add web search (API key, Base URL, browser model); /addweb off")
        c["prefensi"] = (self.cmd_prefensi, "Add your own instructions / system prompt for the AI")
        c["prompt"] = (self.cmd_prefensi, "")
        c["instruksi"] = (self.cmd_prefensi, "")
        c["mode"] = (self.cmd_mode, "Permission mode: auto | ask | yolo  (Shift+Tab cycles)")
        c["thinking"] = (self.cmd_thinking, "AI thinking: off | low | medium | high  (show | hide)")
        c["usage"] = (self.cmd_usage, "Token usage and context size")
        c["addbot"] = (self.cmd_addbot, "Telegram bot: talk to the AI (and run commands) from Telegram")
        c["mcp"] = (self.cmd_mcp, "MCP servers: list | tools | add | remove | trust | restart")
        c["theme"] = (self.cmd_theme, "Colors: android | ocean | sunset | grape | mono")
        c["apitype"] = (self.cmd_apitype, "Provider protocol: auto | openai | anthropic | gemini | ollama | azure")
        c["rtk"] = (self.cmd_rtk, "Output compaction (RTK): on | builtin | off | gain | recall <id>")
        c["caveman"] = (self.cmd_caveman, "Terse replies, fewer output tokens: lite | full | ultra | wenyan | off")
        c["ponytail"] = (self.cmd_ponytail, "Minimal-code mode: lite | full | ultra | off")
        c["ponytail-review"] = (self.cmd_ponytail_review, "Find code to delete in your uncommitted diff")
        c["ponytail-audit"] = (self.cmd_ponytail_audit, "Audit the project for over-engineering")
        c["ponytail-debt"] = (self.cmd_ponytail_debt, "List `ponytail:` shortcut markers in your code")
        c["ponytail-gain"] = (self.cmd_ponytail_gain, "Lines the AI wrote this session")
        c["ponytail-help"] = (self.cmd_ponytail_help, "")
        c["context7"] = (self.cmd_context7, "Library docs (Context7): key | on | off | test")
        c["docs"] = (self.cmd_docs, "Fetch current docs: /docs <library> <question>")
        c["compress"] = (self.cmd_compress, "Shrink saved project notes (caveman-compress)")
        c["izin"] = (self.cmd_izin, "Show always-allowed actions; /izin reset")
        c["undo"] = (self.cmd_undo, "Undo the last file change made by the AI")
        c["memory"] = (self.cmd_memory, "Show project notes and changed files; /memory clear")
        c["fullscreen"] = (self.cmd_fullscreen, "Termux fullscreen: /fullscreen on | off")
        c["skills"] = (self.cmd_skills, "List installed skills")
        c["plugins"] = (self.cmd_plugins, "List loaded plugins and tools")
        c["exit"] = (lambda a: sys.exit(0), "Quit")
        c["quit"] = (lambda a: sys.exit(0), "")

    def cmd_help(self, arg):
        t = Table(show_header=False, box=None, padding=(0, 2))
        for name, (_, h) in sorted(self.commands.items()):
            if h:
                t.add_row(f"[yellow]/{name}[/]", h)
        t.add_row("[yellow]!cmd[/]", "Run a shell command directly (no AI)")
        t.add_row("[yellow]Ctrl+C[/]", "Stop the current response / command")
        console.print(t)

    def cmd_new(self, arg):
        self.save()
        self.messages, self.ledger, self.undo_stack = [], [], []
        self.session_id = new_session_id()
        self.created = datetime.now().isoformat(timespec="seconds")
        console.print("[dim]New chat started.[/]")

    def cmd_cd(self, arg):
        p = Path(os.path.expanduser(arg.strip() or "~"))
        p = p if p.is_absolute() else Path(os.getcwd()) / p
        if p.is_dir():
            os.chdir(p)
            console.print(f"[dim]$ cd {p}[/]")
        else:
            console.print(f"[red]Not a directory: {p}[/]")

    def cmd_model(self, arg):
        arg = arg.strip()
        if not arg:
            console.print(f"Current model: [bold]{escape(self.cfg.get('model'))}[/]")
            try:
                arg = input("New model id (Enter to keep): ").strip()
            except (EOFError, KeyboardInterrupt):
                return
        if arg:
            self.cfg.set("model", arg)
            self.cfg.save()
            console.print(f"[dim]Model set to {escape(arg)}[/]")

    def cmd_config(self, arg):
        run_setup(self.cfg)

    def cmd_fullscreen(self, arg):
        if not is_termux():
            console.print("[dim]Only available inside Termux.[/]")
            return
        want = arg.strip().lower()
        if want not in ("on", "off"):
            console.print("Usage: /fullscreen on | off")
            return
        set_termux_fullscreen(want == "on")
        self.cfg.set("fullscreen", want == "on")
        self.cfg.set("fullscreen_applied", want == "on")
        self.cfg.set("fullscreen_v2", True)
        self.cfg.save()
        console.print(f"[dim]Fullscreen {want}. Restart Termux to apply.[/]")

    def apply_web_tool(self):
        ws = self.cfg.data.get("web_search") or {}
        if not (ws.get("base_url") and ws.get("model")):
            self.tools.pop("web_search", None)
            return
        self.tools["web_search"] = Tool(
            "web_search", "Search the web for current information, docs, versions and error messages.",
            obj({"query": {"type": "string"}}, ["query"]),
            lambda a: web_search_run(self.cfg.data["web_search"], a["query"]))

    def cmd_addweb(self, arg):
        if arg.strip().lower() in ("off", "remove", "delete"):
            self.cfg.data.pop("web_search", None)
            self.cfg.save()
            self.apply_web_tool()
            console.print("[dim]Web search removed.[/]")
            return
        cur = self.cfg.data.get("web_search", {})
        key = ask_text("API key", cur.get("api_key"), secret=True)
        base = normalize_base_url(ask_text("Base URL", cur.get("base_url")), "openai")
        model = ask_text("Model ID (browser)", cur.get("model"))
        ws = {"api_key": key, "base_url": base, "model": model}
        try:
            with console.status("[yellow]Testing web search...[/]"):
                res = web_search_run(ws, "What is the latest stable Python version? Answer in one line.")
            console.print("[green]✓ Web search works[/]  [dim]" + escape(res.splitlines()[0][:90]) + "[/]")
        except Exception as e:
            console.print(f"[red]✗ {escape(str(e)[:200])}[/]")
            if input("Save anyway? [y/N]: ").strip().lower() != "y":
                return
        self.cfg.data["web_search"] = ws
        self.cfg.save()
        self.apply_web_tool()
        console.print("[dim]The AI can now use web_search.[/]")

    def cmd_prefensi(self, arg):
        inst = self.cfg.data.get("instructions", "")
        sysp = self.cfg.data.get("system_prompt", "")
        choice = arg.strip()
        if not choice:
            console.print("[bold]Preferences[/] — instructions and prompts for the AI")
            console.print(f"  1  Custom instructions  [dim]{f'{len(inst)} chars' if inst else 'empty'}[/]")
            console.print(f"  2  System prompt        [dim]{f'custom, {len(sysp)} chars' if sysp else 'default'}[/]")
            console.print("  3  View the full prompt the AI receives")
            console.print("  4  Reset both")
            try:
                choice = input("Choose 1-4: ").strip()
            except (EOFError, KeyboardInterrupt):
                return
        if choice == "1":
            text = read_multiline("Custom instructions: added to every request and applied on top of the defaults.")
            if text is None:
                return
            self.cfg.set("instructions", text)
        elif choice == "2":
            text = read_multiline("System prompt: REPLACES the default one (you can use {cwd} and {env}). "
                                  "Empty = back to the default.")
            if text is None:
                return
            self.cfg.set("system_prompt", text)
        elif choice == "3":
            console.print(Panel(Text(self.system_prompt().replace(DYN_MARK, "\n\n")[:8000]), title="System prompt", border_style="brand"))
            return
        elif choice == "4":
            self.cfg.data.pop("instructions", None)
            self.cfg.data.pop("system_prompt", None)
        else:
            return
        self.cfg.save()
        console.print("[green]✓ Saved.[/] [dim]Applies from the next message.[/]")

    def cycle_mode(self):
        order = ["ask", "auto", "yolo"]
        cur = self.cfg.get("mode", "auto")
        self.cfg.set("mode", order[(order.index(cur) + 1) % 3] if cur in order else "auto")
        self.cfg.save()

    def cmd_mode(self, arg):
        want = arg.strip().lower()
        if want in MODES:
            self.cfg.set("mode", want)
            self.cfg.save()
            console.print(f"[green]✓ Mode: {want}[/] [dim]{MODES[want]}[/]")
            return
        cur = self.cfg.get("mode", "auto")
        for m, d in MODES.items():
            console.print(f"  {'[green]●[/]' if m == cur else ' '} [bold]{m:5}[/] [dim]{d}[/]")
        console.print("[dim]Change with /mode auto | ask | yolo[/]")

    def cmd_thinking(self, arg):
        parts = arg.lower().split()
        if not parts:
            lv, st = self.thinking_level(), self.cfg.get("thinking_style", "auto")
            how = ("provider reasoning" if self.thinking_params() else "<think> notes" if lv != "off" else "-")
            console.print(f"Thinking: [bold]{lv}[/]  style: {st}  via: {how}  "
                          f"text shown: {'yes' if self.cfg.get('show_thinking', True) else 'no'}")
            console.print("[dim]/thinking off|low|medium|high [native|prompt]   /thinking show|hide[/]")
            console.print("[dim]Reasoning is displayed but never stored or re-sent, so it does not eat context.[/]")
            return
        for w in parts:
            if w in ("off", "low", "medium", "high"):
                self.cfg.set("thinking", w)
            elif w in ("on", "auto"):
                self.cfg.set("thinking", "medium")
            elif w in ("native", "prompt"):
                self.cfg.set("thinking_style", w)
            elif w in ("show", "hide"):
                self.cfg.set("show_thinking", w == "show")
            else:
                console.print(f"[red]Unknown option: {escape(w)}[/]")
                return
        self.cfg.save()
        console.print(f"[green]✓ Thinking: {self.thinking_level()}[/] [dim]({self.cfg.get('thinking_style', 'auto')})[/]")

    def cmd_usage(self, arg):
        u = self.usage
        note = "reported by the provider" if u["reported"] else "estimated (provider reports no usage)"
        console.print(f"Context now: ~{self.ctx_tokens:,} tokens  ·  requests: {u['calls']}")
        console.print(f"Session total: {u['prompt']:,} in / {u['completion']:,} out  [dim]({note})[/]")
        lim = int(self.cfg.get("auto_compact_tokens", 50000) or 0)
        console.print(f"[dim]Older history is summarised automatically above ~{lim:,} tokens "
                      f"(config: auto_compact_tokens, 0 = off). /compact does it now.[/]" if lim else
                      "[dim]Auto-compaction is off. /compact summarises history now.[/]")

    # ---- MCP servers
    def start_mcp(self):
        self.mcp = {}
        if os.environ.get("MIVO_NO_MCP"):
            return
        ensure_mcp_config()
        for name, spec in load_mcp_servers(self.c7_key()).items():
            self._boot_mcp(name, spec)

    def _boot_mcp(self, name, spec):
        cl = McpClient(name, spec)
        self.mcp[name] = cl

        def boot():
            cl.connect(timeout=90 if cl.kind == "stdio" else 30)
            if cl.status == "ready":
                self.register_mcp_tools(cl)
        threading.Thread(target=boot, daemon=True).start()

    def register_mcp_tools(self, cl):
        new = {}
        for t in cl.tools:
            real = t.get("name", "")
            tname = mcp_tool_name(cl.name, real)
            schema = slim_schema(t.get("inputSchema") or {"type": "object", "properties": {}})
            if schema.get("type") != "object":
                schema = {"type": "object", "properties": {}}
            desc = f"[{cl.name}] " + " ".join(str(t.get("description") or t.get("title") or "").split())[:300]
            perm = (lambda a, n=cl.name, tr=cl.trusted: ("safe", None, "") if tr else ("ask", [f"mcp:{n}"], ""))
            prev = (lambda a, n=tname: (f"MCP {n}", Text(json.dumps(a, ensure_ascii=False)[:1500])))
            new[tname] = Tool(tname, desc, schema, (lambda a, c=cl, r=real: c.call(r, a)), perm, prev)
        with self._tools_lock:
            tools = dict(self.tools)
            tools.update(new)
            if cl.name == "context7" and new:   # the MCP docs tools replace the REST fallback
                tools.pop("lib_docs", None)
                tools.pop("lib_search", None)
            self.tools = tools

    def drop_mcp_tools(self, name):
        with self._tools_lock:
            self.tools = {k: v for k, v in self.tools.items() if not k.startswith(f"mcp__{name}__")}

    def mcp_counts(self):
        return sum(1 for c in self.mcp.values() if c.status == "ready"), len(self.mcp)

    def wait_mcp(self, seconds=3.0):
        end = time.time() + seconds
        while time.time() < end and any(c.status == "starting" for c in self.mcp.values()):
            time.sleep(0.1)

    def close_mcp(self):
        for c in list(self.mcp.values()):
            c.close()

    def cmd_mcp(self, arg):
        try:
            parts = shlex.split(arg)
        except ValueError:
            parts = arg.split()
        sub = parts[0].lower() if parts else "list"
        file_servers = read_mcp_file()
        if sub in ("list", "status"):
            if not self.mcp:
                console.print("[muted]No MCP servers. Add one: /mcp add <name> <url | command args...> [--trust][/]")
            for n, c in self.mcp.items():
                st = {"ready": "[ok]✓ ready[/]", "starting": "[warn]… starting[/]"}.get(c.status, f"[err]✗ {escape(c.error)}[/]")
                console.print(f"  [bold]{escape(n):12}[/] {c.kind:5}  {st}  [muted]{len(c.tools)} tools"
                              f"{' · trusted' if c.trusted else ' · asks before use'}[/]")
            console.print("[muted]/mcp tools [name] · add · remove <name> · trust <name> on|off · restart [name][/]")
        elif sub == "tools":
            for k, t in self.tools.items():
                if k.startswith("mcp__") and (len(parts) < 2 or k.startswith(f"mcp__{parts[1]}__")):
                    console.print(f"  {escape(k)}  [muted]{escape(t.description[:80])}[/]")
        elif sub == "add" and len(parts) >= 3:
            name, rest = parts[1], parts[2:]
            trust = "--trust" in rest
            rest = [x for x in rest if x != "--trust"]
            headers = {}
            while "--header" in rest:
                i = rest.index("--header")
                if i + 1 < len(rest) and "=" in rest[i + 1]:
                    k, _, v = rest[i + 1].partition("=")
                    headers[k] = v
                del rest[i:i + 2]
            spec = {"url": rest[0]} if re.match(r"^https?://", rest[0]) else {"command": rest[0], "args": rest[1:]}
            if headers:
                spec["headers"] = headers
            if trust:
                spec["trust"] = True
            file_servers[name] = spec
            write_mcp_file(file_servers)
            self.drop_mcp_tools(name)
            self._boot_mcp(name, load_mcp_servers(self.c7_key()).get(name, spec))
            console.print(f"[ok]✓[/] Added [bold]{escape(name)}[/]. Connecting in the background: /mcp to see the status.")
        elif sub in ("remove", "rm") and len(parts) >= 2:
            name = parts[1]
            if name in MCP_DEFAULTS:
                file_servers[name] = {"disabled": True}
            else:
                file_servers.pop(name, None)
            write_mcp_file(file_servers)
            if name in self.mcp:
                self.mcp.pop(name).close()
            self.drop_mcp_tools(name)
            if name == "context7":
                self.apply_c7_tools()
            console.print(f"[ok]✓[/] Removed {escape(name)}")
        elif sub == "trust" and len(parts) >= 3:
            name = parts[1]
            spec = dict(file_servers.get(name) or MCP_DEFAULTS.get(name) or {})
            if not spec:
                console.print("[err]Unknown server[/]")
                return
            spec["trust"] = parts[2].lower() == "on"
            file_servers[name] = spec
            write_mcp_file(file_servers)
            if name in self.mcp:
                self.mcp[name].spec["trust"] = spec["trust"]
            self.drop_mcp_tools(name)
            if name in self.mcp and self.mcp[name].status == "ready":
                self.register_mcp_tools(self.mcp[name])
            console.print(f"[ok]✓[/] {escape(name)} trust {'on' if spec['trust'] else 'off'}")
        elif sub == "restart":
            names = [parts[1]] if len(parts) > 1 else list(self.mcp)
            servers = load_mcp_servers(self.c7_key())
            for n in names:
                if n in self.mcp:
                    self.mcp.pop(n).close()
                self.drop_mcp_tools(n)
                if n in servers:
                    self._boot_mcp(n, servers[n])
            console.print("[muted]Restarting...[/]")
        else:
            console.print("[muted]/mcp · /mcp tools [name] · /mcp add <name> <url | command args...> [--trust] "
                          "[--header K=V] · /mcp remove <name> · /mcp trust <name> on|off · /mcp restart [name][/]")

    # ---- Telegram bot (/addbot)
    def cmd_addbot(self, arg):
        parts = arg.split()
        sub = parts[0].lower() if parts else ""
        if sub:
            return self._addbot_sub(sub, parts[1:])
        t = tg_cfg(self.cfg)
        token = ask_text("Bot token", t.get("token"), secret=True, step=(1, 1),
                         hint="Create a bot with @BotFather and paste its token. Every character is hidden as *")
        with console.status("[brand]Verifying token...[/]"):
            ok, info = tg_verify(token, self.cfg.data.get("telegram_api"))
        if not ok:
            _panel(f"[err]✗[/] {escape(str(info))}", "[err]Could not connect[/]", "err")
            return
        same = t.get("token") == token
        keep = t if same else {}
        users = keep.get("allowed_users", [])
        code = "" if users else f"{secrets.randbelow(10 ** 6):06d}"
        self.cfg.data["telegram"] = {
            "token": token, "bot_id": info.get("id"), "name": info.get("first_name", ""),
            "username": info.get("username", ""), "allowed_users": users, "pair_code": code,
            "pair_expires": time.time() + 900 if code else 0, "mode": keep.get("mode", "auto"),
            "cwd": keep.get("cwd", ""), "enabled": True}
        self.cfg.save()
        if not same:
            stop_bot()
        started, msg = start_bot()
        lines = [f"[bold]{escape(info.get('first_name', ''))}[/]", f"[brand]@{escape(info.get('username', ''))}[/]",
                 "[ok]Connected[/]" if started else f"[warn]Token OK, but the background process did not start: {escape(msg)}[/]"]
        if not started:
            lines.append("[muted]Run it by hand: mivo bot[/]")
        if code:
            lines.append(f"[muted]Pair your account: send[/] [bold]/pair {code}[/] [muted]to @{escape(info.get('username', ''))} (15 min)[/]")
        else:
            lines.append(f"[muted]{len(users)} paired account(s). Add another: /addbot pair[/]")
        _panel("\n".join(lines), "[ok]✓ Telegram bot[/]", "ok")
        try:
            pt_prompt([(pt_brand(), "❯ ")])    # Enter closes
        except (EOFError, KeyboardInterrupt):
            pass

    def _addbot_sub(self, sub, rest):
        t = tg_cfg(self.cfg)
        if sub == "help" or (not t.get("token") and sub != "help"):
            if not t.get("token"):
                console.print("[muted]No bot yet. Run /addbot and paste the token from @BotFather.[/]")
                return
        c = self.cfg.data.setdefault("telegram", {})
        if sub == "status":
            pid = bot_running()
            log = MIVO_HOME / "bot.log"
            tail = log.read_text("utf-8", "replace").strip().splitlines()[-4:] if log.exists() else []
            body = (f"[bold]{escape(t.get('name', ''))}[/] [brand]@{escape(t.get('username', ''))}[/]\n"
                    f"{'[ok]● running[/] (pid ' + str(pid) + ')' if pid else '[warn]○ stopped[/]'}   mode: {t.get('mode', 'auto')}\n"
                    f"paired accounts: {len(t.get('allowed_users') or [])} {t.get('allowed_users') or ''}\n"
                    f"folder: {escape(t.get('cwd') or 'home')}")
            if tail:
                body += "\n[muted]" + escape("\n".join(x[:110] for x in tail)) + "[/]"
            _panel(body, "[brand]◆ Telegram bot[/]")
        elif sub == "pair":
            c["pair_code"], c["pair_expires"] = f"{secrets.randbelow(10 ** 6):06d}", time.time() + 900
            self.cfg.save()
            console.print(f"Send [bold]/pair {c['pair_code']}[/] to @{escape(t.get('username', ''))} within 15 minutes.")
        elif sub in ("allow", "deny") and rest and rest[0].lstrip("-").isdigit():
            users = [u for u in (c.get("allowed_users") or []) if u != int(rest[0])]
            if sub == "allow":
                users.append(int(rest[0]))
            c["allowed_users"] = users
            self.cfg.save()
            console.print(f"[ok]✓[/] {sub}: {rest[0]}")
        elif sub == "mode" and rest and rest[0] in MODES:
            c["mode"] = rest[0]
            self.cfg.save()
            console.print(f"[ok]✓[/] Telegram mode: {rest[0]} [muted]{MODES[rest[0]]}[/]")
        elif sub == "cwd" and rest:
            c["cwd"] = " ".join(rest)
            self.cfg.save()
            console.print(f"[ok]✓[/] New Telegram chats start in {escape(c['cwd'])}")
        elif sub in ("start", "restart"):
            if sub == "restart":
                stop_bot()
            c["enabled"] = True
            self.cfg.save()
            ok, msg = start_bot()
            console.print(f"[{'ok' if ok else 'warn'}]{'✓' if ok else '●'}[/] {escape(msg)}")
        elif sub == "stop":
            c["enabled"] = False
            self.cfg.save()
            console.print("[ok]✓ Stopped[/]" if stop_bot() else "[muted]It was not running.[/]")
        elif sub == "remove":
            stop_bot()
            self.cfg.data.pop("telegram", None)
            self.cfg.save()
            console.print("[ok]✓[/] Bot removed from this device. Revoke the token with @BotFather (/revoke) if you want it dead.")
        elif sub == "log":
            log = MIVO_HOME / "bot.log"
            console.print(escape("\n".join((log.read_text("utf-8", "replace").splitlines()[-25:]) if log.exists() else ["(no log yet)"])))
        else:
            console.print("[muted]/addbot · status · pair · allow <id> · deny <id> · mode auto|ask|yolo · cwd <path> · "
                          "start · stop · restart · remove · log[/]")

    # ---- theme / protocol
    def cmd_theme(self, arg):
        name = arg.strip().lower()
        if name in THEMES:
            self.cfg.set("theme", name)
            self.cfg.save()
            apply_theme(name)
            for line in render_mascot():
                console.print("  " + line)
            console.print(f"[brand]✓ Theme: {name}[/]")
            return
        cur = self.cfg.get("theme", "android")
        for n, t in THEMES.items():
            console.print(f"  {'[ok]●[/]' if n == cur else ' '} [bold {t['brand']}]{n:8}[/] {gradient('▇▇▇▇▇▇▇▇', *t['grad'])}")
        console.print("[muted]/theme <name>[/]")

    def cmd_apitype(self, arg):
        want = arg.strip().lower()
        cur = self.cfg.get("api_type", "auto")
        if want in ("auto",) + API_TYPES:
            self.cfg.set("api_type", want)
            self.cfg.set("base_url", normalize_base_url(self.cfg.data.get("base_url", ""),
                                                        None if want == "auto" else want))
            self.cfg.save()
            console.print(f"[ok]✓[/] Provider type: [bold]{self.provider.api_type}[/] [muted]({self.provider.label})[/]")
            console.print(f"[muted]  base {escape(self.provider.base)}[/]")
            return
        console.print(f"Provider type: [bold]{cur}[/] → {self.provider.api_type} ({self.provider.label})")
        console.print("[muted]/apitype auto|openai|anthropic|gemini|ollama|azure[/]")

    # ---- RTK-style compaction
    def store_recall(self, text):
        rid = uuid.uuid4().hex[:6]
        self.recall_store[rid] = text[:200000]
        while len(self.recall_store) > 20:
            self.recall_store.pop(next(iter(self.recall_store)))
        return rid

    def rtk_filter(self, cmd, out):
        if self.cfg.get("rtk", "auto") == "off":
            return out
        body, trail = split_trailer(out)
        if len(body) < 700:
            return out
        m = re.search(r"\[exit code (\d+)\]", "\n".join(trail))
        new = rtk_compact(cmd, body, int(m.group(1)) if m else 0)
        if len(new) > len(body) * 0.85:
            return out
        rid = self.store_recall(body)
        st = self.rtk_stats
        st["calls"] += 1
        st["before"] += len(body)
        st["after"] += len(new)
        note = f"[rtk: {len(body.splitlines())}→{len(new.splitlines())} lines; full output: recall {rid}]"
        return "\n".join([new, note] + trail)

    def cmd_rtk(self, arg):
        a = arg.strip().lower()
        if a.startswith("recall"):
            txt = self.recall_store.get(a.split()[-1]) if len(a.split()) > 1 else None
            console.print(Text(truncate(txt, 6000)) if txt else "[err]Unknown id[/]")
            return
        if a in ("install", "reinstall"):
            with console.status("[brand]Downloading rtk...[/]"):
                ok, msg = install_rtk()
            console.print(f"[{'ok' if ok else 'warn'}]{'✓' if ok else '●'}[/] {escape(msg)}")
        if a in ("on", "auto", "builtin", "off"):
            self.cfg.set("rtk", "auto" if a == "on" else a)
            self.cfg.save()
        mode = self.cfg.get("rtk", "auto")
        binp = rtk_binary()
        st = self.rtk_stats
        saved = st["before"] - st["after"]
        console.print(f"RTK: [bold]{mode}[/]   binary: {escape(binp) if binp else 'not installed (built-in compaction is used)'}")
        console.print(f"Compacted outputs: {st['calls']}   saved ≈ {saved // 4:,} tokens "
                      f"[muted]({st['before']:,} → {st['after']:,} bytes; tokens ≈ bytes/4)[/]")
        console.print("[muted]/rtk install (download the official binary) · on|builtin|off · recall <id>[/]")

    # ---- caveman / ponytail
    def cmd_caveman(self, arg):
        a = arg.strip().lower()
        if a == "compress":
            return self.cmd_compress("")
        if a in CAVEMAN_RULES or a == "off":
            self.cfg.set("caveman", a)
            self.cfg.save()
        elif a in ("on", ""):
            if a == "on":
                self.cfg.set("caveman", "full")
                self.cfg.save()
        cur = self.cfg.get("caveman", "lite")
        console.print(f"Caveman: [bold]{cur}[/]  [muted]/caveman lite|full|ultra|wenyan|off · /caveman compress[/]")
        console.print("[muted]Shorter replies = fewer output tokens. Code and commands stay exact.[/]")

    def cmd_compress(self, arg):
        notes = read_notes()
        if not notes:
            console.print("[muted]No project notes to compress.[/]")
            return
        prompt = ("Rewrite these project notes using the fewest tokens possible without losing any fact: terse "
                  "fragments, no filler. Keep file names, commands and numbers exact. Output only '- ' bullets.\n\n" + notes)
        saved, self.provider.extra_body = self.provider.extra_body, {}
        try:
            with console.status("[brand]Compressing notes...[/]"):
                new = strip_think(self.provider.complete([{"role": "user", "content": prompt}])).strip()
        finally:
            self.provider.extra_body = saved
        if new and len(new) < len(notes):
            (project_dir() / "notes.md").write_text(new + "\n", "utf-8")
            console.print(f"[ok]✓[/] Notes {len(notes):,} → {len(new):,} chars")
        else:
            console.print("[muted]Notes are already compact.[/]")

    def cmd_ponytail(self, arg):
        a = arg.strip().lower()
        if a in PONYTAIL_RULES or a == "off":
            self.cfg.set("ponytail", a)
            self.cfg.save()
        elif a == "on":
            self.cfg.set("ponytail", "full")
            self.cfg.save()
        console.print(f"Ponytail: [bold]{self.cfg.get('ponytail', 'lite')}[/]  "
                      "[muted]/ponytail lite|full|ultra|off · /ponytail-help[/]")

    def _git_diff(self):
        for cmd in (["git", "diff", "--no-color", "-U2"], ["git", "diff", "--cached", "--no-color", "-U2"]):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd(), timeout=20)
            except (OSError, subprocess.SubprocessError):
                return None
            if r.returncode != 0:
                return None
            if r.stdout.strip():
                return r.stdout
        return ""

    def cmd_ponytail_review(self, arg):
        d = self._git_diff()
        if d is None:
            console.print("[warn]Not a git repository (or git is missing).[/]")
            return None
        if not d.strip():
            console.print("[muted]No uncommitted changes to review.[/]")
            return None
        return PONYTAIL_REVIEW + "\n\n```diff\n" + truncate(d, 14000) + "\n```"

    def cmd_ponytail_audit(self, arg):
        return PONYTAIL_AUDIT

    def cmd_ponytail_debt(self, arg):
        rx, rows = re.compile(r"ponytail:\s*(.+)"), []
        for f in iter_files(os.getcwd()):
            try:
                if f.stat().st_size > 500_000:
                    continue
                with open(f, "r", encoding="utf-8") as fh:
                    for n, line in enumerate(fh, 1):
                        m = rx.search(line)
                        if m:
                            rows.append((rel(f), n, m.group(1).strip()[:100]))
            except (OSError, UnicodeDecodeError):
                continue
        if not rows:
            console.print("[muted]No `ponytail:` markers found. Shortcuts the AI takes in ponytail mode are marked this way.[/]")
            return
        for f, n, note in rows[:60]:
            console.print(f"[brand]{escape(f)}:{n}[/]  {escape(note)}")
        console.print(f"[muted]{len(rows)} shortcut(s) with a known upgrade path[/]")

    def cmd_ponytail_gain(self, arg):
        total = sum(e["lines"] for e in self.ledger)
        console.print(f"Ponytail: [bold]{self.cfg.get('ponytail', 'lite')}[/]   files touched: {len(self.ledger)}   "
                      f"lines in them: {total}")
        for e in sorted(self.ledger, key=lambda e: -e["lines"])[:8]:
            console.print(f"  {e['op']:8} {escape(e['path'])} [muted]({e['lines']} lines)[/]")

    def cmd_ponytail_help(self, arg):
        console.print("[bold]Ponytail[/] — the lazy senior dev: the best code is the code you do not write.")
        console.print("  /ponytail lite|full|ultra|off   set the mode")
        console.print("  /ponytail-review   find code to delete in your uncommitted diff")
        console.print("  /ponytail-audit    audit the project for over-engineering")
        console.print("  /ponytail-debt     list `ponytail:` shortcut markers")
        console.print("  /ponytail-gain     lines written this session")

    # ---- Context7 docs
    def c7_enabled(self):
        return (self.cfg.data.get("context7") or {}).get("enabled", True) is not False

    def c7_key(self):
        return (self.cfg.data.get("context7") or {}).get("api_key") or os.environ.get("CONTEXT7_API_KEY", "")

    def apply_c7_tools(self):
        cl7 = self.mcp.get("context7")
        if not self.c7_enabled() or (cl7 and cl7.status == "ready"):
            self.tools.pop("lib_docs", None)
            self.tools.pop("lib_search", None)
            return
        S = lambda d: {"type": "string", "description": d}
        self.tools["lib_docs"] = Tool(
            "lib_docs", "Fetch CURRENT, version-specific documentation and code examples for a library or framework "
            "(Context7). Use it instead of guessing an API from memory.",
            obj({"library": S("Library name, e.g. react, fastapi"), "query": S("What you need to know"),
                 "library_id": S("Exact Context7 id like /vercel/next.js (optional, skips the search)"),
                 "max_chars": {"type": "integer", "description": "Default 6000"}}, ["library", "query"]),
            lambda a: c7_lib_docs(a["library"], a["query"], self.c7_key(), a.get("library_id") or None,
                                  int(a.get("max_chars", 6000))))
        self.tools["lib_search"] = Tool(
            "lib_search", "List Context7 libraries matching a name (id, title, description).",
            obj({"library": S("Library name"), "query": S("Topic (optional)")}, ["library"]),
            lambda a: "\n".join(f"{r.get('id')}  {r.get('title') or r.get('name') or ''}  "
                                f"{' '.join(str(r.get('description') or '').split())[:100]}"
                                for r in c7_search(a["library"], a.get("query", ""), self.c7_key())[:8]) or "No libraries found")

    def cmd_context7(self, arg):
        a = arg.strip().lower()
        c = self.cfg.data.setdefault("context7", {})
        if a == "key":
            k = pt_prompt([(pt_brand(), "❯ "), ("", "Context7 API key: ")], is_password=True).strip()
            if k:
                c["api_key"] = k
                self.cfg.save()
                console.print("[ok]✓[/] Key saved.")
                if "context7" in self.mcp:
                    self.cmd_mcp("restart context7")
        elif a in ("on", "off"):
            c["enabled"] = a == "on"
            self.cfg.save()
            self.apply_c7_tools()
        elif a == "test":
            try:
                with console.status("[brand]Asking Context7...[/]"):
                    res = c7_lib_docs("react", "useState", self.c7_key(), max_chars=300)
                console.print("[ok]✓ Context7 works[/] [muted]" + escape(res.splitlines()[0][:90]) + "[/]")
            except Exception as e:
                console.print(f"[err]✗ {escape(str(e)[:200])}[/]")
            return
        state = "on" if self.c7_enabled() else "off"
        console.print(f"Context7 docs: [bold]{state}[/]   key: {'set' if self.c7_key() else 'none (works with lower limits)'}")
        console.print("[muted]/context7 key · on · off · test   ·   /docs <library> <question>[/]")

    def cmd_docs(self, arg):
        parts = arg.strip().split(None, 1)
        if len(parts) < 2:
            console.print("[muted]Usage: /docs <library> <question>   e.g. /docs fastapi dependency injection[/]")
            return
        try:
            with console.status("[brand]Fetching docs...[/]"):
                text = c7_lib_docs(parts[0], parts[1], self.c7_key(), max_chars=3000)
        except Exception as e:
            console.print(f"[err]{escape(str(e)[:200])}[/]")
            return
        console.print(Panel(Text(text), title=f"[brand]{escape(parts[0])}[/] docs", border_style="brand", box=box.ROUNDED))

    def cmd_izin(self, arg):
        if arg.strip().lower() == "reset":
            self.allowed.clear()
            self.cfg.data.pop("always_allow", None)
            self.cfg.save()
            console.print("[dim]Always-allowed list cleared.[/]")
            return
        console.print("Always allowed: " + (", ".join(sorted(self.allowed)) or "none") + "  [dim](/izin reset)[/]")

    def cmd_undo(self, arg):
        if not self.undo_stack:
            console.print("[dim]Nothing to undo.[/]")
            return
        path, bk = self.undo_stack.pop()
        try:
            if bk:
                shutil.copy2(bk, path)
                console.print(f"[green]Restored[/] {escape(rel(Path(path)))}")
            else:
                Path(path).unlink(missing_ok=True)
                console.print(f"[green]Removed new file[/] {escape(rel(Path(path)))}")
            self.ledger = [e for e in self.ledger if e["path"] != rel(Path(path))]
        except OSError as e:
            console.print(f"[red]Undo failed: {escape(str(e))}[/]")

    def cmd_memory(self, arg):
        if arg.strip().lower() == "clear":
            (project_dir() / "notes.md").unlink(missing_ok=True)
            console.print("[dim]Project notes cleared.[/]")
            return
        console.print("[bold]Project notes[/]\n" + (read_notes() or "[dim](none)[/]"))
        console.print("[bold]Files changed this session[/]")
        for e in reversed(self.ledger[-25:]):
            console.print(f"  {e['op']} {escape(e['path'])} [dim]({e['lines']} lines, {e['t']})[/]")
        if not self.ledger:
            console.print("  [dim](none)[/]")

    def cmd_skills(self, arg):
        if not self.skills:
            console.print(f"[dim]No skills. Add folders with SKILL.md to {SKILL_DIR}[/]")
        for n, s in self.skills.items():
            console.print(f"[yellow]{escape(n)}[/]  [dim]{escape(s['description'])}[/]")

    def cmd_plugins(self, arg):
        console.print("[bold]Plugins:[/] " + (", ".join(self.plugins) or "none"))
        console.print("[bold]Tools:[/] " + ", ".join(self.tools))

    def cmd_history(self, arg):
        files = sorted(SESSION_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
        rows = []
        for f in files:
            try:
                rows.append(json.loads(f.read_text("utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        if not rows:
            console.print("[dim]No saved chats yet.[/]")
            return
        t = Table(box=None, padding=(0, 1))
        for col in ("#", "Updated", "Title", "Folder", "Msgs"):
            t.add_column(col, style="dim" if col != "Title" else "")
        for i, d in enumerate(rows, 1):
            t.add_row(str(i), d.get("updated", "")[5:16].replace("T", " "), d.get("title", ""),
                      d.get("cwd", ""), str(len(d.get("messages", []))))
        console.print(t)
        sel = arg.strip()
        if not sel:
            try:
                sel = input("Restore which chat? (number, Enter to cancel): ").strip()
            except (EOFError, KeyboardInterrupt):
                return
        if not sel.isdigit() or not 1 <= int(sel) <= len(rows):
            return
        d = rows[int(sel) - 1]
        self.save()
        self.messages, self.session_id = d["messages"], d["id"]
        self.ledger = d.get("ledger", [])
        self.created = d.get("created", self.created)
        if d.get("cwd") and os.path.isdir(d["cwd"]):
            os.chdir(d["cwd"])
        console.print(f"[green]Restored:[/] {escape(d.get('title', ''))}  [dim]({os.getcwd()})[/]\n")
        for m in self.messages[-8:]:
            c = (m.get("content") or "").strip()
            if m["role"] == "user" and c:
                console.print(Text("❯ " + c[:300], style="bold yellow"))
            elif m["role"] == "assistant" and c:
                console.print(Text(c[:600] + ("…" if len(c) > 600 else "")))
        console.print()

    # ---- REPL
    def repl(self):
        MIVO_HOME.mkdir(parents=True, exist_ok=True)
        kb = KeyBindings()

        def more_input_pending(event):
            """True while pasted text is still arriving (works even if the terminal sends no
            bracketed-paste markers): an Enter inside a paste must not send the prompt."""
            try:
                if len(event.app.key_processor.input_queue) > 0:
                    return True
            except Exception:
                pass
            try:
                import select
                return bool(select.select([event.app.input.fileno()], [], [], 0.04)[0])
            except Exception:
                return False

        @kb.add("enter")
        def _(event):   # Enter sends; "\\" + Enter or a paste keeps adding lines
            buf = event.current_buffer
            if buf.document.text_before_cursor.endswith("\\"):
                buf.delete_before_cursor(1)
                buf.insert_text("\n")
            elif more_input_pending(event):
                buf.insert_text("\n")
            else:
                buf.validate_and_handle()

        @kb.add("s-tab")
        def _(event):
            self.cycle_mode()
            event.app.invalidate()

        @kb.add("escape", "enter")
        def _(event):
            event.current_buffer.insert_text("\n")

        # multiline=True keeps pasted multi-line text as ONE prompt
        session = PromptSession(history=FileHistory(str(HISTORY_FILE)), multiline=True,
                                key_bindings=kb, prompt_continuation="  ")
        toolbar = lambda: (f" {self.cfg.get('model')}  ·  {os.getcwd()}  ·  mode: {self.cfg.get('mode', 'auto')}"
                           f"  ·  think: {self.thinking_level()}  ·  mcp {self.mcp_counts()[0]}/{self.mcp_counts()[1]}"
                           f"  ·  ctx ~{self.ctx_tokens // 1000}k  ·  /help ")
        while True:
            console.print("─" * max((console.width or 80) - 1, 1), style="muted")
            try:
                text = session.prompt([(pt_brand(), "❯ ")], bottom_toolbar=toolbar).strip()
            except KeyboardInterrupt:
                console.print("[dim]Press Ctrl+D or type /exit to quit[/]")
                continue
            except EOFError:
                break
            if not text:
                continue
            if text.startswith("/"):
                name, _, arg = text[1:].partition(" ")
                cmd = self.commands.get(name.lower())
                if not cmd:
                    console.print(f"[red]Unknown command /{escape(name)}[/] — try /help")
                    continue
                try:
                    res = cmd[0](arg)
                except KeyboardInterrupt:
                    console.print("[dim]Cancelled.[/]")
                    continue
                except SystemExit:
                    raise
                except Exception as e:
                    console.print(f"[red]Error: {escape(str(e))}[/]")
                    continue
                if isinstance(res, str) and res.strip():
                    text = res   # a command can hand a prompt to the AI (for example /ponytail-review)
                else:
                    continue
            if text.startswith("!"):
                try:
                    self._map = None
                    console.print(t_bash({"command": text[1:]}))
                except KeyboardInterrupt:
                    console.print("[dim]Interrupted.[/]")
                continue
            try:
                self.run_turn(text)
            except KeyboardInterrupt:
                console.print("\n[dim]Interrupted.[/]")
            except ProviderError as e:
                if e.status in (401, 403):
                    hint = " Check your API key with /config."
                elif e.transient():
                    hint = " The provider is having trouble: try again in a moment or switch with /model."
                else:
                    hint = ""
                console.print(f"[red]{escape(e.friendly())}{hint}[/]")
            except requests.RequestException as e:
                console.print(f"[red]Network error: {escape(str(e))}[/]")
        self.save()
        console.print("[yellow]Bye![/]")


# --------------------------------------------------------------------------
# Setup / startup
# --------------------------------------------------------------------------
def _panel(body, title, style="brand"):
    console.print(Panel(body, title=title, title_align="left", border_style=style, box=box.ROUNDED, padding=(0, 1)))


def ask_text(label, current=None, secret=False, step=None, hint=None):
    shown = f" [{'****' + current[-4:] if secret else current}]" if current else ""
    if step:
        _panel(f"[muted]{hint or ''}[/]", f"[brand]◆ Step {step[0]}/{step[1]}[/] [bold]{label}[/]")
    while True:
        # prompt_toolkit masks each typed/pasted character as '*'
        v = pt_prompt([(pt_brand(), "❯ "), ("", f"{label}{shown}: ")], is_password=secret).strip()
        if v:
            return v
        if current:
            return current
        console.print("[err]This field is required.[/]")


def run_setup(cfg: Config):
    _panel("[bold]Connect your AI[/]\n[muted]OpenAI-compatible · Anthropic · Gemini · Ollama · Azure[/]",
           "[brand]◆ MIVO setup[/]")
    cur = cfg.data
    while True:
        key = ask_text("API key", cur.get("api_key"), secret=True, step=(1, 3),
                       hint="Paste your key. Every character is hidden as *")
        raw = ask_text("Base URL", cur.get("base_url"), step=(2, 3),
                       hint="Any provider URL. The type is detected from it automatically.")
        forced = cur.get("api_type") if cur.get("api_type") in API_TYPES else None
        api_type = forced or detect_api_type(raw)
        base = normalize_base_url(raw, api_type)
        console.print(f"[muted]  ↳ {API_LABELS[api_type]} · {base}[/]")
        model = ask_text("Model ID", cur.get("model"), step=(3, 3),
                         hint="Exact model name, e.g. gpt-4o · claude-sonnet-4-5 · gemini-2.5-flash · llama3.1")
        tmp = Config({"api_key": key, "base_url": base, "model": model, "api_type": forced or "auto",
                      "extra_params": cur.get("extra_params", {})}, use_env=False)
        with console.status("[brand]Connecting...[/]"):
            ok, msg = Provider(tmp).verify()
        if ok:
            _panel(f"[ok]✓[/] {escape(msg)}\n[muted]model[/] {escape(model)}", "[ok]Connected[/]", "ok")
        else:
            _panel(f"[err]✗[/] {escape(msg)}", "[err]Could not connect[/]", "err")
            if input("Try again? [Y/n]: ").strip().lower() != "n":
                cur = dict(tmp.data)
                continue
            if input("Save anyway? [y/N]: ").strip().lower() != "y":
                console.print("[muted]Nothing saved.[/]")
                return
        cfg.data.update({"api_key": key, "base_url": base, "model": model})
        cfg.data.setdefault("api_type", "auto")
        cfg.data.setdefault("tool_mode", "native")
        cfg.save()
        return


def choose_path(arg=None, root=None):
    root = Path(root or Path.home())
    cands = [("Home", root)]
    for label, p in (("Internal storage", "/storage/emulated/0"), ("Downloads", "/storage/emulated/0/Download"),
                     ("Documents", "/storage/emulated/0/Documents")):
        if Path(p).is_dir() and all(Path(p) != c[1] for c in cands):
            cands.append((label, Path(p)))
    here = Path(os.getcwd())
    if all(here != c[1] for c in cands):
        cands.append(("Current folder", here))
    if arg is None:
        rows = "\n".join(f"[brand]{i}[/]  [bold]{lbl:<17}[/] [muted]{escape(str(p))}[/]" for i, (lbl, p) in enumerate(cands, 1))
        _panel(rows + "\n[muted]or type any path[/]", "[brand]◆ Workspace[/] [bold]Where should the AI work?[/]")
    while True:
        try:
            raw = arg if arg is not None else pt_prompt([(pt_brand(), "❯ "), ("", "Path: ")]).strip()
        except (EOFError, KeyboardInterrupt):
            raw = ""
        arg = None
        if raw.isdigit() and 1 <= int(raw) <= len(cands):
            target = cands[int(raw) - 1][1]
        else:
            target = Path(os.path.expanduser(raw)) if raw else root
        if raw.startswith("/storage") and not target.exists():
            console.print("[warn]Storage not accessible. Run: termux-setup-storage[/]")
        if target.is_dir():
            os.chdir(target)
            console.print(f"[ok]✓[/] Workspace [bold]{escape(str(target))}[/]\n")
            return
        console.print(f"[err]Not a directory: {escape(str(target))}[/]")


def print_header(animate=True):
    t = THEMES[_theme_name]
    width = console.width or 80
    title = "M I V O   C O D E"
    side = [
        (len(title), gradient(title, *t["grad"])),
        (len(f" v{VERSION}  AI coding agent"), f"[bold black on {t['brand']}] v{VERSION} [/] [muted]AI coding agent[/]"),
        (0, ""),
        (len("tools · memory · thinking · rtk · docs"), "[accent]tools · memory · thinking · rtk · docs[/]"),
        (len("by Wiji & Claude"), "[muted]by Wiji & Claude[/]"),
    ]

    def build(frame):
        art = render_mascot(frame)
        out = []
        if width >= MASCOT_W + 4 + 38:       # wide: text beside the mascot
            pad = " " * max((width - MASCOT_W - 4 - 38) // 2, 0)
            for i, line in enumerate(art):
                k = i - 1
                out.append(f"{pad}{line}    " + (side[k][1] if 0 <= k < len(side) else ""))
        else:                                  # phone portrait: mascot centered, text below
            pad = " " * max((width - MASCOT_W) // 2, 0)
            out += [pad + line for line in art]
            out.append("")
            for plain, markup in side:
                out.append(" " * max((width - plain) // 2, 0) + markup if plain else "")
        return out
    console.clear()
    console.print()
    lines = build(0)
    for line in lines:
        console.print(line)
    if animate and console.is_terminal and not os.environ.get("MIVO_NO_ANIM"):
        for fr in (1, 0, 2, 0):               # blink, antenna lights
            time.sleep(0.16)
            sys.stdout.write(f"\033[{len(lines)}A")
            sys.stdout.flush()
            for line in build(fr):
                console.print(line)
    console.print()


def _termux_props():
    return Path.home() / ".termux" / "termux.properties"


def set_termux_fullscreen(on: bool):
    """Edit termux.properties. Only `fullscreen` is set; the keyboard workaround is removed because
    it can squash the terminal view on some phones."""
    props = _termux_props()
    props.parent.mkdir(parents=True, exist_ok=True)
    lines = props.read_text("utf-8").splitlines() if props.exists() else []
    lines = [l for l in lines if not re.match(r"\s*(fullscreen|use-fullscreen-workaround)\s*=", l)]
    if on:
        lines.append("fullscreen = true")
    props.write_text("\n".join(lines) + "\n", "utf-8")
    if shutil.which("termux-reload-settings"):
        subprocess.run(["termux-reload-settings"], timeout=10)


def is_termux():
    return os.environ.get("PREFIX", "").startswith("/data/data/com.termux")


def ensure_termux_fullscreen(cfg):
    """Enable Termux fullscreen once. Disable any time with /fullscreen off."""
    if not is_termux() or cfg.data.get("fullscreen") is False:
        return
    try:
        if not cfg.data.get("fullscreen_applied"):
            set_termux_fullscreen(True)
            cfg.set("fullscreen_applied", True)
            cfg.set("fullscreen_v2", True)
            cfg.save()
            console.print("[dim]Termux fullscreen enabled (restart Termux to apply). Undo: /fullscreen off[/]")
        elif not cfg.data.get("fullscreen_v2"):  # migrate: drop the old workaround line
            set_termux_fullscreen(True)
            cfg.set("fullscreen_v2", True)
            cfg.save()
            console.print("[dim]Fullscreen layout fixed. Restart Termux (swipe it away and reopen).[/]")
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(prog="mivo", description="MIVO CODE - AI coding agent")
    ap.add_argument("--setup", action="store_true", help="re-run API setup")
    ap.add_argument("--path", help="start in this directory")
    ap.add_argument("-v", "--version", action="store_true")
    ap.add_argument("command", nargs="?", choices=["setup", "doctor", "update", "bot"],
                    help="setup: install/refresh RTK + MCP · doctor: check readiness · update: pull and reinstall · bot: run the Telegram gateway")
    ap.add_argument("--quiet", action="store_true", help="with setup: no output")
    ap.add_argument("--show", action="store_true", help="with setup: show the last result")
    args = ap.parse_args()
    if args.version:
        print(f"MIVO CODE {VERSION}\nfile:   {os.path.abspath(__file__)}\ndata:   {MIVO_HOME}")
        return
    for d in (SESSION_DIR, SKILL_DIR, PLUGIN_DIR):
        d.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    apply_theme(cfg.get("theme", "android"))
    os.environ.setdefault("RTK_TELEMETRY_DISABLED", "1")   # never send telemetry from the optional rtk binary
    if args.command:
        sys.exit(run_cli_command(args, cfg))
    print_header()
    if args.setup or not cfg.complete():
        run_setup(cfg)
        if not cfg.complete():
            return
    if cfg.data.get("base_url"):
        fixed = normalize_base_url(cfg.data["base_url"], cfg.data.get("api_type"))
        if fixed != cfg.data["base_url"]:
            cfg.data["base_url"] = fixed  # repair old saved values
        cfg.save()
    ensure_termux_fullscreen(cfg)
    choose_path(args.path, cfg.get("root_dir"))
    agent = Agent(cfg)
    agent.wait_mcp(3.0)
    mcp_r, mcp_t = agent.mcp_counts()
    tgc = tg_cfg(cfg)
    if tgc.get("token") and tgc.get("enabled", True) and not bot_running():
        start_bot(wait=5)
    atexit.register(agent.close_mcp)
    rtk_state = "off" if cfg.get("rtk", "auto") == "off" else ("binary" if rtk_binary() and cfg.get("rtk", "auto") == "auto" else "built-in")
    console.print(f"[muted]model[/] [bold]{escape(cfg.get('model'))}[/] [muted]· {agent.provider.label} · {len(agent.skills)} skills · "
                  f"{len(agent.plugins)} plugins[/]")
    console.print(f"[muted]mode[/] {cfg.get('mode', 'auto')}  [muted]thinking[/] {agent.thinking_level()}  "
                  f"[muted]rtk[/] {rtk_state}  [muted]mcp[/] {mcp_r}/{mcp_t}  [muted]docs[/] on  "
                  f"[muted]caveman[/] {cfg.get('caveman', 'lite')}  [muted]ponytail[/] {cfg.get('ponytail', 'lite')}")
    if tgc.get("token"):
        console.print(f"[muted]telegram[/] @{escape(tgc.get('username', ''))} "
                      f"{'[ok]●[/] running' if bot_running() else '[warn]○[/] stopped (/addbot start)'}")
    console.print("[muted]/help · /prefensi · /thinking · /theme · /rtk · /caveman · /ponytail · /docs · /addweb[/]\n")
    try:
        agent.repl()
    except SystemExit:
        agent.save()
        console.print("[yellow]Bye![/]")


if __name__ == "__main__":
    main()
