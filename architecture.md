# NewsBot Blogs - Architecture Document

## 1. Project Overview

**NewsBot Blogs** is a fully automated, AI-driven content generation engine designed to crawl, curate, write, and publish motorcycle-related news for the Indian market. The system operates as a set of sequential agents orchestrated by an asynchronous pipeline. It uses Google's Gemini API for finding recent news, extracting facts, validating claims, and writing SEO-optimized articles in a single combined step. It also features an automated image processing pipeline that searches for motorcycle images, removes backgrounds, and generates rich composite thumbnails in a non-blocking background queue.

---

## 2. Refactored Folder & File Structure

### Root Directory
* **`src/index.py`**: Application entrypoint. Loads `.env`, initializes the DB, starts the scheduler and the FastAPI approval server via `uvicorn`.
* **`run_once.py`**: Manual trigger script to initialize the DB and trigger a single pipeline run immediately (no web server).
* **`requirements.txt`**: Python dependencies (FastAPI, uvicorn, APScheduler, psycopg2, google-genai, httpx, etc).

### `/src/agents/`
* **`crawler_agent.py`**: Uses Gemini + the built-in `google_search` grounding tool to discover recent news items within a configured time window. Normalizes and deduplicates results.
* **`filter_agent.py`**: Analyzes raw items to calculate a relevance score to weed out irrelevant or sponsored content.
* **`grouping_agent.py`**: Clusters similar news items together using Jaccard Similarity and Union-Find.
* **`story_agent.py`**: Unified agent that makes a single structured Gemini call per cluster to: extract story facts/entities/quotes, validate facts across sources, and draft 2-3 SEO articles (JSON schema response).
* **`image_agent.py`**: Background task that uses Gemini `google_search` grounding to gather visual context, then generates the final hero image internally. SerpAPI is used only as a fallback search source, and placeholders are generated when search or generation cannot produce a usable result.
* **`publisher_agent.py`**: Writes approved drafts to `outputs/articles/` as Markdown + HTML, and optionally POSTs to a CMS webhook if configured.

### `/src/approval/`
* **`approval_server.py`**: FastAPI server providing approval links (`/approve/{article_id}`), edit requests, image retry, and serving published HTML (`/bikes/{slug}`).
* **`approval_service.py`**: Approval workflow (token generation/validation), email generation, approve/reject/edit handlers, and timeout archival.

### `/src/db/`
* **`database.py`**: PostgreSQL connection pool (psycopg2) and migration bootstrap.
* **`migrations/*.sql`**: SQL migrations applied on startup.
* **`queries/*.py`**: Query helpers for raw items, clusters, drafts, and job registry.

### `/src/config/`
* **`config.py`**: Centralized configuration reading from environment variables (`DATABASE_URL`, `GEMINI_API_KEY`, image search keys, etc).

### `/src/pipeline/`
* **`blog_pipeline.py`**: Orchestrates the core pipeline. Includes execution time tracking for observability.
* **`pipeline_runner.py`**: Trigger wrapper utilizing an `asyncio.Queue` to handle multiple pipeline requests concurrently without DB lock contention.

---

## 3. Model & Integration Map

### Gemini (google-genai)
* **Client**: `google.genai.Client(api_key=GEMINI_API_KEY)` from `src/utils/llm_service.py`.
* **Crawler**: Gemini call with `tools=[{"google_search": {}}]` to ground results in web sources and extract a JSON list of items.
* **Story agent**: One Gemini call per cluster using a strict JSON response schema (story extraction + fact validation + drafts in one response).

### Image Search (optional)
* **Gemini grounding**: Primary search path uses Gemini with the `google_search` tool to gather authoritative visual cues from the web.
* **SerpAPI**: Uses `SERPAPI_API_KEY` only when Gemini search does not return usable visual context.
* **Internal generation**: Search output is treated as reference context; final assets are generated internally rather than downloaded from third-party sources.
* **Fallback**: If neither search path yields usable context, `image_agent` generates a placeholder image so approvals can proceed.

---

## 4. Execution Flow & Concurrency

1. **Startup** (`src/index.py`): loads `.env`, initializes the DB (Postgres pool + SQL migrations), starts APScheduler jobs, and serves the approval API via FastAPI/uvicorn.
2. **Trigger** (`pipeline_runner.py`): scheduled jobs (every 6 hours + weekly) enqueue a run into an in-memory `asyncio.Queue`.
3. **Worker**: a single background worker drains the queue and runs the pipeline sequentially, avoiding overlapping pipeline runs in the same process.
4. **Crawl and filter** (`crawler_agent.py`, `filter_agent.py`): discover news via Gemini grounding and filter by relevance.
5. **Group** (`grouping_agent.py`): cluster related items.
6. **Story processing** (`story_agent.py`): for each cluster, one structured Gemini call produces story metadata + drafts. Drafts are stored in Postgres.
7. **Images (non-blocking)** (`image_agent.py`): dispatched via `asyncio.create_task()` so the main pipeline can proceed to email approvals.
8. **Approval emails** (`approval_service.py` + `utils/emailer.py`): send one email per selected draft with approve/reject/edit/retry-image links.
9. **Publish** (`publisher_agent.py`): on approval, writes Markdown + HTML locally and optionally calls the CMS webhook.

---

## 5. Identified Bottlenecks & Observability

### Current Bottlenecks
* **Image generation**: internal generation and validation still consume model latency; repeated retries can slow large batches.
* **External I/O**: grounded search and SerpAPI fallback remain network bound; slow search responses or rate limits can reduce throughput.
* **Single-process queue**: `asyncio.Queue` is in-memory; multiple replicas will not coordinate runs without an external broker/lock.
* **Database availability**: the service expects a reachable Postgres instance at startup (pool creation + migrations).

### Observability Additions
* **Agent tracing**: `src/utils/observability.py` tracks agent actions and can enforce daily email limits.
* **Performance tracing**: `blog_pipeline.py` captures phase timing (crawl/group, story processing, image dispatch, approvals).

---

## 6. Future Scalability Roadmap

1. **Distributed runs**: Move from in-process `asyncio.Queue` to Redis/RabbitMQ and add a distributed lock so multiple instances do not double-run the same schedule.
2. **Dedicated workers**: Offload image generation to a worker pool (Celery/RQ/Arq) to isolate the web server and scheduler.
3. **Better clustering**: Replace Jaccard-based clustering with embeddings + pgvector/Qdrant for semantic grouping.
4. **Artifact storage**: Store generated assets in object storage (S3/GCS) and persist public URLs in Postgres instead of local paths.

---

## 7. Environment Variables (Runtime)

### Required for a real pipeline run
* **`GEMINI_API_KEY`**: required; the service raises on startup if missing.
* **`DATABASE_URL`**: required; Postgres DSN used to create the connection pool and run migrations.

### Required for approval emails
* **`SMTP_HOST`**, **`SMTP_PORT`**, **`SMTP_USER`**, **`SMTP_PASS`**
* **`APPROVER_EMAILS`**
* **`BASE_URL`** (used to build approval and published-article links)

### Optional integrations
* **Image search**: `USE_GEMINI_IMAGE_SEARCH` and optional `SERPAPI_API_KEY`
* **CMS publish**: `CMS_WEBHOOK_URL` (+ optional `CMS_API_KEY` for `x-api-key` header)
