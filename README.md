# discord-local-llm-bridge (dLLb)
Discord bot with a FastAPI API for notifications and status, and conversations connected to a LLM client.
The repository also includes attachment processing, channel cleanup, and plugins.

## Features
- LLM replies to Discord messages, with an optional prompt in the channel topic.
- `GET /status` and `POST /send` API endpoints for status and notifications.
- Local fallback audio transcription and reading of text attachments.
- Plugins loaded from `plugins/` and periodic cleanup of temporary channels.

## Prerequisites
- Python (minimum version not declared) and a configured Discord application/bot.
- The `common` submodule, required for configuration and LLM access.
- Discord read/send intents and permissions; channel management for cleanup.
- Python dependencies: `discord.py`, `fastapi`, `uvicorn`, `pydantic`, `requests`, `APScheduler`, `faster-whisper`.

## Installation
From a copy of the repository, at its root:
```sh
git submodule update --init --recursive
python -m venv .venv
. .venv/bin/activate
python -m pip install discord.py fastapi uvicorn pydantic requests APScheduler faster-whisper
```
No dependency/lock file is provided; the list above is based on imports. `mcp_bot.py` also requires the `mcp` package.

## Configuration
Complete the `config.yaml` file created in `~/Documents/Projectdir` at execution, using [`config_example.yaml`](config_example.yaml) as a reference. Replace the placeholders with your own values and never share your credentials.

## Launch

```sh
python main.py
```

## Usage example
Check the local API (example port):
```sh
curl http://127.0.0.1:8000/status
```
In Discord, send a message in a supported channel to query the LLM; `!help` displays the configured text.

## Structure
```text
main.py                  bot + API startup
discord_bot.py           messages, LLM, and plugins
discord_janitor.py       channel cleanup
attachment_router.py     attachment classification
whisper_engine.py        local transcription
agents/                  prompts
plugins/                 agenda and multiroom plugins
common/                  external submodule
config_example.yaml      configuration example
LICENSE                  MIT license
```

## Extending
- Add `plugins/<name>/service.py` and define `handle_<name>` handlers there.
- The channel name prefix routes messages to the corresponding plugin.
- For a new attachment type, add both classification **and** processing in `DiscordBot.process_attachments`.

## Credits and license
Credit: Vincent NGUYEN, © 2026. MIT license; see [`LICENSE`](LICENSE).
