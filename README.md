# MIVO CODE

**An AI coding agent for your terminal, built for Termux (Android).**
Plug in any OpenAI-compatible API and MIVO CODE turns a normal chat model into a coding agent that can read your project, write and edit files, run commands and fix its own mistakes.

> Repository: <https://github.com/WIJI-THUKUL/mivo>
> Contributors: **Wiji** & **Claude**

[Bahasa Indonesia ↓](#bahasa-indonesia)

---

## Features

> **Version 1.0** · Termux · Ubuntu/Debian · multi-provider

- **Works with more than OpenAI-compatible APIs**: OpenAI-compatible (OpenAI, OpenRouter, Groq, DeepSeek, LiteLLM...), **Anthropic native**, **Google Gemini native**, **Ollama native** and **Azure OpenAI**. The type is detected from your Base URL. You bring the API key, Base URL and model ID; no token, context or temperature limits are imposed.
- **Themed, animated interface**: 5 color themes (`/theme`), a shaded 16x16 pixel mascot that blinks, a gradient title and boxed setup steps.
- **Everything is installed and on by default** (no commands to type): RTK output compaction, MCP with Context7 live docs, Caveman terse replies (lite) and Ponytail minimal-code mode (lite). `bash mivo.sh` provisions them in one go and `mivo doctor` checks they are ready.
- **Real agent loop with tools**: `bash`, `read_file`, `write_file`, `edit_file`, `list_dir`, `glob`, `grep`, plus skills, notes and optional web search.
- **Live streaming code + auto-save**: code appears line by line in a colored block and is saved to disk while it streams. Folders are created automatically.
- **Minimal permission prompts**: files and normal commands just run. Only gradle, git writes and package installs ask, with a single keypress.
- **Sharper memory**: every turn the AI receives a live project map (files, line counts, function/class names), the files it changed and its saved project notes. Old history is summarised automatically, so long sessions stay sharp and cheap.
- **Thinking mode**: `/thinking low|medium|high` lets the AI reason before acting, with the provider's native reasoning when available or `<think>` notes for any model.
- **Token-saving tool use**: unchanged files are never re-sent, old bulky output is shrunk, `multi_edit` changes many lines in one call, and every write gets an instant syntax check.
- **Skills and plugins**: 19 built-in coding skills that switch on automatically by keyword, plus Python plugins.
- **Your own instructions**: `/prefensi` lets you type or paste instructions or a full system prompt.
- **Chat history**: every chat is saved as JSON and can be restored with `/riwayat`.
- **Runs on Termux, Ubuntu/Debian (proot too) and more**: pure-Python dependencies only (`requests`, `rich`, `prompt_toolkit`), no compiling.
- **Safety net**: `/undo` restores the AI's last file change; dangerous commands need a typed `yes`.

## Requirements

- **Termux**, **Ubuntu/Debian** (including proot/PhoneIDE), Alpine, Fedora, Arch or macOS, with `bash`
- Python 3.8+ (the installer installs it for you if it is missing)
- An OpenAI-compatible API key, Base URL (ending in `/v1`) and model ID

## Install

**Termux**

```bash
pkg update && pkg install -y git
git clone https://github.com/WIJI-THUKUL/mivo.git
cd mivo
bash mivo.sh
```

**Ubuntu / Debian (also proot, PhoneIDE, WSL)**

```bash
apt update && apt install -y git
git clone https://github.com/WIJI-THUKUL/mivo.git
cd mivo
bash mivo.sh
```

The installer shows a progress bar:

```
Installing mivo version: 1.0
■■■■■■■■■■■■■■■■■■■■■■■■･･････････････････････････  48%
```

Details go to `~/.mivo/install.log`. The same `bash mivo.sh` works everywhere. It detects the system on its own: Termux uses `pkg`, and if `pkg` is missing or fails it automatically switches to the Ubuntu/Debian way (`apt`); Alpine, Fedora, Arch and macOS are handled too. On Ubuntu the dependencies go into a private virtualenv (`~/.mivo/venv`), so the system Python is left alone.

The installer copies the app to `~/.mivo`, installs Python and the dependencies if needed, **provisions the components** (the official RTK binary where it can run, the default MCP servers, a readiness check) and creates the `mivo` command. Check it worked:

```bash
mivo --version
```

**One command for everything** (same idea as `npx rea-agents setup` / `rea update` from [morluto/rea](https://github.com/morluto/rea)):

```bash
mivo setup     # install or refresh RTK and the MCP servers, then show a readiness table
mivo doctor    # check everything, including your API connection and every MCP server
mivo update    # git pull the source folder and re-run the installer
```

**Update later:**

```bash
cd mivo && git pull && bash mivo.sh
```

Your config, chat history and any skills or plugins you edited are kept.

## Run

```bash
mivo
```

1. **First run only: API setup**, in three boxed steps: `API key` (shown as `*`), `Base URL` and `Model ID`. The provider type (OpenAI-compatible, Anthropic, Gemini, Ollama or Azure) is detected from the URL and shown, the connection is tested, and nothing is saved until it works. A pasted endpoint such as `.../v1/chat/completions` is cleaned up automatically.
2. **Choose a workspace.** A small menu lists Home, Internal storage, Downloads and so on: type its number, or type any path such as `/storage/emulated/0/MyProject`. An empty answer uses the home folder. For shared storage run `termux-setup-storage` once.
3. **Talk to it**, for example: `make a todo web app with HTML, CSS and JS and run a local server`.

Start in a folder directly: `mivo --path ~/myproject`. Redo the setup: `mivo --setup`.

## Typing and pasting

- **Enter** sends the message.
- **Paste** any amount of text: it stays one prompt.
- To type several lines, end a line with `\` and press Enter.
- `!command` runs a shell command directly, without the AI.
- **Ctrl+C** stops the current answer or command.

## Commands

| Command | What it does |
|---|---|
| `/help` | List commands |
| `/riwayat` (or `/history`) | Browse and restore earlier chats |
| `/new` | Start a fresh chat (old one stays in `/riwayat`) |
| `/clear` | Clear the screen |
| `/compact` | Summarize the history to free context |
| `/cd <path>` | Change the working directory |
| `/model [id]` | Show or change the model |
| `/config` | Redo API setup |
| `/prefensi` (`/prompt`, `/instruksi`) | Your own instructions or system prompt for the AI |
| `/mode auto\|ask\|yolo` | Permission mode (Shift+Tab cycles) |
| `/izin` | Show "always allowed" actions; `/izin reset` clears them |
| `/undo` | Undo the AI's last file change |
| `/memory` | Show project notes and changed files; `/memory clear` |
| `/theme <name>` | Colors: `android`, `ocean`, `sunset`, `grape`, `mono` |
| `/apitype <type>` | Force the protocol: `auto`, `openai`, `anthropic`, `gemini`, `ollama`, `azure` |
| `/addbot` | Telegram bot: talk to the AI from Telegram (details below) |
| `/mcp` | MCP servers: `list`, `tools`, `add`, `remove`, `trust`, `restart` |
| `/rtk` | Output compaction: `on\|builtin\|off`, `gain`, `recall <id>` |
| `/caveman <level>` | Terse replies: `lite\|full\|ultra\|wenyan\|off`; `/caveman compress` shrinks project notes |
| `/ponytail <level>` | Minimal-code mode: `lite\|full\|ultra\|off`; also `-review`, `-audit`, `-debt`, `-gain`, `-help` |
| `/context7` | Live library docs: `key`, `on`, `off`, `test`; `/docs <library> <question>` |
| `/thinking` | AI thinking: `off\|low\|medium\|high [native\|prompt]`, `show\|hide` |
| `/usage` | Token usage and context size |
| `/addweb` | Add web search (API key, Base URL, browser model) |
| `/fullscreen on\|off` | Termux fullscreen |
| `/skills`, `/plugins` | List skills, plugins and tools |
| `/exit` | Quit |

## Permissions

MIVO CODE follows the same idea as other terminal coding agents: work freely inside your storage, ask only for risky things, answer with one key (Enter = yes).

| Mode | Behavior |
|---|---|
| `auto` (default) | Files and normal commands run freely. Asks only for **gradle**, **git writes** (commit, push, pull, checkout...) and **installs** (npm, pip, pkg, npx...). |
| `ask` | Strict. Asks before every file write and every command that is not read-only. |
| `yolo` | Never asks. Truly dangerous commands still need a typed `yes`. |

Prompt: `Allow? [Y]es / [A]lways / [N]o`. `A` is remembered permanently. `N` lets you type what the AI should do instead. System or secret locations (`/etc`, `~/.ssh`, `~/.bashrc`, `config.json`) always ask, and `rm -rf` outside the project, `sudo`, `dd`, force push and `curl | sh` require typing `yes`.

## Auto-save

- Files written with the `write_file` tool stream live and are saved as they arrive.
- Code shown in chat is also saved when the block is labeled with a file name:
  ````
  ```python src/app.py
  ```js:index.js
  ````
  or a line right above the block containing only the path (for example `File: app.py`). Unlabeled snippets and shell blocks are never saved.

## Memory

Chats start empty, but the AI always gets: a live **project map**, the **files it changed** this session, and **project notes** saved with its `remember` tool (stored per folder in `~/.mivo/projects/`). Old chats come back with `/riwayat`.

## Thinking

`/thinking` controls whether the AI reasons before it acts.

| Command | Effect |
|---|---|
| `/thinking off` | Default. No extra thinking, cheapest. |
| `/thinking low\|medium\|high` | Sends the provider's reasoning setting (`reasoning_effort`, OpenRouter `reasoning`, Anthropic `thinking` budget). If the provider rejects it, MIVO automatically falls back to prompt-based thinking. |
| `/thinking medium prompt` | Force prompt-based thinking: any model writes short `<think>` notes (about 60 / 150 / 400 words for low / medium / high) before acting. |
| `/thinking hide` / `show` | Hide or show the thinking text. |

Reasoning that a model streams by itself (for example DeepSeek-style `reasoning_content`) is always displayed dimly. Thinking text is **never stored or sent back**, so it does not eat your context.

## Optimization: memory, tokens and tool use

- **Memory:** the project map puts files you just changed or mentioned first with full function lists and keeps the rest short, so big projects cost few tokens. Notes saved with `remember` survive restarts.
- **Auto-compaction:** above about 50,000 estimated tokens, older history is summarised (the latest messages and tool results stay intact). Tune with `"auto_compact_tokens"` in `config.json` (`0` turns it off). `/compact` does it now and `/usage` shows the numbers.
- **Less repeated text:** unchanged files that are still in recent context are not re-sent, old bulky tool output and old file contents are shrunk in what is sent, and defaults are lean (`read_file` 400 lines, 100 grep matches).
- **Better tool use:** `multi_edit` makes several changes in one call; every write returns an instant syntax check (Python, JSON, JavaScript, shell); wrong argument names such as `file_path` or `cmd` are accepted; missing-file errors suggest the right name; the AI is blocked from repeating the same call three times; and after writing runnable code it is nudged once to actually run it (`"verify_nudge": false` turns that off).
- **Tool calls written as text** (` ```json ` or `<tool_call>`) by weaker models are run anyway.

## Providers beyond OpenAI-compatible

| Type | Detected from | Notes |
|---|---|---|
| `openai` | anything else | OpenAI, OpenRouter, Groq, DeepSeek, Mistral, LM Studio, vLLM, LiteLLM, Ollama's `/v1`... |
| `anthropic` | `api.anthropic.com` | Native Messages API: streaming, tools, extended thinking, prompt caching of the stable system prompt |
| `gemini` | `generativelanguage.googleapis.com` | Native API: streaming, function calling, thinking summaries (the `/v1beta/openai` URL stays OpenAI-compatible) |
| `ollama` | port `11434` or "ollama" in the host | Native `/api/chat`: streaming, tools, thinking |
| `azure` | `*.openai.azure.com` | `api-key` header, `api-version` for deployment URLs |

Force a type with `/apitype <type>`. Optional `config.json` keys: `api_type`, `max_tokens` (Anthropic needs one; default 8192), `auth_style` (`bearer`, `x-api-key`, `api-key`, `none`), `extra_headers`, `api_version`, `extra_params`.

## Themes

`/theme android` (default green), `ocean`, `sunset`, `grape`, `mono`. The theme colors the mascot, title, prompt, panels, code blocks and setup steps.

## Token savers, docs and MCP: all on by default

You do not need to type any command for these. They are active from the first message; the commands below only tune or turn them off.

**RTK output compaction** (on by default; `/rtk` to tune). Command output is cleaned before the AI reads it: progress bars and ANSI codes are removed, duplicate lines are collapsed, `pip`/`npm`/`apt`/`git push` noise is dropped, passing test runs shrink to their summary while failures keep their details, `grep` floods are grouped by file, and long `git log` output becomes one line per commit. The full text is kept: the AI can call `recall <id>` (optionally with a `grep` filter) and `/rtk gain` shows the savings. `read_file` also has an `outline` mode (signatures only). The installer downloads the official [`rtk`](https://github.com/rtk-ai/rtk) binary from its GitHub releases into `~/.mivo/bin` (checksum verified when published; it never runs `rtk init` and never touches other tools' settings). MIVO then runs simple commands such as `git status` or `pytest` through it, with telemetry disabled. The official Linux builds are x86_64 and aarch64 with glibc, so they work on Ubuntu/Debian (including proot) and macOS but **not on plain Termux (Android)**: there the built-in engine does the same job. `/rtk off` disables everything.

**Caveman** (default `lite`; `/caveman lite|full|ultra|wenyan|off`). The AI answers in short fragments to cut output tokens. Code, commands, paths and error messages stay exact, and the style drops itself for security warnings and irreversible actions. `/caveman compress` rewrites your saved project notes in fewer tokens.

**Ponytail** (default `lite`; `/ponytail lite|full|ultra|off`). The "lazy senior developer" mode: before writing code the AI asks whether it is needed at all, whether the standard library, the platform or an installed dependency already does it, and only then writes the minimum, marking real shortcuts with a `ponytail:` comment. `/ponytail-review` finds code to delete in your uncommitted git diff, `/ponytail-audit` audits the project, `/ponytail-debt` lists the markers and `/ponytail-gain` shows what was written.

**Context7** (on by default through MCP). The AI reads current, version-specific documentation from [Context7](https://github.com/upstash/context7) instead of guessing an API from memory. It connects to the remote MCP endpoint `https://mcp.context7.com/mcp` (no Node.js needed); if that is unreachable, the built-in REST tools `lib_docs` / `lib_search` take over. It works without a key at lower limits; `/context7 key` stores a free key. Only the library name and your question are sent. `/docs fastapi dependency injection` lets you read docs yourself.

**MCP** (any server, not just Context7). MIVO is an MCP client for stdio and Streamable-HTTP servers. Servers live in `~/.mivo/mcp.json`, the same `{"mcpServers": {...}}` shape other agents use, and each server's tools appear as `mcp__<server>__<tool>`:

```json
{"mcpServers": {
  "context7": {"url": "https://mcp.context7.com/mcp", "trust": true},
  "mytool":   {"command": "npx", "args": ["-y", "some-mcp-server"], "env": {"TOKEN": "${TOKEN}"}}
}}
```

`/mcp` lists servers and status, `/mcp add <name> <url | command args...> [--trust] [--header K=V]` adds one live, `/mcp remove <name>`, `/mcp trust <name> on|off`, `/mcp restart`. Servers start in the background, a broken one never blocks MIVO, and tools from a server that is not trusted ask first (`A` remembers). Stdio servers started with `npx` need Node.js (`pkg install nodejs` or `apt install nodejs npm`). To use a server such as [REA](https://github.com/morluto/rea) (reverse engineering), follow its own setup instructions and add it with `/mcp add`.

## Acknowledgements

The component setup (`setup`, `doctor`, `update`) copies the approach of [morluto/rea](https://github.com/morluto/rea). The ideas behind these features come from [rtk-ai/rtk](https://github.com/rtk-ai/rtk), [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail), [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) and [upstash/context7](https://github.com/upstash/context7). MIVO CODE contains its own Python implementation (and calls the Context7 REST API and, if present, the `rtk` binary); see those repositories for their code and licenses.

## Telegram bot: /addbot

Talk to your AI from Telegram, and let it run commands on this device (same idea as the Hermes messaging gateway).

1. In Telegram open **@BotFather**, send `/newbot`, and copy the token.
2. In MIVO run `/addbot`, paste the token (hidden as `*`) and press Enter. MIVO verifies it, shows the bot's name and `Connected`, and starts the gateway in the background. Press Enter again to close.
3. In Telegram open your bot and send the pairing command MIVO showed: `/pair 123456`. That one account is now allowed.

Then just write to the bot. The AI uses the same tools as in the terminal (files, shell, MCP, docs, web search), and a status message shows which tool is running. Extras: `/new`, `/cd <folder>`, `/pwd`, `/stop` (kills the running command), `/mode auto|ask|yolo`, `/status`, `/id`. Files you send are saved in `<folder>/telegram_inbox/` and handed to the AI; the AI can send you files with its `telegram_send` tool.

**Security model** (a bot username is public, so this matters):
- Only paired Telegram accounts are served; everybody else gets one polite refusal and the AI never runs. Pairing codes are single use, expire in 15 minutes, and 5 wrong attempts lock an account for 10 minutes. Add or remove accounts with `/addbot allow <id>`, `/addbot deny <id>` and `/addbot pair`.
- Private chats only (groups are ignored). Messages that were sent while the gateway was offline are never executed.
- Risky actions (installs, git writes, gradle, dangerous commands, files outside your storage) need a button press in Telegram: **Allow / Always / Deny** (dangerous commands only offer *Yes, run it / Cancel*). Nobody else can press them; no answer in 5 minutes means deny. `/addbot mode ask` asks for every write and command, `yolo` never asks.
- The token lives in `~/.mivo/config.json` (chmod 600) and is removed from logs. If it ever leaks, send `/revoke` to @BotFather.
- Remember that whoever controls a paired Telegram account controls this device. Keep that account protected (2-step verification).

Management: `/addbot status | pair | allow | deny | mode | cwd <folder> | start | stop | restart | remove | log`. The gateway is its own background process (`mivo bot` runs it in the foreground); chat sessions never disturb your terminal session, and new chats start in `/addbot cwd` (default: home). On Termux MIVO takes a wake lock so the bot keeps answering with the screen off. MIVO starts the gateway with the app unless you ran `/addbot stop`. Telegram must be reachable from your network; for a proxy or mirror set `"telegram_api"` in `config.json`.

## Web search

`/addweb` asks for **API key**, **Base URL** and **Model ID (browser)**. The model must be a web-browsing, OpenAI-compatible chat model from your provider. The AI then gets a `web_search` tool that asks that model and returns the answer with source links. Remove it with `/addweb off`.

## Skills

Skills are folders with a `SKILL.md`:

```
~/.mivo/skills/my-skill/SKILL.md
```

```markdown
---
name: my-skill
description: One line about when to use it
triggers: keyword1, keyword2
---
Instructions for the AI...
```

If a trigger word appears in your request, the skill is applied automatically (a `*` trigger means always on). Built in (19): `tool-playbook`, `android-app` (AIDE/Gradle projects), `termux-env`, `git-workflow`, `debugging`, `code-review`, `project-scaffold`, `write-tests`, `python-best-practices`, `javascript-node`, `web-frontend`, `bash-scripting`, `sqlite-database`, `rest-api`, `security-checklist`, `error-handling`, `refactoring`, `documentation`, `performance`.

## Plugins

A plugin is a Python file in `~/.mivo/plugins/` with a `register(api)` function:

```python
def register(api):
    def hello(args):
        return "Hello " + args.get("name", "world")

    api.tool("hello", "Say hello",
             {"type": "object", "properties": {"name": {"type": "string"}}, "required": []},
             hello, permission="safe")
    api.command("hi", lambda arg: print("hi!"), "Say hi")
```

Built in: `web_fetch` (read a URL), `todo` (task list), `termux_api` (battery, clipboard, notifications). **Plugins run arbitrary code: only install ones you trust.**

## Your own instructions

`/prefensi` offers: (1) custom instructions added to every request, (2) a replacement system prompt (you can use `{cwd}` and `{env}`), (3) a view of the full prompt the AI receives, (4) reset. Type or paste your text and finish with a line containing only `/done`.

## Project instructions

Put a `MIVO.md` (or `AGENTS.md` / `CLAUDE.md`) in your project folder and it is read automatically.

## Files and settings

| Path | Content |
|---|---|
| `~/.mivo/config.json` | API settings (permissions `600`) |
| `~/.mivo/sessions/` | Chat history (JSON) |
| `~/.mivo/skills/`, `~/.mivo/plugins/` | Your skills and plugins |
| `~/.mivo/projects/` | Project notes |
| `~/.mivo/backups/` | Backups used by `/undo` |

Useful `config.json` keys: `theme`, `rtk`, `caveman`, `ponytail`, `context7`, `thinking`, `thinking_style`, `show_thinking`, `auto_compact_tokens`, `verify_nudge`, `max_steps`, `mode`, `extra_params`.
Bundled skills and plugins are refreshed on every install; if you edited one, your copy is kept as `SKILL.md.old` / `plugin.py.old`. To customise a skill, copy it under a new name.

Environment overrides: `MIVO_API_KEY`, `MIVO_BASE_URL`, `MIVO_MODEL`, `MIVO_HOME`.
Some providers require `max_tokens`: add `"extra_params": {"max_tokens": 4096}` to `config.json`.

## Troubleshooting

| Problem | Fix |
|---|---|
| Old behavior after updating | Run `mivo --version`. It must show the new version. If not, run `bash mivo.sh` again from the updated folder. |
| `Provider error (503)` / "service unavailable" | The model's provider is down. MIVO retries 3 times; then try again later or switch with `/model`. |
| API key rejected | Run `/config`. Use a Base URL ending in `/v1`. |
| Layout broken after fullscreen | Run `/fullscreen off`, then restart Termux. |
| Cannot access `/storage/emulated/0` | Run `termux-setup-storage` once (Termux only). |
| `Python is required` | Run `apt update && apt install -y python3 python3-pip python3-venv` (Ubuntu/Debian) or `pkg install python` (Termux), then `bash mivo.sh` again. |
| `mivo: command not found` | Add the folder printed by the installer to `PATH`, or run `python3 ~/.mivo/app/mivo.py`. |
| `Permission denied` on a script (noexec mount) | Run it through the interpreter: `sh gradlew`, `bash run.sh`. |
| The model ignores tools | Use a stronger model; MIVO also runs tool calls the model writes as plain text. |

## Uninstall

```bash
rm -rf ~/.mivo
rm -f $PREFIX/bin/mivo /usr/local/bin/mivo ~/.local/bin/mivo
```

---

## Bahasa Indonesia

**MIVO CODE** adalah AI coding agent berbasis terminal untuk Termux, Ubuntu/Debian (termasuk proot), dan Linux/macOS lainnya. Cukup masukkan API key, Base URL (berakhiran `/v1`) dan ID model dari penyedia yang kompatibel dengan OpenAI, lalu AI biasa berubah menjadi AI coding yang bisa membaca proyek, membuat dan mengedit file, menjalankan perintah, dan memperbaiki kesalahannya sendiri.

### Install

**Termux**

```bash
pkg update && pkg install -y git
git clone https://github.com/WIJI-THUKUL/mivo.git
cd mivo
bash mivo.sh
```

**Ubuntu/Debian:** ganti baris pertama dengan `apt update && apt install -y git`, sisanya sama.

Installer mengenali sistemnya sendiri: di Termux memakai `pkg`, dan jika `pkg` tidak ada atau gagal otomatis berganti ke `apt`. Python dipasang otomatis bila belum ada.

Cek hasilnya dengan `mivo --version`. Untuk memperbarui: `cd mivo && git pull && bash mivo.sh`.

### Menjalankan

```bash
mivo
```

1. **Pertama kali:** isi `API key` (tampil sebagai `*`), `Base URL`, dan `Model ID`. Key diverifikasi sebelum disimpan.
2. **Pilih path:** ketik folder, misalnya `/storage/emulated/0/ProyekSaya`, atau tekan Enter untuk memakai folder home Termux. Untuk penyimpanan internal jalankan `termux-setup-storage` sekali.
3. **Ngobrol dengan AI**, misalnya: `buatkan aplikasi todo web dengan HTML, CSS, JS lalu jalankan servernya`.

### Fitur singkat

- Kode tampil langsung (streaming) dalam blok berwarna dan **otomatis tersimpan** ke file/folder.
- **Izin minimal:** hanya gradle, git yang mengubah repo, dan instalasi yang bertanya, cukup satu tombol (Enter = ya). Ganti mode dengan `/mode auto|ask|yolo`.
- **Memori tajam:** AI selalu menerima peta proyek terbaru, daftar file yang ia ubah, dan catatan proyek.
- **Riwayat chat:** `/riwayat` untuk memulihkan chat sebelumnya. `/undo` untuk membatalkan perubahan file terakhir.
- **Instruksi sendiri:** `/prefensi` untuk mengetik atau paste instruksi dan system prompt.
- **Web search:** `/addweb`, isi API key, Base URL, dan Model ID (browser).
- **Skills dan plugin:** 19 skills bawaan yang aktif otomatis menurut kata kunci, plus plugin Python.
- **Paste teks panjang** tetap menjadi satu prompt. Untuk baris baru saat mengetik, akhiri baris dengan `\` lalu Enter.

### Hapus data

```bash
rm -rf ~/.mivo
rm -f $PREFIX/bin/mivo /usr/local/bin/mivo ~/.local/bin/mivo
```

---

Made by **Wiji** & **Claude**.
