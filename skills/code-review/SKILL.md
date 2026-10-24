---
name: code-review
description: Review code for bugs, security and maintainability. Use when asked to review, audit or improve existing code.
triggers: review, audit
---
# Code review checklist
- **Correctness**: edge cases (empty, None, large input), off-by-one, error paths, resource cleanup.
- **Security**: untrusted input reaching shell/SQL/paths, hardcoded secrets, unsafe deserialization, missing auth checks.
- **Maintainability**: unclear names, duplicated logic, functions doing too much, dead code.
- **Performance**: only flag real problems (N+1 queries, quadratic loops on big data).
- **Tests**: are the risky paths covered?
Output: group findings as Critical / Should fix / Nit, each with file:line and a concrete suggested fix. Read the code first; do not review from memory.
