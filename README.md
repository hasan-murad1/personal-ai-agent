# Personal AI Agent

A voice-controlled personal assistant I'm building to learn how AI agents actually work under the hood. You press Enter, talk to it, and it answers out loud. Behind that it can search my documents, look things up on the web, manage my calendar, send an email, and remember facts I ask it to keep.

I'm a university student (Business Administration + AI), and this is a learning project. I built it one feature at a time, broke a lot of things along the way, and wrote down what I learned below.

## What it can do

- Talks by voice: push-to-talk recording, local speech-to-text (faster-whisper) and local text-to-speech (Piper). You can skip a reply mid-sentence with Space.
- Remembers recent conversations across sessions, plus a separate list of long-term facts that it only saves when I explicitly ask it to ("remember that...") and deletes when I ask it to forget.
- Answers questions from my own PDF and Word documents, and says which file the answer came from.
- Searches the live web for current information such as news, prices, or who currently holds a position. Results come back as a short list of titles, snippets and links.
- Summarizes CSV and Excel files (row counts, columns, basic statistics).
- Views, creates and deletes Google Calendar events.
- Sends email from a dedicated test account, but only to one pre-approved address.
- Opens a small allow-list of apps (Notepad, Calculator) and YouTube search results.
- Decides by itself when it needs a tool, and can chain several tools for one request, with a hard cap on the number of steps.
- Asks me to type yes or no before anything risky (writing or deleting files, sending email, changing the calendar, saving or forgetting facts). This is keyboard only on purpose, so a misheard word can never approve an action.
- Logs every tool call to a local audit trail that I can check later.
- Runs fully offline with Ollama, or switches to Groq for much faster replies with one line of config.

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

Secrets live in a `.env` file in the project root, which is never committed. Only the first one is needed if you use Groq; everything else is optional and the related feature simply reports that it is not configured.

| Variable | What it is for |
|---|---|
| GROQ_API_KEY | Cloud LLM (free tier). Not needed with Ollama. |
| TAVILY_API_KEY | Web search (free tier, no card needed). |
| AGENT_EMAIL | The test Gmail account the agent sends from. |
| AGENT_EMAIL_PASSWORD | A Gmail App Password for that account, not the real password. |
| ALLOWED_RECIPIENT | The only address the agent is allowed to email. |

For the calendar you also need a Google Cloud OAuth `credentials.json` in the project root. Run `python calendar_test.py` once to sign in; it saves a `token.json` that the agent reuses.

The Groq model name in `chat.py` has to be a model that is available in your own Groq account.

## Troubleshooting

- The agent hears nothing or writes nonsense: run `python mic_test.py`. It records three seconds, prints the input level and plays it back. If the peak level is tiny, the problem is the microphone or Windows settings, not the code.
- Calendar stops working: the Google token has expired. Delete `token.json` and run `python calendar_test.py` again.

## How it was built

One capability at a time:

| Phase | What was added |
|---|---|
| 1 | Basic chat loop with Ollama |
| 2 | Conversation memory (SQLite) |
| 3 | Tool calling: a calculator built on `ast` instead of `eval`, and the date and time |
| 4 | Document search (RAG) as a tool the agent chooses to use |
| 5 | Safety layer for risky tools, with file access limited to a sandbox folder |
| 6 | Multi-step tool use with a step limit |
| 7 | Voice input and output, later made skippable mid-reply |
| 8 | Limited computer automation, allow-listed apps only |
| 9 | Email, YouTube search and Google Calendar |
| 10 | CSV and Excel analysis, a switchable Ollama/Groq layer, and the action log |
| 11 | Long-term fact memory, plus code-level checks against fake "done" replies |
| 12 | Live web search, English-only transcription, and microphone silence detection |

## What I learned

Small models can fake tool calls. The local model sometimes wrote tool-call JSON as plain text instead of actually calling the tool, which quietly skipped my safety checks. A small detector now catches that and makes it try again.

Tools should report what really happened, not just "success". When the file tool only said it had worked, the model invented its own summary of the content. Returning the exact text that was written fixed most of that.

A model can claim it did something without doing anything. It told me events were deleted, facts were forgotten, and once showed me an action log it had made up, all without calling a single tool. A system prompt rule helped but did not stop it. What finally worked was checking my own message in code: if I ask it to delete, forget, send or remember something, the first model call is required to produce a real tool call. A second check catches replies that claim an action when no tool ran.

"Use a tool" is not the same as "use the right tool". The model once answered "who is the prime minister of Bangladesh" from old training data. Forcing it to call any tool was not enough, since it could just check the clock and stop. For questions about current facts I now force the web search tool by name.

Search results are untrusted text. A web page can contain instructions aimed at the AI, so results are clearly labelled as outside content that must never be treated as commands, and the agent is told never to put my personal details into a search.

The agent's own words are not evidence. Many times it said something worked when it had not. I only trust the database, the action log, or the actual GitHub page.

OAuth works differently from an API key. Google Calendar needed a consent screen, a desktop OAuth client and a token that refreshes itself, instead of one fixed key.

One blocking call can freeze everything. The first time the calendar needed new permission it opened a browser window in the background, and the whole voice loop hung until I dealt with it.

Switching LLM providers shows how much you depend on one API's exact format. Moving from Ollama to Groq broke on small differences in message fields. A thin `call_llm()` function keeps those details away from the rest of the code.

A silent microphone looks exactly like bad speech recognition. I spent time suspecting Whisper and my own changes before measuring the input level and finding the mic was delivering almost nothing. Now I measure first, and the agent warns me when the recording is silent.

Once something is pushed to GitHub, it stays in the history. My email address was hardcoded in an early commit. It is in `.env` now, but the old commit still has it, so I check for secrets before every push.

A tight loop can make audio stutter. Checking for the skip key as fast as possible fought with the audio playback for CPU time. A tiny sleep in the loop fixed it.

## Known limitations

- Tool calling is less reliable than with frontier models, especially across several steps, and it varies a lot between models.
- The code checks that force a tool call are pattern-based, so some requests will be missed and a few will be caught by mistake. They reduce the risk; they do not remove it.
- Forcing tool calls only works with Groq; Ollama does not support it.
- Local CPU-only inference is slow. Groq is much faster but sends my conversation to a cloud service, and web search sends the query to Tavily.
- Only the last 20 messages are kept as conversation context.
- Speech recognition sometimes mishears uncommon words, and it is set to English only.
- Email can only go to one fixed recipient. That is on purpose.
- If the calendar token is missing, the sign-in browser window can still block the voice loop.

## Ideas for later

- A hands-free session mode: press Enter once, then talk back and forth with the end of each sentence detected automatically, and later a "Hey Jarvis" wake word
- Moving the calendar sign-in completely out of the voice loop
- LoRA or QLoRA fine-tuning experiments on a free cloud GPU

## License

MIT, see the [LICENSE](LICENSE) file.

## Note

This is a personal learning project, not production software. File and automation actions stay inside sandbox folders and a short list of approved apps, and email and calendar access are limited to a single test account and recipient.