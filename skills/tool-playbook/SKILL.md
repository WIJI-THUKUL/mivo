---
name: tool-playbook
description: Worked examples of correct tool use. Always active.
triggers: *
---
# Tool playbook (copy these patterns)
**Create:** user "make a python hello app" ->
  write_file {"path": "hello/main.py", "content": "print('Hello')\n"}  then  bash {"command": "python hello/main.py"}  then 1-line report.
**Change:** user "rename greet to welcome" ->
  grep {"pattern": "greet"}  ->  read_file {"path": "src/app.py", "offset": 1, "limit": 80}  ->
  multi_edit {"path": "src/app.py", "edits": [{"old_string": "def greet(", "new_string": "def welcome("}, {"old_string": "greet(name)", "new_string": "welcome(name)"}]}  ->  run the tests.
**Fix:** bash shows a traceback -> read_file around the failing line -> edit_file the real cause -> run the same command again, until it passes.
**Several files at once:** put the independent calls (reads, greps, writes) in ONE response.
**Never:** narrate long plans, ask the user to run commands, paste files in chat, retry the same failing call unchanged, or stop before you ran what you built.
