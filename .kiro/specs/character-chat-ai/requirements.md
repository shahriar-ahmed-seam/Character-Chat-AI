# Requirements Document

## Introduction

Character Chat AI is an end-to-end deployable product that lets users hold conversations with multiple AI characters, each with a distinct personality. The product is reachable through three thin clients: a web Progressive Web App (PWA), an Android application, and a Telegram bot. All business logic — persona injection, memory management, model routing, and chat history — lives in a single shared FastAPI backend so that every client behaves identically and logic is never duplicated.

The backend is stateless; all conversation state is persisted in PostgreSQL. Language model access is abstracted behind a single OpenAI-compatible client so the underlying provider (Ollama for local development; Groq, OpenRouter, or Hugging Face Dedicated Endpoints for production) can be swapped through environment configuration alone, without code changes. The system is designed to run on $0 free-tier infrastructure (Render/Fly for the backend, Neon for Postgres, Vercel for the web client, Groq/OpenRouter for inference) while remaining reliable, stable, and low-maintenance.

This document defines the requirements for the full product. Implementation is intended to proceed in phases: Phase 1 (backend + local model), Phase 2 (web PWA), Phase 3 (Telegram bot), Phase 4 (Android wrap), and Phase 5 (production hardening + optional long-term memory).

## Glossary

- **System**: The complete Character Chat AI product, including the backend and all clients.
- **Backend_API**: The shared FastAPI service that holds all business logic and exposes HTTP endpoints to clients.
- **Client**: Any of the three thin front-ends (Web_PWA, Android_App, Telegram_Bot) that call the Backend_API.
- **Web_PWA**: The React-based Progressive Web App client.
- **Android_App**: The Android application produced by wrapping the React codebase using Capacitor (or an equivalent native wrapper).
- **Telegram_Bot**: The Telegram client implemented with aiogram in webhook mode.
- **Persona**: A defined AI character with a validated schema consisting of id, name, archetype, system_directive, example_dialogue, and speech_patterns.
- **Persona_Schema**: The strict validation schema that every Persona definition must satisfy.
- **Persona_Manager**: The Backend_API component responsible for loading, validating, and serving Personas.
- **Conversation**: An ordered sequence of Messages exchanged between a user and a single Persona within a Session.
- **Message**: A single chat entry with a role (user or assistant), text content, persona association, and timestamp.
- **Session**: A persisted context that associates a user (or a Telegram chat_id) with a Conversation and its history.
- **Chat_Service**: The Backend_API component that orchestrates a chat turn: assembling persona directives, memory, and history, then calling the LLM_Client.
- **Memory_Manager**: The Backend_API component that manages short-term and optional long-term memory.
- **Short_Term_Memory**: A sliding window of the most recent N Messages included in each model request.
- **Long_Term_Memory**: An optional retrieval-augmented memory using pgvector and nomic-embed-text embeddings.
- **LLM_Client**: The single provider-abstraction component that communicates with language model providers through an OpenAI-compatible interface.
- **Provider**: A configured language model backend (for example Ollama, Groq, OpenRouter, or Hugging Face Dedicated Endpoints).
- **Datastore**: The PostgreSQL database where Sessions, Conversations, Messages, and embeddings are persisted.
- **Health_Endpoint**: The Backend_API endpoint used to report service liveness and to mitigate free-tier cold starts.
- **API_Credential**: A token or key required by a Client to authenticate requests to the Backend_API.
- **N**: The configurable number of most recent Messages retained in Short_Term_Memory.

## Requirements

### Requirement 1: Persona Definition and Validation

**User Story:** As a product maintainer, I want characters defined through a strict validated schema, so that personas load reliably and malformed definitions are rejected before reaching users.

#### Acceptance Criteria

1. THE Persona_Schema SHALL require the fields id, name, archetype, system_directive, example_dialogue, and speech_patterns to be present and non-empty for every Persona.
2. THE Persona_Schema SHALL constrain the id field to a unique string of 1 to 64 characters, each of name and archetype to a string of 1 to 200 characters, and system_directive to a string of 1 to 8000 characters.
3. WHEN a Persona definition is loaded, THE Persona_Manager SHALL validate the definition against the Persona_Schema before making the Persona available for chat requests.
4. IF a Persona definition fails Persona_Schema validation, THEN THE Persona_Manager SHALL reject only that definition, retain all previously validated definitions, and report a validation error identifying each missing or invalid field.
5. IF two or more Persona definitions share the same id, THEN THE Persona_Manager SHALL reject all definitions sharing that id and report an error identifying the conflicting id.
6. WHEN the Backend_API starts, THE Persona_Manager SHALL load and validate all configured Persona definitions before the Backend_API serves any chat request.
7. IF one or more configured Persona definitions fail validation during Backend_API startup, THEN THE Persona_Manager SHALL prevent the Backend_API from serving chat requests and report an error identifying each failing definition.

### Requirement 2: Persona Listing and Selection

**User Story:** As a user, I want to see and choose among the available characters, so that I can start a conversation with the personality I want.

#### Acceptance Criteria

1. WHEN a Client requests the list of available Personas, THE Backend_API SHALL return, within 2 seconds, a list containing each valid Persona's id, name, and archetype.
2. WHEN a Client requests the list of available Personas, THE Backend_API SHALL exclude the system_directive field from every Persona entry in the response.
3. IF a Client requests the list of available Personas and no valid Personas exist, THEN THE Backend_API SHALL return an empty list rather than an error response.
4. WHEN a user selects an existing Persona by id to begin a Conversation, THE Backend_API SHALL associate the selected Persona with the Session and confirm the association in the response.
5. IF a user selects a Persona by an id that does not exist, THEN THE Backend_API SHALL return an error response identifying the unknown Persona id and SHALL leave any existing Session Persona association unchanged.
6. IF a Client requests a chat turn with a Persona id that does not exist, THEN THE Backend_API SHALL return an error response identifying the unknown Persona id and SHALL NOT create or modify a Session.

### Requirement 3: Chat Conversation Flow

**User Story:** As a user, I want to send messages to a character and receive in-character replies, so that I can hold a coherent conversation.

#### Acceptance Criteria

1. WHEN a user submits a valid Message to a selected Persona, THE Chat_Service SHALL assemble a model request that includes the Persona's system_directive, the most recent Short_Term_Memory Messages for the Session up to a maximum of 20 Messages, and the new Message.
2. WHEN the Chat_Service assembles a model request, THE Chat_Service SHALL include the selected Persona's system_directive, example_dialogue, and speech_patterns in the model request.
3. WHEN the LLM_Client returns a generated reply, THE Chat_Service SHALL persist both the user Message and the assistant Message to the Datastore associated with the Session.
4. WHEN the LLM_Client returns a generated reply, THE Backend_API SHALL return the assistant Message to the requesting Client.
5. IF a submitted Message is empty or exceeds 4000 characters, THEN THE Chat_Service SHALL reject the Message, SHALL return an error response indicating the validation failure to the Client, and SHALL NOT persist the Message or invoke the LLM_Client.
6. IF the LLM_Client does not return a reply within 30 seconds, THEN THE Chat_Service SHALL treat the request as a failed generation.
7. IF the LLM_Client fails to return a reply, returns an error, or exceeds the 30 second timeout, THEN THE Chat_Service SHALL persist the user Message to the Datastore, SHALL NOT persist an assistant Message, and SHALL return an error response indicating the generation failure to the Client.

### Requirement 4: Short-Term Memory

**User Story:** As a user, I want the character to remember the recent course of our conversation, so that replies stay relevant to what was just discussed.

#### Acceptance Criteria

1. THE Memory_Manager SHALL maintain Short_Term_Memory as the most recent N Messages of the Session, where N is an integer configurable through environment configuration within the range 1 to 100 inclusive.
2. WHEN the Chat_Service assembles a model request, THE Memory_Manager SHALL provide the Short_Term_Memory ordered from oldest to newest Message.
3. WHILE a Session contains more than N Messages, THE Memory_Manager SHALL include only the most recent N Messages in Short_Term_Memory.
4. WHILE a Session contains N or fewer Messages, THE Memory_Manager SHALL include all Messages of the Session in Short_Term_Memory ordered from oldest to newest Message.
5. WHEN N is not set in environment configuration, THE Memory_Manager SHALL apply a default value of 20 for N.
6. IF N is set in environment configuration to a non-integer value or to a value outside the range 1 to 100 inclusive, THEN THE Memory_Manager SHALL reject the configured value, apply the default value of 20 for N, and record an error indication that the configured value was invalid.

### Requirement 5: Optional Long-Term Memory

**User Story:** As a user, I want the character to recall relevant facts from earlier in our history, so that long-running conversations feel continuous.

#### Acceptance Criteria

1. WHERE Long_Term_Memory is enabled through configuration, WHEN a Message is persisted to the Datastore, THE Memory_Manager SHALL generate an embedding for that Message using the nomic-embed-text embedding model and store the embedding in the Datastore using pgvector.
2. WHERE Long_Term_Memory is enabled, WHEN the Chat_Service assembles a model request, THE Memory_Manager SHALL retrieve up to 10 stored Messages whose vector similarity to the new Message is at least 0.75 on a 0.0 to 1.0 scale, ordered from most similar to least similar, and include them in the model request.
3. WHERE Long_Term_Memory is enabled, IF no stored Message meets the 0.75 similarity threshold, THEN THE Memory_Manager SHALL assemble the model request using only Short_Term_Memory.
4. WHERE Long_Term_Memory is disabled through configuration, THE Memory_Manager SHALL assemble model requests using only Short_Term_Memory.
5. WHERE Long_Term_Memory is enabled, IF embedding generation fails for a Message, THEN THE Memory_Manager SHALL continue the chat turn using Short_Term_Memory, retain the Message in the Datastore, and record a failure entry identifying the affected Message.

### Requirement 6: Session and History Persistence

**User Story:** As a user, I want my conversations saved, so that I can leave and return without losing history.

#### Acceptance Criteria

1. WHEN a user begins a new Conversation, THE Backend_API SHALL create a Session with a unique Session identifier and persist it in the Datastore.
2. WHEN a Message is exchanged in a Session, THE Backend_API SHALL persist the Message in the Datastore with its role, content, associated Persona id, and timestamp.
3. IF the Backend_API fails to persist a Session or a Message to the Datastore, THEN THE Backend_API SHALL return an error response indicating the persistence failure and SHALL preserve any previously persisted Session and Message state without partial writes.
4. WHEN a Client requests the history of an existing Session, THE Backend_API SHALL return the Session's Messages ordered from oldest to newest by timestamp, with ties broken by ascending order of insertion.
5. IF a Client requests the history of a Session identifier that does not exist in the Datastore, THEN THE Backend_API SHALL return an error response indicating the Session was not found and SHALL NOT create a new Session.
6. THE Backend_API SHALL store all Conversation state in the Datastore rather than in process memory.
7. WHEN the Backend_API restarts, THE Backend_API SHALL serve all previously persisted Sessions and Messages with their role, content, associated Persona id, and timestamp unchanged and with no Messages omitted.

### Requirement 7: Model Provider Abstraction and Swapping

**User Story:** As a product maintainer, I want a single model client that works across providers, so that I can switch between local and production inference without changing code.

#### Acceptance Criteria

1. THE LLM_Client SHALL communicate with every Provider through a single OpenAI-compatible interface.
2. THE LLM_Client SHALL select the active Provider, base URL, model name, and API_Credential from environment configuration at startup.
3. WHEN the active Provider is changed through environment configuration and the Backend_API is restarted, THE System SHALL route subsequent inference requests to the new Provider with no modification to application source code.
4. WHERE the environment configuration selects Ollama, THE LLM_Client SHALL route chat completion requests to the local Ollama service and embedding requests to the nomic-embed-text model.
5. IF a required Provider configuration value (active Provider, base URL, model name, or API_Credential) is missing or empty at startup, THEN THE Backend_API SHALL terminate startup, SHALL NOT begin serving requests, and SHALL report the name of each missing configuration value.
6. IF the active Provider does not return a response to a chat completion or embedding request within 30 seconds, THEN THE LLM_Client SHALL abort the request and return an error indicating that the Provider is unreachable, and THE Backend_API SHALL remain running.
7. IF the active Provider rejects a request because the supplied API_Credential is invalid or unauthorized, THEN THE LLM_Client SHALL return an error indicating authentication failure without retrying the request.

### Requirement 8: Web PWA Client

**User Story:** As a web user, I want a browser-based app with a character picker and chat view, so that I can chat with characters from any device.

#### Acceptance Criteria

1. WHEN the Web_PWA loads the character picker, THE Web_PWA SHALL request the available Personas from the Backend_API and SHALL display each returned Persona as a selectable item.
2. IF the Backend_API returns an empty set of Personas, THEN THE Web_PWA SHALL display an indication that no characters are available.
3. WHEN a user selects a Persona in the Web_PWA, THE Web_PWA SHALL display a chat view for a Conversation with the selected Persona.
4. WHEN a user sends a Message in the Web_PWA, THE Web_PWA SHALL submit the Message to the Backend_API.
5. WHEN the Backend_API returns an assistant Message within 30 seconds of submission, THE Web_PWA SHALL display the returned assistant Message in the chat view.
6. IF the Backend_API returns an error or does not respond within 30 seconds when retrieving Personas or submitting a Message, THEN THE Web_PWA SHALL display an error indication describing the failure and SHALL retain the user's unsent Message text.
7. THE Web_PWA SHALL satisfy Progressive Web App installability requirements by providing a web app manifest and a service worker.
8. THE Web_PWA SHALL obtain all chat and persona data from the Backend_API and SHALL contain no persona injection, memory, or model routing logic.

### Requirement 9: Android Client

**User Story:** As a mobile user, I want an installable Android app, so that I can chat with characters natively on my phone.

#### Acceptance Criteria

1. THE Android_App SHALL be produced by wrapping the shared React codebase used by the Web_PWA.
2. THE Android_App SHALL provide the same character picker and chat functionality as the Web_PWA, including Persona selection and Message exchange.
3. WHEN a user sends a Message in the Android_App, THE Android_App SHALL submit the Message to the Backend_API.
4. WHEN the Backend_API returns an assistant Message, THE Android_App SHALL display the returned assistant Message.
5. IF the Backend_API returns an error or does not respond within 30 seconds of Message submission, THEN THE Android_App SHALL display an error indication that the Message could not be delivered and SHALL retain the user's submitted Message for resend.
6. WHEN a user installs the Android_App on their device, THE Android_App SHALL launch as a standalone native application without requiring a separate web browser.
7. THE Android_App SHALL obtain all chat and Persona data from the Backend_API and SHALL contain no persona injection, memory, or model routing logic.

### Requirement 10: Telegram Bot Client

**User Story:** As a Telegram user, I want to chat with characters inside Telegram, so that I can use the product without installing a separate app.

#### Acceptance Criteria

1. THE Telegram_Bot SHALL operate in webhook mode using aiogram.
2. WHEN the Telegram_Bot receives a message from a Telegram chat_id that already maps to a Session, THE Telegram_Bot SHALL use the mapped Session for the message.
3. IF the Telegram_Bot receives a message from a Telegram chat_id that does not map to an existing Session, THEN THE Telegram_Bot SHALL request the Backend_API to create a Session and map the chat_id to it.
4. WHEN the Telegram_Bot receives a user message, THE Telegram_Bot SHALL submit the message to the Backend_API.
5. WHEN the Backend_API returns an assistant Message, THE Telegram_Bot SHALL send the assistant Message as a reply to the originating Telegram chat_id.
6. IF the Backend_API returns an error or does not respond within 30 seconds, THEN THE Telegram_Bot SHALL notify the user that the message could not be processed and SHALL leave the Session state unchanged.
7. WHEN a Telegram user requests the available characters, THE Telegram_Bot SHALL present the Personas returned by the Backend_API.
8. WHEN a Telegram user selects a presented Persona, THE Telegram_Bot SHALL associate the selected Persona with the user's Session.
9. IF a Telegram user selects a Persona that is not in the presented list, THEN THE Telegram_Bot SHALL reject the selection and notify the user that the selection is invalid.
10. THE Telegram_Bot SHALL obtain all chat and Persona data from the Backend_API.
11. THE Telegram_Bot SHALL contain no persona injection, memory, or model routing logic.

### Requirement 11: Endpoint Security and Rate Limiting

**User Story:** As a product maintainer, I want the backend protected against unauthorized and excessive use, so that the service stays available and within free-tier limits.

#### Acceptance Criteria

1. WHEN a Client calls a chat or session endpoint, THE Backend_API SHALL require a valid API_Credential before processing the request.
2. IF a request to a protected endpoint omits a valid API_Credential, THEN THE Backend_API SHALL reject the request without processing it and return an unauthorized error response indicating that a valid API_Credential is required.
3. WHEN the count of requests received from a single API_Credential exceeds the configured rate-limit threshold within the configured time window, THE Backend_API SHALL reject each further request from that API_Credential with a rate-limit error response that indicates the time remaining until the time window resets.
4. WHEN the configured time window for an API_Credential elapses, THE Backend_API SHALL reset that API_Credential's request count to zero and resume accepting requests from it.
5. THE Backend_API SHALL load API_Credential values, the rate-limit threshold (expressed as maximum requests), and the rate-limit time window (expressed in seconds) from environment configuration.
6. IF any required API_Credential value, rate-limit threshold, or rate-limit time window is absent or invalid in environment configuration at startup, THEN THE Backend_API SHALL refuse to serve protected endpoints and report a configuration error indicating the missing or invalid setting.
7. WHEN the Backend_API returns an error response, THE Backend_API SHALL exclude API_Credential values and Provider secrets from the response body.

### Requirement 12: Deployment and Reliability on Free Tiers

**User Story:** As a product maintainer, I want the system to run reliably on $0 free-tier infrastructure, so that I can operate it at no cost without constant maintenance.

#### Acceptance Criteria

1. THE Backend_API SHALL expose a Health_Endpoint that reports service liveness, where liveness includes the reachability of the Datastore and the availability of the configured Provider.
2. WHEN the Health_Endpoint receives a request and all checked dependencies (Datastore and Provider) are reachable, THE Backend_API SHALL respond within 2 seconds with a success status indicating the service is available.
3. IF the Health_Endpoint receives a request and any checked dependency (Datastore or Provider) is unreachable, THEN THE Backend_API SHALL respond within 2 seconds with an error status indicating which dependency is unavailable.
4. THE Backend_API SHALL read all environment-specific settings, including Datastore connection, Provider configuration, and API_Credential values, from environment configuration at startup.
5. IF a required environment configuration value (Datastore connection, Provider configuration, or API_Credential) is missing or empty at startup, THEN THE Backend_API SHALL report a configuration error identifying the missing value and SHALL return an error status from the Health_Endpoint.
6. IF the Backend_API cannot connect to the Datastore at startup after 3 connection attempts within a 30-second window, THEN THE Backend_API SHALL report the connection failure and SHALL return an error status from the Health_Endpoint.
7. WHEN the Backend_API resumes from a free-tier cold start, THE Backend_API SHALL serve requests within 60 seconds using Session and Message state persisted in the Datastore, with no loss of previously persisted Session or Message data.

### Requirement 13: Stable Client-Backend API Contract

**User Story:** As a product maintainer, I want a stable, validated API contract between clients and the backend, so that clients keep working and data stays consistent.

#### Acceptance Criteria

1. THE Backend_API SHALL validate the structure, required fields, and data types of every incoming Client request against a defined request schema before performing any processing on the request.
2. IF an incoming Client request fails request-schema validation, THEN THE Backend_API SHALL reject the request without creating or modifying any Session or Persona data and return a validation error that identifies each field that failed validation and the reason each field was rejected.
3. THE Backend_API SHALL return chat, Persona, and Session responses using a single response structure that is identical across all Clients for the same response type.
4. WHEN the Backend_API returns an error, THE Backend_API SHALL return a consistent error structure that includes a machine-readable error identifier and a human-readable error description.
5. WHERE the request schema or response structure is changed, THE Backend_API SHALL continue to accept Client requests and return responses that conform to all previously published schema versions.
