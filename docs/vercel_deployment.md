# FluentFlow Vercel deployment notes

FluentFlow should be deployed to Vercel as a static frontend only.

The local FastAPI backend is intentionally not deployed as a Vercel Function because the core workflow depends on local capabilities:

- FFmpeg on the host PATH.
- faster-whisper model loading and local CPU/GPU performance.
- large audio/video uploads.
- cancellable long-running STT subprocesses.
- SQLite and local files under `data/`.
- optional local `lark-cli`.

These do not map cleanly to Vercel Functions. A Vercel deployment is useful for a hosted UI shell or demo, while the real processing backend should stay local or move to a long-running server with FFmpeg and persistent storage.

## What the current Vercel config does

`vercel.json` deploys a clean static bundle under `dist/`:

- install: `npm ci`
- build: `npm run build:frontend && node scripts/build_vercel_static.js`
- output: `dist`
- SPA fallback: editor/settings routes return `dist/index.html`

`.vercelignore` excludes local-only and heavy files such as:

- `venv/`
- `data/`
- `logs/`
- `reports/`
- `backend/`
- `tests/`
- `requirements*.txt`

## Configure the API backend

Set this Vercel environment variable when deploying the frontend:

```bash
FLUENTFLOW_API_BASE=https://your-backend.example.com
```

The build writes it into:

```txt
frontend/assets/config.js
```

At runtime the frontend resolves API base in this order:

1. `window.FLUENTFLOW_CONFIG.apiBase`
2. `localStorage.fluentflow_api_base`
3. local dev fallback: `http://127.0.0.1:8000` when running on `localhost:5185`
4. same-origin fallback

For quick manual testing, open the browser console on the Vercel site and run:

```js
localStorage.setItem("fluentflow_api_base", "https://your-backend.example.com");
location.reload();
```

## Not supported on Vercel Functions

Do not expect these features to work from a Vercel-hosted backend:

- uploading full audio/video files for STT
- local faster-whisper transcription
- FFmpeg extraction
- local SQLite history/event persistence
- local edited transcript backups
- local `lark-cli` export
- long-running cancellable STT jobs

For those features, run the FastAPI backend locally or deploy it to a long-running host/container that supports:

- persistent disk
- FFmpeg installation
- larger request bodies
- long request duration or background workers
- model cache persistence

## Deployment commands

After installing Vercel CLI and logging in:

```bash
vercel
vercel --prod
```

To set the API base:

```bash
vercel env add FLUENTFLOW_API_BASE production
```

Then redeploy.
