---
name: debugging
description: Systematic debugging - reproduce, isolate, fix root cause, verify. Use when something is broken, a test fails or an error appears.
triggers: error, bug, crash, fix, fail, failing, exception, traceback, broken
---
# Debugging method
1. **Reproduce**: get the exact error and the command that triggers it. Run it yourself with bash.
2. **Read the error fully**: file, line, message. Open that code with read_file.
3. **Form one hypothesis**, then test it (print/log, small script, grep for usages). Change one thing at a time.
4. **Fix the root cause**, not the symptom. Keep the edit minimal.
5. **Verify**: re-run the original command and the related tests. Report what was wrong and what you changed.
Avoid: guessing multiple fixes at once, rewriting whole files, silencing errors with broad try/except.
