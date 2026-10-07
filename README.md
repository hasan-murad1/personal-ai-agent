
## What it can do

- Remembers conversations across sessions
- Answers questions from personal documents, with source attribution
- Analyzes CSV/Excel files and reports summary statistics
- Decides on its own when a tool is needed, and chains multiple tools together for complex requests (capped at a fixed number of steps)
- Asks for confirmation before any risky action; all file and automation access is sandboxed with path-traversal protection
- Logs every tool execution to a local audit trail it can query on request
- Opens allow-listed applications and YouTube search results
- Sends email through a dedicated account, restricted to a single pre-approved recipient
- Views, creates, and deletes Google Calendar events via OAuth
- Can run entirely offline (Ollama) or switch to faster cloud inference (Groq) with one config line
- Lets the user skip a response mid-speech instead of waiting it out

## Setup

```bash
git clone <your-repo-url>
cd personal-ai-agent

python -m venv venv
venv\Scripts\activate

pip install ollama groq chromadb sentence-transformers pypdf python-docx faster-whisper sounddevice numpy scipy piper-tts python-dotenv google-auth-oauthlib google-auth-httplib2 google-api-python-client pandas openpyxl keyboard

ollama pull qwen3:4b
python -m piper.download_voices en_US-lessac-medium

python chat.py
```

Email and calendar features require their own one-time setup (Gmail App Password in a `.env` file; a Google Cloud OAuth `credentials.json`) and are optional — the core agent works without them. Groq requires a free API key in `.env`; Ollama requires no external account.

## How it was built

Built in phases, one capability at a time:

| Phase | What was added |
|---|---|
| 1 | Basic chat loop with Ollama |
| 2 | Persistent memory (SQLite) |
| 3 | Tool calling (calculator via `ast`, not `eval`; datetime) |
| 4 | RAG as a tool the agent chooses to use |
| 5 | Safety layer for risky tools, scoped to a sandboxed workspace |
| 6 | Multi-step tool orchestration with a step limit |
| 7 | Voice I/O (Whisper + Piper), later made skippable mid-response |
| 8 | Scoped computer automation, allow-listed apps only |
| 9 | Email, YouTube search, and Google Calendar (OAuth) integration |
| 10 | CSV/Excel analysis, a swappable Ollama/Groq provider layer, and an action-logging audit trail |

## What I learned

- **Small models can fake tool calls.** The model occasionally wrote JSON-like text directly into its response instead of using real function calling, silently bypassing the safety layer. Fixed with a detector that catches the pattern and forces a retry.
- **Tool responses need to confirm what actually happened, not just that it succeeded.** A file-write tool that only said "success" let the model hallucinate its own content summary. Returning the actual written content fixed most of this.
- **A model can claim success without ever calling a tool at all.** Separately from malformed tool calls, the model sometimes answered a delete/data request directly in text — confidently saying an event was deleted, or inventing a plausible-looking action log — without attempting any tool call, which silently bypassed confirmation entirely. This was a more dangerous failure mode than a malformed call, since nothing in the code flagged it. Fixed with an explicit system prompt rule: never claim an action or present data without having actually called the corresponding tool.
- **OAuth is a different trust model than an API key.** Setting up Google Calendar access meant learning a consent screen, a desktop OAuth client, and a token that's requested once and refreshed afterward, instead of a single static credential.
- **A blocking call can silently freeze an entire voice loop.** The first time the calendar tool needed a new OAuth permission, it opened a browser window in the background waiting for approval — and because the agent's flow is single-threaded, the whole app hung until that window was handled.
- **Switching LLM providers exposes how much you relied on one API's exact shape.** Moving from Ollama to Groq broke on missing `role`, string-vs-object `tool_calls.arguments`, and missing `id`/`tool_call_id` fields — all differences invisible until tool-calling actually ran. A thin `call_llm()` abstraction isolated the rest of the app from these provider-specific details.
- **Stopping TTS mid-sentence can glitch the audio output.** A tight polling loop checking for a skip key-press competed with the audio thread for CPU time, causing stutter. A small `time.sleep()` in the loop fixed it.

## Known limitations

- Tool-calling is less reliable than frontier models, especially across multiple steps, and varies noticeably between providers/models
- CPU-only local inference is noticeably slower than cloud-based assistants; Groq trades that off for reduced privacy/offline capability
- Only the last 20 messages are kept as context; no long-term fact memory yet
- Speech recognition occasionally mishears uncommon words (e.g. "sandbox"); partially mitigated with a prompt hint
- Email is restricted to a single hardcoded recipient by design, not general-purpose messaging
- Calendar and email require one-time external setup (OAuth consent, App Password) and are not part of the zero-setup local core

## Ideas for later

- Web search tool for real-time information lookup
- Fact-based long-term memory, separate from raw conversation history
- Wake-word activation instead of push-to-talk
- LoRA/QLoRA fine-tuning experiments

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Note

This is a personal learning project, not production software. All file and automation actions are restricted to sandboxed folders and a small list of approved applications. Email and calendar access are scoped to a single test account/recipient.