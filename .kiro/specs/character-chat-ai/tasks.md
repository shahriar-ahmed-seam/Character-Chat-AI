# Implementation Plan: Character Chat AI

## Overview

This plan converts the design into incremental coding steps, organized to follow the
design's phased delivery. Each phase is independently runnable and testable before the next
begins:

- **Phase 1** — FastAPI backend: config/fail-fast, Postgres + SQLAlchemy + Alembic,
  Persona_Manager, persistence, short-term Memory_Manager, LLM_Client (Ollama),
  Chat_Service, core endpoints, shared Pydantic contract + error envelope.
- **Phase 2** — Web PWA (React + Vite): picker, chat view, error/unsent-text retention,
  manifest + service worker.
- **Phase 3** — Telegram bot (aiogram webhook): chat_id↔session mapping, persona selection,
  message forwarding.
- **Phase 4** — Android: Capacitor wrap of the React codebase.
- **Phase 5** — Production hardening: API key auth, per-credential rate limiting, secret
  redaction, health dependency checks, deployment config; optional Long_Term_Memory
  (pgvector + nomic-embed-text RAG).

Implementation language is **Python** for the backend (FastAPI, Pydantic, SQLAlchemy,
httpx) per the design, with property-based tests using **Hypothesis** (minimum 100
iterations per property, tagged `Feature: character-chat-ai, Property {n}`). The web/Android
client is **React + Vite**, wrapped with **Capacitor**.

## Tasks

### Phase 1 — Backend (FastAPI + local Ollama)

- [x] 1. Project skeleton and fail-fast configuration
  - [x] 1.1 Scaffold the FastAPI backend project structure and tooling
    - Create the package layout (app, components, persistence, api, tests directories)
    - Add dependencies (fastapi, uvicorn, pydantic, sqlalchemy[async], alembic, httpx,
      pgvector, pytest, hypothesis) and configure pytest + Hypothesis test runner
    - _Requirements: 12.4_

  - [x] 1.2 Implement the environment configuration loader with fail-fast validation
    - Read datastore connection, provider config, and general settings from environment
    - Build `ProviderConfig` (provider, base_url, chat_model, embed_model, api_credential)
    - On startup, abort and name each missing/empty required value
    - _Requirements: 7.2, 7.5, 12.4, 12.5_

  - [x]* 1.3 Write property test for provider configuration resolution
    - **Property 22: Provider configuration resolves from environment**
    - **Validates: Requirements 7.2**

  - [x]* 1.4 Write unit tests for fail-fast configuration
    - Missing provider/datastore values abort startup and name each missing value
    - _Requirements: 7.5, 12.5_

- [ ] 2. Database setup (Postgres + SQLAlchemy + Alembic)
  - [x] 2.1 Configure the async SQLAlchemy engine, session factory, and connection retry
    - Connect to Postgres with 3 attempts within a 30-second window before reporting failure
    - _Requirements: 6.6, 12.6_

  - [x] 2.2 Define ORM models for characters, sessions, messages, embeddings, telegram_map
    - Use UUID session id, bigserial message id, pgvector embedding column
    - _Requirements: 6.1, 6.2, 5.1_

  - [ ] 2.3 Create Alembic migration environment and initial migration
    - Include the pgvector extension and embedding vector column
    - _Requirements: 6.1, 6.2, 5.1_

  - [ ]* 2.4 Write unit test for database connection retry
    - 3 attempts within 30s then surface a connection failure
    - _Requirements: 12.6_

- [x] 3. Persona_Manager and Persona_Schema
  - [x] 3.1 Implement the Pydantic Persona_Schema and DialogueExample models
    - Enforce presence, non-emptiness, and length constraints (id 1–64, name/archetype
      1–200, system_directive 1–8000, non-empty example_dialogue and speech_patterns)
    - _Requirements: 1.1, 1.2_

  - [x] 3.2 Implement PersonaManager load/validate, duplicate detection, and startup gating
    - Reject invalid definitions individually with field-level reasons, retain valid ones
    - Reject all definitions sharing a duplicate id and report the conflicting id
    - Load/validate at startup and refuse chat requests if any definition fails
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 3.3 Implement persona listing projection and lookup
    - `list_personas` returns id/name/archetype only; `get` resolves by id
    - _Requirements: 2.1, 2.2, 2.3_

  - [x]* 3.4 Write property test for persona validation
    - **Property 1: Persona validation accepts iff well-formed**
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [x]* 3.5 Write property test for batch loading
    - **Property 2: Batch loading retains valid and reports invalid fields**
    - **Validates: Requirements 1.4**

  - [x]* 3.6 Write property test for duplicate id rejection
    - **Property 3: Duplicate ids reject all conflicting definitions**
    - **Validates: Requirements 1.5**

  - [x]* 3.7 Write property test for persona listing projection
    - **Property 4: Persona listing exposes summary fields only**
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [ ]* 3.8 Write unit tests for persona startup lifecycle
    - Chat refused until persona load completes; invalid startup defs block serving
    - _Requirements: 1.6, 1.7_

- [x] 4. Persistence layer (repositories)
  - [x] 4.1 Implement the session repository
    - Create sessions with unique identifiers and persist them; fetch by id
    - _Requirements: 6.1_

  - [x] 4.2 Implement the message repository with atomic turn writes and ordered history
    - Persist role/content/persona_id/timestamp; atomic multi-message writes (no partial
      writes); history ordered by ascending timestamp, ties by ascending insertion id
    - _Requirements: 6.2, 6.3, 6.4_

  - [x]* 4.3 Write property test for session id uniqueness
    - **Property 16: Session creation produces unique persisted identifiers**
    - **Validates: Requirements 6.1**

  - [x]* 4.4 Write property test for message round-trip
    - **Property 17: Message persistence round-trip preserves fields**
    - **Validates: Requirements 6.2**

  - [ ]* 4.5 Write property test for persistence atomicity
    - **Property 18: Persistence failure is atomic**
    - **Validates: Requirements 6.3**

  - [x]* 4.6 Write property test for history ordering
    - **Property 19: History ordering is deterministic**
    - **Validates: Requirements 6.4**

  - [x]* 4.7 Write property test for unknown session history
    - **Property 20: Unknown session history never creates a session**
    - **Validates: Requirements 6.5**

  - [ ]* 4.8 Write property test for state survival across restart
    - **Property 21: State survives restart unchanged**
    - **Validates: Requirements 6.6, 6.7**

- [x] 5. Memory_Manager (short-term memory)
  - [x] 5.1 Implement effective-N configuration resolution
    - Read N from env (default 20, valid 1–100); reject invalid/out-of-range, fall back to
      20, and record an error
    - _Requirements: 4.1, 4.5, 4.6_

  - [x] 5.2 Implement the short-term sliding window
    - Return the most recent min(len, N) messages ordered oldest-to-newest
    - _Requirements: 4.2, 4.3, 4.4_

  - [x] 5.3 Implement context assembly (short-term-only path)
    - Combine system_directive, example_dialogue, speech_patterns, ordered window, and the
      new message (short-term only when Long_Term_Memory is disabled)
    - _Requirements: 3.1, 3.2, 5.4_

  - [x]* 5.4 Write property test for the short-term window
    - **Property 8: Short-term memory is the correctly ordered most-recent-N window**
    - **Validates: Requirements 4.2, 4.3, 4.4**

  - [x]* 5.5 Write property test for N resolution
    - **Property 9: Window size N resolves safely from configuration**
    - **Validates: Requirements 4.1, 4.5, 4.6**

  - [x]* 5.6 Write property test for assembled model request content
    - **Property 7: Assembled model request contains required persona context and the new message**
    - **Validates: Requirements 3.1, 3.2**

- [ ] 6. LLM_Client (OpenAI-compatible, Ollama)
  - [x] 6.1 Implement the LLM_Client over an OpenAI-compatible interface
    - `chat_completion` and `embeddings` via httpx with a 30-second timeout
    - Return provider-unreachable on timeout (backend stays running); auth-failure on 401/403
      with no retry; route Ollama chat and nomic-embed-text embeddings
    - _Requirements: 7.1, 7.3, 7.4, 7.6, 7.7_

  - [ ]* 6.2 Write unit tests for LLM_Client behaviors
    - Timeout handling, provider-auth rejection (no retry), Ollama routing, and
      provider-swap via config change with no code change
    - _Requirements: 3.6, 7.1, 7.3, 7.4, 7.6, 7.7_

- [x] 7. Chat_Service orchestration
  - [x] 7.1 Implement `handle_turn`
    - Validate message (non-empty, ≤4000) with no persistence/LLM call on failure; verify
      persona exists; assemble context; call LLM_Client with 30s timeout; persist both
      messages atomically on success; persist only the user message on failure/timeout
    - _Requirements: 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x]* 7.2 Write property test for successful turn persistence
    - **Property 10: Successful turn persists user and assistant messages**
    - **Validates: Requirements 3.3, 3.4**

  - [x]* 7.3 Write property test for invalid message handling
    - **Property 11: Invalid message is rejected with no side effects**
    - **Validates: Requirements 3.5**

  - [x]* 7.4 Write property test for failed generation handling
    - **Property 12: Failed generation persists only the user message**
    - **Validates: Requirements 3.6, 3.7**

- [x] 8. API contract and core endpoints
  - [x] 8.1 Define the shared Pydantic request/response models and error envelope
    - Requests (CreateSessionRequest, PostMessageRequest) and responses (PersonaSummary,
      MessageResponse, SessionResponse, HistoryResponse, ErrorResponse); central error
      serializer that redacts credentials and provider secrets
    - _Requirements: 11.7, 13.1, 13.3, 13.4_

  - [x] 8.2 Implement `GET /health`
    - Check datastore and provider reachability within 2s; name unavailable dependencies;
      reflect configuration-error state
    - _Requirements: 12.1, 12.2, 12.3, 12.5_

  - [x] 8.3 Implement `GET /personas`
    - Return id/name/archetype summaries; empty list when none exist
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 8.4 Implement `POST /sessions`
    - Create a session, associate the selected persona, confirm the association; unknown
      persona id returns an identifying error and does not mutate state
    - _Requirements: 2.4, 2.5, 6.1_

  - [x] 8.5 Implement `GET /sessions/{id}/history`
    - Return ordered history; unknown session returns not-found without creating a session
    - _Requirements: 6.4, 6.5_

  - [x] 8.6 Implement `POST /sessions/{id}/messages` chat-turn endpoint
    - Wire request validation to Chat_Service and return the consistent response/error shape
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ]* 8.7 Write property test for persona selection
    - **Property 5: Persona selection associates and confirms**
    - **Validates: Requirements 2.4**

  - [ ]* 8.8 Write property test for unknown persona id
    - **Property 6: Unknown persona id never mutates state**
    - **Validates: Requirements 2.5, 2.6**

  - [ ]* 8.9 Write property test for health status
    - **Property 30: Health status reflects dependency reachability**
    - **Validates: Requirements 12.3**

  - [ ]* 8.10 Write property test for request validation ordering
    - **Property 31: Request validation precedes processing and reports each failure**
    - **Validates: Requirements 13.1, 13.2**

  - [ ]* 8.11 Write property test for response schema conformance
    - **Property 32: Responses conform to the single shared schema**
    - **Validates: Requirements 13.3, 13.4**

  - [ ]* 8.12 Write integration test for an end-to-end chat turn
    - Real local Ollama chat turn plus Health_Endpoint reporting real datastore/provider
      reachability
    - _Requirements: 3.1, 3.3, 3.4, 12.1, 12.2_

- [ ] 9. Checkpoint — Phase 1 backend
  - Ensure all tests pass, ask the user if questions arise.

### Phase 2 — Web PWA (React + Vite)

- [x] 10. Web PWA client
  - [x] 10.1 Scaffold the React + Vite app and the Backend_API client module
    - Single API client that obtains all chat/persona data from the backend (no business logic)
    - _Requirements: 8.1, 8.8_

  - [x] 10.2 Implement the character picker
    - Fetch personas and render selectable items; show a no-characters indication on empty
    - _Requirements: 8.1, 8.2_

  - [x] 10.3 Implement the chat view
    - Open a conversation for the selected persona; submit and display assistant messages
    - _Requirements: 8.3, 8.4, 8.5_

  - [x] 10.4 Implement error handling with unsent-text retention
    - On error/timeout, show a failure indication and retain the user's unsent text
    - _Requirements: 8.6_

  - [x] 10.5 Add the PWA manifest and service worker
    - Provide manifest and registered service worker for installability
    - _Requirements: 8.7_

  - [x]* 10.6 Write component/interaction tests
    - Picker, chat view, empty state, and error display with unsent-text retention
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x]* 10.7 Write PWA installability smoke test
    - Manifest present and service worker registered
    - _Requirements: 8.7_

  - [ ]* 10.8 Write no-business-logic check for the web client
    - Lint/review ensuring no persona, memory, or model-routing modules in the client
    - _Requirements: 8.8_

- [ ] 11. Checkpoint — Phase 2 web PWA
  - Ensure all tests pass, ask the user if questions arise.

### Phase 3 — Telegram bot (aiogram webhook)

- [x] 12. Telegram bot client
  - [x] 12.1 Implement the aiogram webhook bot and `POST /telegram/webhook` intake
    - Webhook-mode bot that forwards user messages to the backend and replies with the
      returned assistant message
    - _Requirements: 10.1, 10.4, 10.5_

  - [x] 12.2 Implement chat_id↔session mapping
    - Use the mapped session when present; otherwise create a session and map the chat_id
    - _Requirements: 10.2, 10.3_

  - [x] 12.3 Implement persona presentation and selection
    - Present backend personas; associate a selected persona; reject selections outside the
      presented list with an invalid notification
    - _Requirements: 10.7, 10.8, 10.9_

  - [x] 12.4 Implement error/timeout notification and enforce no business logic
    - Notify the user on error/timeout leaving session state unchanged; obtain all data from
      the backend with no persona/memory/model-routing logic
    - _Requirements: 10.6, 10.10, 10.11_

  - [x]* 12.5 Write property test for chat_id session mapping
    - **Property 28: Telegram chat_id maps consistently to a session**
    - **Validates: Requirements 10.2, 10.3**

  - [x]* 12.6 Write property test for invalid persona selection
    - **Property 29: Selecting a persona outside the presented list is rejected**
    - **Validates: Requirements 10.9**

  - [ ]* 12.7 Write integration test for webhook intake
    - aiogram webhook-mode intake exercised end to end
    - _Requirements: 10.1_

- [ ] 13. Checkpoint — Phase 3 Telegram bot
  - Ensure all tests pass, ask the user if questions arise.

### Phase 4 — Android (Capacitor wrap)

- [x] 14. Android client
  - [x] 14.1 Add the Capacitor configuration wrapping the shared React codebase
    - Configure Capacitor and add the Android platform over the existing web build
    - _Requirements: 9.1, 9.2_

  - [x] 14.2 Verify picker/chat/error-retention parity through the shared codebase
    - Same persona selection, message exchange, and unsent-message retention; no business
      logic in the wrapper
    - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.7_

  - [ ]* 14.3 Write Android build smoke test
    - Capacitor wrap builds and launches as a standalone native app
    - _Requirements: 9.1, 9.6_

  - [ ]* 14.4 Write no-business-logic check for the Android wrapper
    - Ensure the wrapper contains no persona/memory/model-routing modules
    - _Requirements: 9.7_

- [ ] 15. Checkpoint — Phase 4 Android
  - Ensure all tests pass, ask the user if questions arise.

### Phase 5 — Production hardening and optional Long-Term Memory

- [x] 16. Auth and rate-limit middleware
  - [x] 16.1 Implement API key authentication middleware
    - Extract credential from `Authorization: Bearer`/`X-API-Key`; reject missing/invalid
      with a 401 before any processing
    - _Requirements: 11.1, 11.2_

  - [x] 16.2 Implement per-credential rate limiting
    - Postgres-backed counter per credential + window bucket; reject past threshold with a
      retry-after; reset count when the window elapses
    - _Requirements: 11.3, 11.4_

  - [x] 16.3 Load and validate auth/rate-limit configuration fail-fast
    - Read credentials, threshold (max requests), and window (seconds) from env; refuse
      protected endpoints and report on missing/invalid values
    - _Requirements: 11.5, 11.6_

  - [x] 16.4 Extend the error serializer to guarantee secret redaction
    - Centrally strip credential values and provider secrets from every error body
    - _Requirements: 11.7_

  - [x]* 16.5 Write property test for authentication enforcement
    - **Property 24: Authentication is enforced on protected endpoints**
    - **Validates: Requirements 11.1, 11.2**

  - [x]* 16.6 Write property test for rate-limit triggering
    - **Property 25: Rate limiting triggers past the threshold with remaining time**
    - **Validates: Requirements 11.3**

  - [x]* 16.7 Write property test for rate-limit window reset
    - **Property 26: Rate-limit window resets**
    - **Validates: Requirements 11.4**

  - [x]* 16.8 Write property test for secret redaction
    - **Property 27: Error responses redact secrets**
    - **Validates: Requirements 11.7**

  - [x]* 16.9 Write property test for fail-fast configuration completeness
    - **Property 23: Missing required configuration fails fast and names what is missing**
    - **Validates: Requirements 7.5, 11.6, 12.5**

- [ ] 17. Optional Long-Term Memory (pgvector RAG)
  - [ ] 17.1 Implement config-gated embedding generation and storage on persist
    - When enabled, embed each persisted message via nomic-embed-text and store with pgvector
    - _Requirements: 5.1_

  - [ ] 17.2 Implement long-term retrieval and context integration
    - Retrieve up to 10 messages with similarity ≥ 0.75 ordered most-to-least similar; fall
      back to short-term-only when none qualify
    - _Requirements: 5.2, 5.3_

  - [ ] 17.3 Implement graceful degradation
    - Short-term-only assembly when disabled; non-fatal embedding failure that retains the
      message and records a failure entry naming it
    - _Requirements: 5.4, 5.5_

  - [x]* 17.4 Write property test for embedding coverage
    - **Property 13: Long-term memory embeds every persisted message when enabled**
    - **Validates: Requirements 5.1**

  - [x]* 17.5 Write property test for long-term retrieval
    - **Property 14: Long-term retrieval respects threshold, ordering, and limit**
    - **Validates: Requirements 5.2, 5.3**

  - [x]* 17.6 Write property test for graceful degradation
    - **Property 15: Long-term memory degrades gracefully**
    - **Validates: Requirements 5.4, 5.5**

- [ ] 18. Deployment configuration
  - [x] 18.1 Add deployment configuration files for the free-tier topology
    - Backend service config (Render/Fly), Dockerfile, Neon connection env template, Vercel
      web config, and an external cron health-ping definition
    - _Requirements: 12.7_

  - [ ]* 18.2 Write backward-compatibility integration test
    - A previously published v1 request is still accepted after a schema change
    - _Requirements: 13.5_

- [ ] 19. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; they cover unit,
  property, integration, smoke, and client tests.
- Each property is implemented as a single Hypothesis-based test running a minimum of 100
  iterations, tagged `Feature: character-chat-ai, Property {n}` and placed close to the code
  it validates so errors are caught early.
- All 32 correctness properties are covered (Properties 1–32); example, integration, smoke,
  and client tests cover behaviors not suited to PBT (UI, provider calls, webhook wiring,
  one-time config, deployment wiring).
- Each task references the specific requirements it implements for traceability.
- Checkpoints provide phase boundaries so each phase is independently runnable and testable.
- Deployment tasks create configuration/code only; external service account signup is handled
  separately by the user.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "3.1"] },
    { "id": 2, "tasks": ["1.3", "1.4", "2.2", "5.1"] },
    { "id": 3, "tasks": ["2.3", "2.4", "3.2", "5.5"] },
    { "id": 4, "tasks": ["3.3", "3.4", "3.5", "3.6", "4.1", "4.2"] },
    { "id": 5, "tasks": ["3.7", "3.8", "4.3", "4.4", "4.5", "4.6", "4.7", "5.2", "6.1"] },
    { "id": 6, "tasks": ["4.8", "5.3", "5.4", "5.6", "6.2", "7.1"] },
    { "id": 7, "tasks": ["7.2", "7.3", "7.4", "8.1"] },
    { "id": 8, "tasks": ["8.2", "8.3", "8.4", "8.5", "8.6"] },
    { "id": 9, "tasks": ["8.7", "8.8", "8.9", "8.10", "8.11", "8.12"] },
    { "id": 10, "tasks": ["10.1"] },
    { "id": 11, "tasks": ["10.2", "10.3", "10.4", "10.5"] },
    { "id": 12, "tasks": ["10.6", "10.7", "10.8"] },
    { "id": 13, "tasks": ["12.1", "12.2"] },
    { "id": 14, "tasks": ["12.3", "12.4"] },
    { "id": 15, "tasks": ["12.5", "12.6", "12.7"] },
    { "id": 16, "tasks": ["14.1"] },
    { "id": 17, "tasks": ["14.2"] },
    { "id": 18, "tasks": ["14.3", "14.4"] },
    { "id": 19, "tasks": ["16.1", "16.3", "17.1"] },
    { "id": 20, "tasks": ["16.2", "16.4", "17.2"] },
    { "id": 21, "tasks": ["16.5", "16.6", "16.7", "16.8", "16.9", "17.3"] },
    { "id": 22, "tasks": ["17.4", "17.5", "17.6", "18.1"] },
    { "id": 23, "tasks": ["18.2"] }
  ]
}
```
