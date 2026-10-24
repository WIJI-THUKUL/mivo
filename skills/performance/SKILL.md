---
name: performance
description: Find and fix real performance problems - measure first. Use when code is slow or uses too much memory.
triggers: slow, performance, optimize
---
# Performance
1. **Measure first**: time it (`time cmd`, `python -m cProfile -s cumtime script.py`, `console.time`). Do not guess.
2. Fix the biggest cost only: algorithmic complexity (nested loops over big data, repeated lookups in lists -> use dict/set), N+1 queries, repeated disk/network calls (cache or batch), loading everything into memory (stream/iterate).
3. Re-measure and report before/after numbers.
4. Don't micro-optimize readable code without evidence. Keep the optimization commented with the reason.
