---
name: security-checklist
description: Avoid common vulnerabilities - injection, secrets, unsafe input, dependencies. Use when writing or reviewing code that handles user input, files, auth or network.
triggers: security, secure, vulnerability, password, login
---
# Security checklist
- **Injection**: parameterized SQL; never build shell commands from user input (use argument lists, `subprocess.run([...])` without `shell=True`).
- **Secrets**: never commit keys/tokens; use env vars or a git-ignored `.env`; if a secret leaked, rotate it.
- **Paths**: normalize and verify user-supplied paths stay inside the intended folder (no `../`).
- **Passwords**: hash with bcrypt/argon2 (or `hashlib.scrypt`), never store plaintext, never roll your own crypto.
- **Web**: escape output (XSS), CSRF protection on state-changing requests, HTTPS, restrictive CORS.
- **Deserialization**: no `pickle`/`eval`/`exec` on untrusted data.
- **Dependencies**: install only what's needed, from trusted sources, pinned versions.
