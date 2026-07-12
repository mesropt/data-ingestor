# External Integrations

**Analysis Date:** 2026-07-09

## APIs & External Services

**Anthropic Claude API:**
- Service: Claude API for AI-powered column mapping
- What it's used for: Structured output mapping of messy CRO assay file columns to target fields
  - SDK/Client: `anthropic` package (0.69+)
  - Auth: `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` environment variable
  - Model: `claude-opus-4-8`
  - Features: Structured output via `.messages.parse()`, Pydantic schema, adaptive thinking mode
  - Implementation: `src/assayingest/mapping/mapper.py::propose_mapping()`

## Data Storage

**Databases:**
- Not currently implemented (Day 1)
- Planned: SQLite lab_profile store (Day 2) to cache and reuse mappings per lab signature

**File Storage:**
- Local filesystem only
- Accepted formats: CSV (`.csv`), Excel (`.xlsx`, `.xls`)
- Sample data: `data/synthetic/` contains 10+ realistic test files

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- Anthropic API key (SDK-native resolution from env)
- Implementation: `src/assayingest/cli.py::_has_credentials()` checks for presence; `src/assayingest/cli.py::_map_one()` catches `anthropic.AuthenticationError`

## Monitoring & Observability

**Error Tracking:**
- None (CLI-only, no external error tracking)

**Logs:**
- stdout/stderr via print statements
- Structured output (JSON draft) sent to stdout
- Human-readable review summary sent to stdout

## CI/CD & Deployment

**Hosting:**
- None (standalone CLI; no server)
- Planned: FastAPI backend server (Day 3) for web UI

**CI Pipeline:**
- None detected (local development only)

## Environment Configuration

**Required env vars:**
- `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` - Anthropic SDK credential

**Secrets location:**
- `.env` file (not committed; template: `.env.example`)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

---

*Integration audit: 2026-07-09*
