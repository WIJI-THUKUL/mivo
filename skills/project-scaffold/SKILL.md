---
name: project-scaffold
description: Start a new project with a clean minimal structure (Python CLI, Node app, static website). Use when the user asks to create or bootstrap a project.
triggers: scaffold, bootstrap, starter, template
---
# Scaffolding
Ask nothing unless essential; pick sensible defaults and state them.
**Python**: `src/<pkg>/__init__.py`, `src/<pkg>/main.py`, `tests/`, `requirements.txt`, `README.md`, `.gitignore`.
**Node**: `npm init -y`, `src/index.js`, scripts for `start` and `test`, `.gitignore` with node_modules.
**Static web**: `index.html`, `style.css`, `script.js` (no build step; works offline in a phone browser).
Always: create a README with run instructions, init git only if asked, then run the project once to confirm it works.
