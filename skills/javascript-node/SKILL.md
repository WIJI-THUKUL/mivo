---
name: javascript-node
description: Modern JavaScript and Node.js - modules, async, npm scripts, error handling. Use for JS/Node projects.
triggers: javascript, node, npm, typescript
---
# JavaScript / Node
- Use `const`/`let`, arrow functions, template strings, optional chaining (`?.`), `??`.
- Async: `async/await` with try/catch; run independent work with `Promise.all`; never leave promises unhandled.
- Project: `npm init -y`, `"type": "module"` for ES modules, scripts `start`/`test`/`dev` in package.json, `.gitignore` with node_modules.
- Validate input at boundaries; never trust `req.body` or `process.argv`. Read secrets from `process.env`, never hardcode.
- Built-in test runner: `node --test`. Format/lint with prettier/eslint only if already in the project.
- Check Node version first: `node -v`. In Termux: `pkg install nodejs`.
