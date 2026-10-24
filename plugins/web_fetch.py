"""Plugin: web_fetch - read a web page as plain text (docs, READMEs, APIs)."""
import re

import requests


def register(api):
    def web_fetch(a):
        url = a["url"]
        limit = int(a.get("max_chars", 8000))
        r = requests.get(url, timeout=20, headers={"User-Agent": "MIVO-CODE/0.1"})
        text = r.text
        if "html" in r.headers.get("content-type", ""):
            text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", text)
            text = re.sub(r"(?s)<[^>]+>", " ", text)
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n\s*\n+", "\n\n", text)
        text = text.strip()
        head = f"[HTTP {r.status_code}] {url}\n"
        return head + (text[:limit] + ("\n... [truncated]" if len(text) > limit else ""))

    api.tool(
        "web_fetch",
        "Fetch a URL and return its text (HTML is stripped). Use for docs, READMEs and APIs.",
        {"type": "object",
         "properties": {"url": {"type": "string"},
                        "max_chars": {"type": "integer", "description": "Default 8000"}},
         "required": ["url"]},
        web_fetch,
        permission="safe",
    )
