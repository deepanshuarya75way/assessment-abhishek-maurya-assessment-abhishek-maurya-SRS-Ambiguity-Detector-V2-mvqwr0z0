# SRS Ambiguity Detector

SRS Ambiguity Detector helps product, engineering, and QA teams find unclear or hard-to-verify wording in software requirements before it causes confusion during implementation. Paste in requirement text or upload a supported document, review the findings, and decide which changes make sense for your specification.

The core analysis is deterministic and works without an AI provider. If you choose, you can add an AI-generated overview and rewrite suggestions using your own provider key. Findings and suggestions are review aids; they do not replace a requirements review, and heuristic detectors can produce false positives or miss issues.

## What you can do

- Analyze pasted SRS text or upload one PDF, DOCX, or TXT document at a time. Uploads are limited to 10 MiB; extracted text follows the same 200,000-character analysis limit as pasted text.
- Split documents into requirements and flag wording patterns such as vague quantities, subjective terms, missing measurable criteria, unclear references, optional language, ambiguous operators, undefined terms, absolute claims, passive voice, missing constraints, and incomplete statements.
- Review the evidence phrase, category, severity, explanation, recommendation, score, category summaries, and requirement health indicators for each analysis.
- Save analyses to your account, browse history, and review aggregate activity in the dashboard.
- Optionally enable AI enhancement on an analysis for an overview and suggested rewrites. The AI option is off by default. Configure personal credentials for Google Gemini, Groq, OpenAI, Anthropic, OpenRouter, or Hugging Face in **Settings**. Provider keys are encrypted by the backend and are not required for regular analysis.
- Create an account and sign in, manage your profile and password, and use password reset if needed. **Email verification is not part of signup.** Password reset email delivery remains available through the local development outbox or Resend.
- Manage privacy settings, export account data, set history retention, delete uploaded documents, and delete your account.
- Store documents on local disk for development or use Supabase Storage for a managed deployment.

## How the project is organized

```text
.
├── backend/
│   ├── alembic/                 Database migration configuration and revisions
│   ├── app/
│   │   ├── ai/                  Provider registry, adapters, prompts, and output handling
│   │   ├── analysis/            Requirement segmentation, detectors, scoring, and rules
│   │   ├── api/v1/               HTTP endpoints and API router
│   │   ├── core/                Settings, security, database, logging, and monitoring
│   │   ├── documents/           File validation and text extraction
│   │   ├── email/               Console and Resend email adapters
│   │   ├── exceptions/          Shared application errors
│   │   ├── models/              SQLAlchemy database models
│   │   ├── repositories/        Database access
│   │   ├── schemas/             API request and response schemas
│   │   ├── services/            Authentication, analysis, AI, privacy, and settings logic
│   │   └── storage/             Local and Supabase document storage adapters
│   ├── tests/                   Backend tests
│   ├── .env.example             Backend configuration template
│   ├── alembic.ini
│   ├── requirements.txt         Runtime Python dependencies
│   └── requirements-dev.txt     Test and quality-check dependencies
├── frontend/
│   ├── src/app/                 Next.js pages and route layouts
│   ├── src/components/          Analyzer, reports, auth, dashboard, history, and settings UI
│   ├── src/hooks/               Shared React hooks
│   ├── src/lib/                 API clients, validation, error handling, and utilities
│   ├── src/types/               Shared TypeScript types
│   ├── public/                  Static assets
│   ├── .env.example             Browser-safe frontend configuration template
│   └── package.json             Frontend scripts and dependencies
├── scripts/
│   ├── verify.sh                Full repository quality gate (Bash)
│   └── secret-scan.sh           Secret scanning helper
├── docker-compose.yml           Local PostgreSQL service only
└── README.md
```

The frontend includes public pages, signup/login and password-reset screens, the analyzer, analysis reports, dashboard, history, and account settings. The API is grouped under `/api/v1` and provides health, auth, analysis, document, dashboard, AI-provider, settings, and privacy endpoints.

## Requirements

- Windows, macOS, or Linux.
- Python 3.11 or newer.
- Node.js 20 or newer and npm.
- Docker Desktop with Docker Compose, or a PostgreSQL 16-compatible database.

The Docker Compose file starts PostgreSQL only. The API and web app run as local processes in separate terminals.

## Run locally on Windows with PowerShell

Run these commands from the project root unless a step says otherwise. Keep the backend and frontend terminals open while using the site.

### 1. Start PostgreSQL

```powershell
docker compose up -d db
```

The local Compose defaults are database `srs_ambiguity`, user `srs`, password `changeme-local-only`, and port `5432`. These are development defaults only. If you have changed them, make the database URLs in `backend/.env` match.

### 2. Configure and start the backend

If the environment file does not exist yet, create it once from the template:

```powershell
Set-Location .\backend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Open `backend/.env` and confirm these settings are configured:

```dotenv
APP_ENV=local
BACKEND_CORS_ORIGINS=http://localhost:3000
DATABASE_URL=postgresql+asyncpg://srs:changeme-local-only@localhost:5432/srs_ambiguity
DIRECT_DATABASE_URL=postgresql+asyncpg://srs:changeme-local-only@localhost:5432/srs_ambiguity
JWT_SECRET=<generated-secret-at-least-32-bytes>
APP_BASE_URL=http://localhost:3000
EMAIL_PROVIDER=console
STORAGE_BACKEND=local
ENCRYPTION_MASTER_KEY=<generated-fernet-key>
```

`DATABASE_URL` and `DIRECT_DATABASE_URL` are commented in the example file, so uncomment them when using the local Compose database. Generate the two secrets from the backend directory after installing the Python dependencies:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put the first value in `JWT_SECRET` and the second in `ENCRYPTION_MASTER_KEY`. Keep `.env` private and out of version control. Back up the Fernet key securely; changing or losing it makes already-saved AI provider credentials unreadable.

Activate the existing virtual environment. Create it first only if it is missing:

```powershell
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\Activate.ps1
```

Install dependencies on first setup or after changing the dependency files:

```powershell
pip install -r requirements.txt -r requirements-dev.txt
```

Then run migrations and start the API:

```powershell
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Leave this terminal running. The API liveness endpoint is [http://localhost:8000/api/v1/health/live](http://localhost:8000/api/v1/health/live), and its interactive API docs are at [http://localhost:8000/api/docs](http://localhost:8000/api/docs) in local mode.

### 3. Configure and start the frontend

In a second terminal at the project root:

```powershell
Set-Location .\frontend
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
```

The local `.env.local` should contain:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_SITE_URL=http://localhost:3000
```

Install frontend dependencies on first setup (or after changing the lockfile), then start the development server:

```powershell
if (-not (Test-Path node_modules)) { npm ci }
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Never put API keys or other server secrets in `NEXT_PUBLIC_*` variables; Next.js exposes those values to the browser.

### If a port is unavailable

If Uvicorn reports a Windows socket error such as `[WinError 10013]` on port 8000, try another port, such as 8001:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Update `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to `http://localhost:8001/api/v1`, then restart the frontend dev server. If you change the frontend port, also update `BACKEND_CORS_ORIGINS` and `APP_BASE_URL` in `backend/.env` to the frontend origin, and set `NEXT_PUBLIC_SITE_URL` to that same origin. Restart both servers after changing environment files.

## Email in local development

`EMAIL_PROVIDER=console` avoids an external email service. Password-reset messages and their links are written to the backend development outbox, by default `backend/.dev-outbox/` when running from the backend directory. Keep the outbox private because it contains account links. Email verification links are not used by signup.

For real email delivery, configure `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, and `EMAIL_FROM` in the backend environment. Resend is optional for local development.

## AI provider setup

AI provider keys are managed per signed-in user in **Settings → AI providers**. They are encrypted at rest using `ENCRYPTION_MASTER_KEY`; the app does not read global provider keys from environment variables. Add a provider key and use its **Test connection** control. Provider accounts can have their own permissions, model access, billing, and usage limits.

AI enhancement is an explicit option on the text analyzer and document upload forms and is off by default. Turn it on for each run where you want an AI overview and rewrite suggestions. Regular analysis continues to work if no AI provider is configured or a provider call fails.

## File storage

Local development uses `STORAGE_BACKEND=local` and stores uploaded files under `STORAGE_LOCAL_DIR` (default `backend/uploads/` when started from the backend directory). Local storage is intended for development or a single persistent host.

For Supabase Storage, set `STORAGE_BACKEND=supabase` and configure `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_STORAGE_BUCKET` in the backend environment. Use a private bucket and keep the service-role key backend-only.

## Tests and quality checks

Backend checks (run from `backend/`):

```powershell
python -m pytest -q
ruff check app tests alembic
mypy app
```

Frontend checks (run from `frontend/`):

```powershell
npm run lint
npm run typecheck
npm test
npm run build
```

The complete repository verification script is `scripts/verify.sh`. It runs in Bash environments such as Git Bash or WSL and includes backend and frontend quality checks, secret scanning, and dependency auditing. Some backend integration tests require a reachable test PostgreSQL database; they do not use the local development database unless configured to do so.

## Production notes

The frontend and API are separate services. Deploy the Next.js app and FastAPI service independently, and use a managed PostgreSQL database plus private persistent document storage. Set `APP_ENV=production`, use strong secrets from a secret manager, configure exact CORS origins and HTTPS, and set Resend and storage settings as needed. Keep `.env` files out of source control and do not expose backend secrets in frontend configuration.

Run `alembic upgrade head` as a release step before starting the API. Use the API readiness endpoint `/api/v1/health/ready` for dependency checks. The rate limiter is process-local, so account for that when deciding how many API workers or instances to run. Back up the database, uploaded files, and `ENCRYPTION_MASTER_KEY` independently.

## Known limitations

- Ambiguity detection is heuristic and English-first; review the findings against the original requirement.
- Image-only/scanned PDFs are not OCR processed.
- AI enhancement depends on the provider key, its model access, and provider availability; it can fail independently of deterministic analysis.
- The current app is designed around individual accounts, not shared team workspaces.
- PDF/DOCX report export is not included.

## Maintainer and license

Maintained by Abhishek Maurya. No license is currently included, so reuse and redistribution rights have not been specified.
