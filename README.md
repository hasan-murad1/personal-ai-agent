# Personal AI Agent

A locally-run personal AI assistant built with Python and Ollama. It combines reasoning, tool use, document retrieval, persistent memory, and voice interaction into a working agent — fully local, with no cloud API costs.

Built as a hands-on learning project to understand how AI agents actually work, not just how to call an LLM API.

## Why this approach

Most beginner agent projects wrap an LLM in a chat interface and stop there. This project treats the LLM as one piece of a larger system: it reasons and decides what to do, while tools, memory, retrieval, and a safety layer handle everything else.

## Tech stack

| Component | Technology | Purpose |
|---|---|---|
| LLM | Ollama (Qwen3 4B, quantized) | Local reasoning, zero API cost |
| Memory | SQLite | Persistent conversation history |
| RAG | ChromaDB + Sentence Transformers | Search personal PDFs/DOCX |
| Speech-to-text | faster-whisper | Local voice input |
| Text-to-speech | Piper | Local voice output |
| Automation | Python | Allow-listed apps, sandboxed file access |

Built and tested on: Intel i7-10700, 16GB RAM, no dedicated GPU.

## Architecture

Voice or text input
|
Speech-to-text (Whisper)
|
Agent core (Ollama + tool router)

memory (SQLite)
safety/confirmation layer
tools: calculator, RAG search, file I/O, automation
|
Text-to-speech (Piper)
|
Voice or text output

## What it can do

- Remembers conversations across sessions
- Answers questions from personal documents, with source attribution
- Decides on its own when a tool is needed, and chains multiple tools together for complex requests (capped at a fixed number of steps to avoid runaway loops)
- Asks for confirmation before any risky action; all file and automation access is sandboxed with path-traversal protection
- Works fully offline through voice
- Costs nothing to run beyond your own hardware

## Setup

```bash
git clone <your-repo-url>
cd personal-ai-agent

python -m venv venv
venv\Scripts\activate

pip install ollama chromadb sentence-transformers pypdf python-docx faster-whisper sounddevice numpy scipy piper-tts

ollama pull qwen3:4b
python -m piper.download_voices en_US-lessac-medium

python chat.py
```

## How it was built

Built in phases, one capability at a time:

| Phase | What was added |
|---|---|
| 1 | Basic chat loop with Ollama |
| 2 | Persistent memory (SQLite) |
| 3 | Tool calling (calculator via `ast`, not `eval`; datetime) |
| 4 | RAG as a tool the agent chooses to use |
| 5 | Safety layer for risky tools, scoped to a sandboxed workspace |
| 6 | Multi-step tool orchestration with a hard step limit |
| 7 | Voice I/O (Whisper + Piper) on top of the existing pipeline |
| 8 | Scoped computer automation, allow-listed apps only |

## What I learned

- **Small models can fake tool calls.** The 4B model occasionally wrote JSON-like text directly into its response instead of using real function calling, silently bypassing the safety layer. Fixed with a detector that catches the pattern and forces a retry.
- **Tool responses need to confirm what actually happened, not just that it succeeded.** A file-write tool that only said "success" let the model hallucinate its own content summary — in one case writing a placeholder like `[revenue_value]` to the file while reporting the real number back to me. Returning the actual written content from the tool fixed most of this.
- **RAG quality depends on phrasing.** "Who is the CEO" returned weaker results than "leadership team," since the latter matched the document's actual heading. Not a bug — just how semantic search works.
- **Speed is a real hardware trade-off, not something to code around.** Multi-step tool calls mean multiple LLM passes; on CPU-only hardware, that adds up. This is the honest cost of staying fully local and free.

## Known limitations

- Tool-calling is less reliable than frontier models, especially across multiple steps
- Noticeably slower than cloud-based assistants
- Only the last 20 messages are kept as context; no long-term fact memory yet
- Speech recognition occasionally mishears uncommon words (e.g. "sandbox"); partially mitigated with a prompt hint

## Ideas for later

Fact-based long-term memory, CSV/Excel analysis, LoRA fine-tuning experiments, wake-word activation, action logging.

## Note

This is a personal learning project, not production software. All file and automation actions are restricted to sandboxed folders and a small list of approved applications.