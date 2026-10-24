---
name: refactoring
description: Improve code structure safely without changing behavior. Use when asked to clean up, simplify, reorganize or reduce duplication.
triggers: refactor, cleanup, simplify
---
# Refactoring
1. Make sure behavior is pinned down: run existing tests, or write a quick test/command that shows current output.
2. Change in small steps; re-run after each step. Do not mix refactoring with new features.
3. Typical moves: extract function, rename for clarity, remove duplication, replace nested ifs with early returns, split large files by responsibility, delete dead code.
4. Keep public interfaces stable unless the user asks otherwise; update all call sites (use grep).
5. Finish by showing a short summary of what moved/renamed and confirming tests still pass.
