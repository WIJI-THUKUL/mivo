---
name: bash-scripting
description: Write safe, portable shell scripts. Use for automation, installers and CLI glue in Termux/Linux.
triggers: bash, shell
---
# Bash scripting
- Header: `#!/usr/bin/env bash` and `set -euo pipefail`.
- Always quote variables: `"$var"`; use `[[ ... ]]` for tests; `$(cmd)` not backticks.
- Check dependencies: `command -v tool >/dev/null || { echo "need tool"; exit 1; }`.
- Functions with `local` variables; parse flags with `while getopts` or a `case` loop.
- Temp files via `mktemp`; clean up with `trap 'rm -rf "$tmp"' EXIT`.
- Never `rm -rf "$var/"` without checking `$var` is non-empty. Lint mentally for word-splitting bugs.
- Make executable: `chmod +x script.sh`. (Not possible on /storage/emulated/0.)
