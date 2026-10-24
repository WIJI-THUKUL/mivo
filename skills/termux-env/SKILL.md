---
name: termux-env
description: Termux/Android specifics - installing packages, storage paths, what does not work. Use before installing tools or touching /storage.
triggers: termux, pkg, storage, sdcard
---
# Termux environment
- Install system packages with `pkg install <name>` (no sudo, no apt). Python: `pkg install python`; Node: `pkg install nodejs`.
- `pip install` only works reliably for pure-Python packages. Packages needing Rust/C (pydantic-core, numpy builds) often fail; prefer `pkg install python-numpy` or avoid them.
- Shared storage is `/storage/emulated/0` (needs `termux-setup-storage` once). It does NOT support symlinks, chmod or executable bits; git and node_modules can misbehave there. Build projects in `$HOME` and copy results out.
- `$PREFIX` is `/data/data/com.termux/files/usr`; `$HOME` is `/data/data/com.termux/files/home`.
- No systemd, no docker, no root. Long-running servers: run in background with `nohup ... &` and keep Termux awake (`termux-wake-lock`).
- Check before assuming: `command -v <tool>`.
