---
name: python-best-practices
description: Write clean, idiomatic Python - structure, typing, errors, venv, packaging. Use for any Python code.
triggers: python, pip
---
# Python best practices
- Layout: `src/<pkg>/`, `tests/`, `requirements.txt` (or pyproject.toml). Run with `python -m <pkg>`.
- Style: PEP 8, f-strings, `pathlib` over os.path, `with` for files, small functions, early returns.
- Add type hints to public functions; use `dataclasses` for plain data.
- Errors: catch specific exceptions, never bare `except:`; raise with a helpful message; use `logging`, not print, in libraries.
- Never use mutable default arguments. Prefer comprehensions and `enumerate`/`zip`.
- Dependencies: virtualenv (`python -m venv .venv`) when allowed; pin versions; in Termux avoid packages needing compilation.
- CLI: `argparse` + `if __name__ == "__main__": main()`.
