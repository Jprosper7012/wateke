# The Hive — Vercel Realtime Chat

A small room chat deployed on Vercel. Vercel serves the web app and FastAPI configuration endpoint; Supabase provides Postgres message history and Realtime presence, typing broadcasts, and new-message events. Vercel Functions do not host this app's WebSocket server, so the browser connects to Supabase Realtime directly.

## Set up Supabase

1. Create a Supabase project.
2. In **SQL Editor**, run [`supabase/schema.sql`](supabase/schema.sql). It creates the `general`, `football`, and `music` rooms, message history, access policies, and the Realtime publication.
3. In **Project Settings → API**, copy the project URL and publishable key (`sb_publishable_...`). The older anon key also works.
4. In **Realtime settings**, make sure public channel access is enabled. The MVP intentionally uses public rooms with no account sign-in.

The database policies allow anyone with the public app key to read and post messages. Database constraints enforce valid room names, non-empty usernames (up to 20 characters), and messages (up to 500 characters). Add authentication and narrower policies before using this for private conversations.

## Deploy on Vercel

1. Import this Git repository into Vercel with the project root set to the repository root.
2. Add these Environment Variables for Production and Preview:

   | Name | Value |
   | --- | --- |
   | `SUPABASE_URL` | Your Supabase project URL |
   | `SUPABASE_PUBLISHABLE_KEY` | The Supabase publishable key (or set `SUPABASE_ANON_KEY`) |

3. Deploy or redeploy. Vercel detects the FastAPI app exported from root [`index.py`](index.py); the browser assets are in `public/`.

The publishable key is designed to be exposed in browser apps. Never put a Supabase secret or service-role key in either variable.

## Run locally

Requires Python 3.10 or newer and a Supabase project configured with the SQL above.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set the two Supabase values in `.env`, then run:

```bash
set -a
source .env
set +a
uvicorn index:app --reload
```

Open http://localhost:8000. `vercel dev` can also run the project with the Vercel CLI after linking the repository and configuring local environment variables.

## Components and flow

- **Web app:** plain HTML, CSS, and JavaScript under `public/`, served by Vercel.
- **Vercel function:** FastAPI in `app/main.py` returns the UI and only the public Supabase configuration.
- **Persistence:** Supabase Postgres stores messages; joining a room loads the newest 50.
- **Presence and typing:** Supabase Realtime Presence and Broadcast channels keep transient state live across Vercel function instances.
- **Live messages:** clients subscribe to Postgres inserts filtered by room.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Chat UI |
| GET | `/api/config` | Public Supabase URL and publishable key |
| GET | `/api/health` | Function and Supabase configuration status |

## Tests

```bash
pytest -v
```

The tests cover the Vercel FastAPI entrypoint, UI response, missing Supabase configuration, and ensuring secret keys are never returned by the public config endpoint.

## Demo script

1. Open the deployment in two browser windows and join `general` as Ada and Lin.
2. Show both names in the online list and type in one window to show the typing indicator in the other.
3. Send a message and show it appear immediately in both windows.
4. Refresh or rejoin to show the message history is saved.
5. Explain that Vercel handles the UI/API while Supabase handles persistent data and realtime events.

## MVP limits

There is no sign-in, so anyone can post to public rooms. Usernames are checked against current room presence but are not reserved atomically. Add authentication, authorization, and rate limits before treating the service as private or production-critical.
