# Character Chat AI

Chat with multiple AI characters, each with a distinct personality, across three thin
clients — a web PWA, an Android app, and a Telegram bot — all backed by one shared
FastAPI service. All business logic (persona injection, memory, model routing, history)
lives in the backend; the clients only render UI and call the API.

## Live deployment

- **Telegram bot:** [@CharacterChatX_bot](https://t.me/CharacterChatX_bot) — open it,
  send `/start` to list characters, `/use luna` (or `elias` / `sergeant_kane`) to pick
  one, then just chat.
- **Backend API:** hosted on Render (`https://chat-with-ai-x.onrender.com`), backed by
  Neon Postgres, using OpenRouter for inference. API-key protected.
- **Android app:** download the latest `.apk` from the repo's
  [Releases](../../releases) page and install it on your phone.
- **Web app:** deployed on Vercel.

### Telegram bot commands

| Command | What it does |
|---------|--------------|
| `/start` | List the available characters |
| `/use <id>` | Pick a character to talk to (e.g. `/use elias`) |
| `/help` | Show characters and usage |

The bot maps each Telegram chat to a persistent session, so it remembers your
conversation. The webhook is verified with a secret token, and the bot reaches the chat
logic inside the backend directly (it does not need the public API key).

## Architecture

One shared backend holds all logic; the three clients are thin and call the same API.

```
        ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
        │  Web (PWA)   │   │  Android app  │   │ Telegram bot │
        │ Vercel/static│   │  (Capacitor)  │   │  (webhook)   │
        └──────┬───────┘   └──────┬────────┘   └──────┬───────┘
               │  HTTPS + API key │                   │ webhook
               └──────────┬───────┴─────────┬─────────┘
                          ▼                  ▼
                 ┌─────────────────────────────────────┐
                 │     FastAPI backend (Render)         │
                 │  auth → rate-limit → routes          │
                 │  PersonaManager · ChatService        │
                 │  MemoryManager · LLMClient           │
                 └───────┬───────────────────┬──────────┘
                         ▼                   ▼
                ┌──────────────────┐  ┌────────────────────────┐
                │ Postgres (Neon)  │  │ LLM provider (OpenAI-   │
                │ sessions,        │  │ compatible): Ollama dev │
                │ messages,        │  │ Groq / Gemini in prod   │
                │ embeddings       │  └────────────────────────┘
                └──────────────────┘
```

### Request pipeline (one chat turn)

```
Client sends {session_id, message}
   │
   ▼
[Auth] valid API key?  ──no──▶ 401
   │yes
   ▼
[Rate limit] under quota? ──no──▶ 429
   │yes
   ▼
[Validate] non-empty, ≤4000 chars? ──no──▶ 422 (nothing saved)
   │yes
   ▼
[ChatService] load session + persona
   │
   ▼
[MemoryManager] assemble prompt:
   system_directive + speech_patterns + examples
   + last N messages (short-term)
   + [optional] relevant older messages (RAG)
   + new user message
   │
   ▼
[LLMClient] call provider (timeout) ──fail/timeout──▶ save user msg only, return error
   │ok
   ▼
[Persist] save user + assistant messages (atomic)
   │
   ▼
[optional] embed both messages → store for RAG
   │
   ▼
return assistant message  ──▶  client renders + saves session id locally
```

### Project layout

- **backend/** — FastAPI service: personas, memory, chat orchestration, provider
  abstraction, auth/rate limiting, Telegram webhook.
- **web/** — React + Vite PWA; also wrapped as the Android app via Capacitor.

## Run locally

### 1. Backend (needs local Ollama with `gemma3:4b` + `nomic-embed-text`)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env        # defaults to local SQLite + Ollama, auth off
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8099
```

Tip: warm the model once so the first reply beats the 30s timeout:
`ollama run gemma3:4b "hi"`.

Health check: open http://127.0.0.1:8099/health and http://127.0.0.1:8099/docs.

### 2. Web PWA

```powershell
cd web
npm install
copy .env.example .env        # points at http://127.0.0.1:8099
npm run dev
```

### 3. Run tests

```powershell
# backend (property-based + unit + integration logic)
cd backend; .\.venv\Scripts\python.exe -m pytest
# web (component tests)
cd web; npm test
```

## Build the Android app

The Android app is the same web build wrapped by Capacitor (requires Android Studio).

```powershell
cd web
npm run android:sync     # vite build + cap sync android
npm run android:open     # opens the project in Android Studio to build/run the APK
```

Set `VITE_API_BASE_URL` in `web/.env` to your deployed backend URL before building the
APK (an installed app can't reach `localhost`).

## How memory works

There are two layers, and they solve different problems:

1. **Conversation continuity (always on).** Every session and message is saved in
   Postgres. The web/Android client remembers the session id per character on the device
   (localStorage), so reopening a character **continues the same conversation** and
   reloads its history. The Telegram bot maps each `chat_id` to a session for the same
   effect. A "New chat" button starts a fresh session on demand.

2. **Short-term window (always on).** Each turn includes the last `SHORT_TERM_N` messages
   (default 20) so the character stays coherent with the recent conversation.

3. **Long-term recall — RAG (optional, off by default).** For *long* conversations where
   something important scrolled out of the recent window, enable
   `LONG_TERM_MEMORY_ENABLED=true`. Each message is embedded (via the provider's embedding
   model, e.g. `nomic-embed-text` on Ollama) and stored; on each turn the most relevant
   older messages (cosine similarity ≥ 0.75, up to 10) are pulled back into the prompt.
   It degrades gracefully — if embeddings fail or the provider has none, it silently falls
   back to the short-term window.

> RAG is only needed for long-range recall. For typical chats, layers 1 + 2 already make
> the character "remember" the conversation.

## Choosing an LLM provider

The backend talks to any **OpenAI-compatible** endpoint, so switching is just env vars —
no code changes. Recommendation:

| Provider   | Best for | Notes |
|------------|----------|-------|
| **Groq**   | Primary chat in production | Free tier, extremely fast, hosts Llama/Gemma. No embeddings — keep RAG off or use another embedder. |
| **Gemini** | Great free option, has embeddings | Generous free tier, strong quality, and `text-embedding-004` for RAG. Use its OpenAI-compatible endpoint. |
| **Ollama** | Local development | Free/offline; CPU is slow (raise `LLM_TIMEOUT_SECONDS`). Has `nomic-embed-text` for RAG. |
| OpenRouter | Model variety | One key, many models. |

**Suggested setup:** develop on Ollama, run production on **Groq** for speed. If you want
long-term RAG memory in production, use **Gemini** (chat + embeddings from one provider) —
keep it as a selectable option via env.

Example env for each provider:

```ini
# Groq (fast, no embeddings)
LLM_PROVIDER=groq
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_CHAT_MODEL=llama-3.3-70b-versatile
LLM_API_KEY=gsk_xxx

# Gemini (chat + embeddings; good for RAG)
LLM_PROVIDER=gemini
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_CHAT_MODEL=gemini-2.0-flash
LLM_EMBED_MODEL=text-embedding-004
LLM_API_KEY=AIza_xxx
```

## Production providers (switch with env only, no code changes)

| Concern   | Local dev            | Production              |
|-----------|----------------------|-------------------------|
| LLM       | Ollama `gemma3:4b`   | Groq / OpenRouter       |
| Database  | SQLite (`dev.db`)    | Neon Postgres           |
| Backend   | uvicorn on localhost | Render / Fly (Docker)   |
| Web       | vite dev server      | Vercel                  |

To go to production: set `DATABASE_URL` to your Neon string, set `LLM_PROVIDER`/
`LLM_BASE_URL`/`LLM_API_KEY` to Groq, set `AUTH_ENABLED=true` with `API_KEYS`, and deploy
the backend with `render.yaml` (Render > New > Blueprint). Point the web app and Android
build at the deployed URL.

## Telegram bot (optional)

Set `TELEGRAM_BOT_TOKEN` (from BotFather) and `TELEGRAM_WEBHOOK_SECRET`, deploy, then
register the webhook:

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<your-backend>/telegram/webhook&secret_token=<SECRET>
```

In Telegram: `/start` lists characters, `/use <id>` picks one, then just chat.
