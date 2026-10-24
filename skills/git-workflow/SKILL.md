---
name: git-workflow
description: Safe git habits - branching, commit messages, undoing mistakes. Use when committing, branching or fixing git problems.
triggers: git, commit, branch, merge, github
---
# Git workflow
1. Run `git status` and `git diff` before committing; never commit blindly with `git add -A` if untracked junk exists.
2. Work on a branch: `git switch -c feat/<short-name>`.
3. Commit messages: imperative, under 72 chars (`Add login validation`); body explains why.
4. Never force-push or `reset --hard` without the user's explicit approval; prefer `git revert` for shared history.
5. Undo helpers: unstage `git restore --staged <f>`; discard `git restore <f>` (destructive, ask first); amend last commit `git commit --amend`.
6. Add a `.gitignore` early (node_modules, __pycache__, .env, build output). Never commit secrets.
