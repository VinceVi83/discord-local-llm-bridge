# A.L.I.S.U Configuration Guide

To customize the LLM's behavior in this channel, modify the **Channel Topic**. The bot parses these settings before every generation.

## Topic Structure
`parameter: value | parameter: value --- System Prompt`

---

## ⚙️ Technical Settings (Before the `---`)
You can combine multiple options using the `|` separator:

* **model**: The Ollama model name (e.g., `batiai/qwen3.5-9b`).
* **profile**: Load a predefined preset: `default`, `thinking_webdev`, `instruct_general`, or `instruct_reasoning`.
* **temp**: Adjust creativity from 0.0 to 1.0 (e.g., `temperature: 0.7`).
* **num_predict**: Maximum number of tokens to generate (e.g., `num_predict: 1000`).
* **soul**: Injects a specific personality trait into the AI.

---

## System Prompt (After the `---`)
Everything following the triple dashes defines the **AI's role and instructions** for this specific channel.

### Copy-Paste Example:
`model: batiai/qwen3.5-9b | profile: instruct_reasoning | temp: 0.7 --- ## Role: You are a senior Python developer. Provide secure, optimized code and explain your logic concisely.`

---

## Commands
* `!help`: Displays this configuration guide.
* `!archive_clean`: Wipes the channel history while migrating all Topic settings to a new channel.
* `!restart`: Restart application.