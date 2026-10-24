---
name: error-handling
description: Robust error handling, logging and input validation. Use when code crashes, is fragile or needs reliability.
triggers: exception, logging, retry
---
# Error handling
- Validate input at the boundary and fail early with clear messages.
- Catch specific exceptions; handle what you can, let the rest propagate. Never swallow errors silently.
- Show users a friendly message; log technical detail (with traceback) separately.
- Clean up resources with `with`/`finally`. Make operations idempotent where retried.
- Network/file operations: timeouts, retries with backoff, and a graceful fallback.
- Log levels: debug (dev detail), info (milestones), warning (recoverable), error (failed operation).
