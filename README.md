# Personal AI Agent

A voice assistant I'm building to learn how AI agents really work. I press Enter once and then just talk to it, back and forth, like a conversation. It can search my documents and the live web, manage my calendar, send an email, and remember things I ask it to keep.

I'm a university student (Business Administration + AI). I built this one feature at a time, broke plenty along the way, and wrote down the lessons below.

## What it can do

- Hands-free conversation: press Enter once, then talk. It notices when I stop speaking, answers out loud, and listens again. Esc ends the session. Speech-to-text (faster-whisper) and text-to-speech (Piper) run locally.
- Uses tools on its own when it needs them, and can chain several for one request (with a step limit):
  - search my PDF and Word documents and say which file the answer came from
  - search the live web for news, prices or who currently holds a role
  - summarize CSV and Excel files
  - view, create and delete Google Calendar events
  - send email, but only to one pre-approved address
  - open a small allow-list of apps and YouTube searches
- Remembers recent conversations, plus long-term facts that it only saves or forgets when I explicitly ask.
- Asks me to type yes before anything risky (files, email, calendar changes, saving facts). Keyboard only, so a misheard word can never approve an action.
- Logs every tool call to a local audit trail.
- Runs offline with Ollama, or switches to Groq for much faster replies with one line of config.

## How it works

1. The microphone opens and the agent waits for speech. It measures the room noise first, and decides I've finished when it hears about 1.2 seconds of quiet.
2. Whisper turns the recording into text.
3. The text goes to the LLM together with the list of tools. Before that, a few checks in code look at my words: if I asked for an action or for current facts, the model is required to call a real tool (the web search tool, for current facts).
4. Each tool call runs in a loop of at most 7 steps. Risky tools stop and wait for me to type yes. Every call is written to the action log.
5. The final answer is spoken with Piper, and the microphone opens again for the next turn.

| File | What it does |
|---|---|
| chat.py | Main loop, LLM calls, tool loop and the safety checks |
| voice.py | Microphone, end-of-speech detection, Whisper and Piper |
| tools.py | Tool definitions and which tools count as risky |
| safe_paths.py | The single path check every file tool goes through |
| web_search.py | Tavily search with results labelled as untrusted |
| automation.py | Apps, sandbox folders, email and Google Calendar |
| rag.py, data_analysis.py | Document search (ChromaDB) and CSV/Excel summaries |
| memory.py, fact_memory.py | Conversation history and saved facts (SQLite) |
| action_logger.py | Audit log of every tool call |

## Setup

```bash
git clone https://github.com/hasan-murad1/personal-ai-agent.git
cd personal-ai-agent
python -m venv venv
venv\Scripts\activate

pip install ollama groq chromadb sentence-transformers pypdf python-docx faster-whisper sounddevice numpy scipy piper-tts python-dotenv google-auth-oauthlib google-auth-httplib2 google-api-python-client pandas openpyxl keyboard

ollama pull qwen3:4b
python -m piper.download_voices en_US-lessac-medium
python chat.py
```

Secrets go in a `.env` file, which is never committed. Only the first one is needed with Groq; without the others the related feature just says it is not configured.

| Variable | Used for |
|---|---|
| GROQ_API_KEY | Cloud LLM (free tier). Not needed with Ollama. |
| TAVILY_API_KEY | Web search (free tier, no card). |
| AGENT_EMAIL, AGENT_EMAIL_PASSWORD | The test Gmail account the agent sends from (App Password, not the real one). |
| ALLOWED_RECIPIENT | The only address the agent may email. |

For the calendar, put a Google Cloud OAuth `credentials.json` in the project root and run `python calendar_test.py` once to sign in. The Groq model name in `chat.py` must be one that exists in your own Groq account. Set `SESSION_MODE = False` in `chat.py` for classic push-to-talk.

If it hears nothing or writes nonsense, run `python mic_test.py` to check the microphone level. If the calendar stops working, run `python calendar_test.py` again.

## How it was built

| Phase | What was added |
|---|---|
| 1-3 | Chat loop with Ollama, SQLite memory, first tools (a calculator built on `ast`, not `eval`) |
| 4-6 | Document search (RAG) as a tool, a safety layer with sandboxed folders, multi-step tool use |
| 7-9 | Voice in and out, allow-listed apps, email, YouTube and Google Calendar |
| 10 | CSV and Excel analysis, switchable Ollama/Groq, the action log |
| 11 | Long-term fact memory and code-level checks against fake "done" replies |
| 12 | Live web search and microphone silence detection |
| 13 | Path-check and calendar sign-in fixes, then hands-free session mode |

## How I test it

There is no automated test suite yet; these are the checks I actually run.

- `mic_test.py` records three seconds, prints the input level and plays it back, so I can tell a microphone problem from a code problem.
- `vad_test.py` runs end-of-speech detection in my real room and reports CPU use while listening.
- `calendar_test.py` signs in to Google and lists upcoming events. It never changes the calendar.

I don't take the agent's word for anything. To confirm an action happened I check the action log, the database or the GitHub page. When I search for something and find nothing, I first search for something I know is there, so an empty result actually means something. For safety fixes I write the attack first, for example a path into `agent_workspace_evil`, show that the old code let it through, then show the new code blocks it, and run it again on Windows. For the forced web search I also check the opposite case: "what is the current time" must use the clock, not the web.

## What I learned

The model will say it did something without doing it. It told me events were deleted and facts were forgotten, and once showed me an action log it had made up, all without calling a tool. A prompt rule helped but did not stop it. What worked was a check in code: if my message asks to delete, forget, send or remember, the model is required to make a real tool call.

"Use a tool" is not the same as "use the right tool". Asked who the prime minister of Bangladesh is, it answered from old training data. Forcing any tool was not enough, since checking the clock also counts. For current-fact questions I now force the web search tool by name.

Web results are untrusted input. A page can contain instructions aimed at the AI, so results are labelled as outside text and never treated as commands. The same thinking is why file access goes through one strict path check: my first version compared paths as text, and a folder named `agent_workspace_evil` slipped through because it starts with `agent_workspace`.

The agent's own words are not evidence. I only trust the database, the action log or the GitHub page.

One blocking call can freeze everything. When the calendar needed a new sign-in, a hidden browser window hung the whole voice loop. Now the agent never opens that window; it tells me to run the sign-in script instead.

Measure before you blame the code. When speech recognition went wrong, the real problem was a microphone sending almost nothing. Now the agent warns me when a recording is silent. Measuring also showed that listening in session mode uses about 0.5% of one CPU core.

Hands-free needs extra care around confirmations. The microphone is only open while it is listening, so it never hears itself or my typing, and keys pressed earlier are cleared before a yes/no prompt so a stray Enter can never answer it.

Once something is pushed, it stays in the git history. My email was hardcoded in an early commit. It lives in `.env` now, and I scan for secrets before pushing.

## Known limitations

- Tool calling is less reliable than with frontier models and varies between models.
- The checks that force tool calls are pattern-based, so they reduce the risk rather than remove it, and they only work with Groq.
- Groq and web search send data to cloud services; fully local mode is private but slow on a CPU.
- End-of-speech detection uses loudness, so a noisy room can delay it. Speech recognition is English only.
- Esc is detected system-wide, so pressing it in another window also ends the session.
- Only the last 20 messages are kept as conversation context.

## Ideas for later

- Automated tests (pytest) for the path check, the end-of-speech detector and the tool-forcing patterns
- A "Hey Jarvis" wake word in place of the first Enter
- Shorter spoken answers, tuned for voice
- LoRA or QLoRA fine-tuning experiments on a free cloud GPU

## License

MIT, see [LICENSE](LICENSE).

This is a personal learning project, not production software. File and app access is limited to sandbox folders and an allow-list, and email and calendar access to one test account and recipient.