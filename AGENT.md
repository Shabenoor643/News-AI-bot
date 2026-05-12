# AGENT.md — NewsBot Blogs for Vehicles
## Codex/AI Agent Build Specification

> **Project Name:** `newsbot-blogs`
> **Stack:** Node.js (ESM), Gemini API (`@google/genai`), SQLite (local), Express.js
> **AI Engine:** Google Gemini 2.0 Flash (`gemini-2.0-flash`) for all generation tasks
> **Goal:** Fully automated motorcycle blog pipeline — crawl → filter → generate → approve → publish

---

## 0. AGENT GROUND RULES

When building this project, the agent must:

1. Create **every file listed** in Section 2 (File Map). No file is optional.
2. Never invent API methods. All Gemini calls use `@google/genai` SDK exactly as documented below.
3. Every function must have JSDoc comments with `@param` and `@returns`.
4. Every file must have a top-level comment block: `// FILE: <path> | PURPOSE: <one line>`
5. All environment variables are read from `.env` via `dotenv`. Never hardcode keys.
6. SQLite DB file lives at `./data/newsbot.db`. Create the `data/` directory if it does not exist.
7. All logs use the shared logger at `src/utils/logger.js`. Never use `console.log` directly.
8. Errors are caught at the caller level and passed to `src/utils/errorHandler.js`.
9. All Gemini responses that should be JSON must be parsed through `src/utils/parseGeminiJSON.js`.
10. Run `npm install` before any code execution.

---

## 1. GEMINI API REFERENCE (use exactly this)

### SDK Install
```bash
npm install @google/genai
```

### Client Initialization
```js
// Always initialize this way — read key from process.env
import { GoogleGenAI } from "@google/genai";
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
```

### Text Generation (standard)
```js
const response = await ai.models.generateContent({
  model: "gemini-2.0-flash",
  contents: "Your prompt here",
});
const text = response.text;
```

### Text Generation with System Instruction
```js
const response = await ai.models.generateContent({
  model: "gemini-2.0-flash",
  contents: userPrompt,
  config: {
    systemInstruction: "You are a motorcycle journalist writing for Indian riders...",
    temperature: 0.7,
    maxOutputTokens: 2048,
  },
});
```

### Structured JSON Output
```js
const response = await ai.models.generateContent({
  model: "gemini-2.0-flash",
  contents: prompt,
  config: {
    responseMimeType: "application/json",
    responseSchema: {
      type: "object",
      properties: {
        title: { type: "string" },
        body: { type: "string" },
        tags: { type: "array", items: { type: "string" } },
      },
      required: ["title", "body", "tags"],
    },
  },
});
const parsed = JSON.parse(response.text);
```

### Google Search Grounding (for news crawling)
```js
const response = await ai.models.generateContent({
  model: "gemini-2.0-flash",
  contents: "Latest motorcycle launches in India this week",
  config: {
    tools: [{ googleSearch: {} }],
  },
});
// response.candidates[0].groundingMetadata has sources
```

### URL Context (for extracting page content)
```js
const response = await ai.models.generateContent({
  model: "gemini-2.0-flash",
  contents: [
    {
      role: "user",
      parts: [
        { text: "Extract all motorcycle specifications from this page as JSON" },
        { fileData: { mimeType: "text/html", fileUri: pageUrl } },
      ],
    },
  ],
});
```

### Image Generation (Imagen 3)
```js
const response = await ai.models.generateImages({
  model: "imagen-3.0-generate-002",
  prompt: imagePromptText,
  config: {
    numberOfImages: 1,
    aspectRatio: "16:9",
    outputMimeType: "image/jpeg",
  },
});
const imageBase64 = response.generatedImages[0].image.imageBytes;
// imageBytes is a base64 string — write to disk as Buffer.from(imageBase64, 'base64')
```

### Rate Limiting Note
- `gemini-2.0-flash`: 15 RPM free tier, 1000 RPM paid
- `imagen-3.0-generate-002`: 10 RPM
- Always add `await sleep(2000)` between consecutive Gemini calls in loops

---

## 2. FILE MAP (agent must create every one of these)

```
newsbot-blogs/
├── AGENT.md                          ← this file (already exists)
├── package.json
├── .env.example
├── .gitignore
├── README.md
│
├── src/
│   ├── index.js                      ← main entry point, wires everything
│   │
│   ├── config/
│   │   └── config.js                 ← all config constants (schedules, thresholds, etc.)
│   │
│   ├── agents/
│   │   ├── crawlerAgent.js           ← Stage 2: data collection via Gemini Search grounding
│   │   ├── filterAgent.js            ← Stage 3: relevance scoring
│   │   ├── groupingAgent.js          ← Stage 4: cluster similar stories
│   │   ├── factAgent.js              ← Stage 5: structured fact extraction
│   │   ├── validationAgent.js        ← Stage 6: cross-source validation
│   │   ├── contentAgent.js           ← Stage 7: article generation
│   │   ├── imageAgent.js             ← Stage 8: image generation/selection
│   │   └── publisherAgent.js         ← Stage 10: final publish to CMS/DB
│   │
│   ├── pipeline/
│   │   ├── blogPipeline.js           ← orchestrates all agents in sequence
│   │   └── pipelineRunner.js         ← cron trigger + run management
│   │
│   ├── approval/
│   │   ├── approvalService.js        ← sends approval email, tracks state
│   │   └── approvalServer.js         ← Express server for approve/reject webhooks
│   │
│   ├── db/
│   │   ├── database.js               ← SQLite connection + init
│   │   ├── migrations/
│   │   │   └── 001_initial_schema.sql
│   │   ├── models/
│   │   │   ├── RawItem.js
│   │   │   ├── StoryCluster.js
│   │   │   ├── DraftArticle.js
│   │   │   └── JobRegistry.js
│   │   └── queries/
│   │       ├── rawItems.js
│   │       ├── storyClusters.js
│   │       ├── draftArticles.js
│   │       └── jobRegistry.js
│   │
│   └── utils/
│       ├── logger.js                 ← structured logger (Winston)
│       ├── errorHandler.js           ← centralized error handler
│       ├── sleep.js                  ← async sleep utility
│       ├── parseGeminiJSON.js        ← safe JSON parser for Gemini responses
│       ├── fingerprint.js            ← topic fingerprint + Jaccard similarity
│       ├── emailer.js                ← nodemailer wrapper for approval emails
│       └── imageUtils.js            ← base64 → file, resize utilities
│
├── data/                             ← SQLite DB lives here (git-ignored)
│   └── .gitkeep
│
├── outputs/
│   ├── articles/                     ← generated markdown articles
│   ├── images/                       ← generated/scraped images
│   └── logs/                         ← run logs
│
└── tests/
    ├── agents/
    │   ├── crawlerAgent.test.js
    │   ├── filterAgent.test.js
    │   └── contentAgent.test.js
    └── utils/
        ├── fingerprint.test.js
        └── parseGeminiJSON.test.js
```

---

## 3. FILE-BY-FILE SPECIFICATION

### 3.1 `package.json`

```json
{
  "name": "newsbot-blogs",
  "version": "1.0.0",
  "description": "Automated motorcycle blog pipeline for NewsBot using Gemini API",
  "type": "module",
  "main": "src/index.js",
  "scripts": {
    "start": "node src/index.js",
    "dev": "node --watch src/index.js",
    "test": "node --test tests/**/*.test.js",
    "migrate": "node src/db/database.js",
    "approval-server": "node src/approval/approvalServer.js"
  },
  "dependencies": {
    "@google/genai": "^1.0.0",
    "better-sqlite3": "^9.4.3",
    "dotenv": "^16.4.5",
    "express": "^4.18.3",
    "node-cron": "^3.0.3",
    "nodemailer": "^6.9.13",
    "sharp": "^0.33.3",
    "winston": "^3.13.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0"
  }
}
```

---

### 3.2 `.env.example`

```env
# Gemini API
GEMINI_API_KEY=your_gemini_api_key_here

# Email (for approval workflow)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
APPROVER_EMAILS=approver1@example.com,approver2@example.com

# App config
PORT=3001
BASE_URL=http://localhost:3001
SITE_NAME=NewsBot

# Pipeline config
CRAWL_INTERVAL_HOURS=6
RELEVANCE_THRESHOLD=0.6
MAX_RETRIES=3

# CMS (optional webhook endpoint to POST published articles)
CMS_WEBHOOK_URL=https://your-cms.com/api/articles
CMS_API_KEY=your_cms_key
```

---

### 3.3 `src/config/config.js`

**PURPOSE:** Single source of truth for all tunable constants.

```js
// FILE: src/config/config.js | PURPOSE: Centralized config constants
export const CONFIG = {
  gemini: {
    model: "gemini-2.0-flash",
    imageModel: "imagen-3.0-generate-002",
    temperature: 0.7,
    maxOutputTokens: 2048,
    rateLimitDelayMs: 2000,
  },
  pipeline: {
    crawlIntervalHours: parseInt(process.env.CRAWL_INTERVAL_HOURS) || 6,
    lookbackWindowHours: 8,
    relevanceThreshold: parseFloat(process.env.RELEVANCE_THRESHOLD) || 0.6,
    minSourcesForValidation: 2,
    validationScoreThreshold: 0.4,
    articleMinWords: 800,
    articleMaxWords: 1200,
    approvalTimeoutHours: 48,
    maxEditCycles: 2,
  },
  keywords: {
    motorcycle: [
      "motorcycle", "bike", "two-wheeler", "scooter", "moped",
      "bajaj", "hero", "tvs", "royal enfield", "honda", "yamaha", "suzuki",
      "kawasaki", "ktm", "triumph", "harley", "ducati", "bmw motorrad",
      "ola electric", "ather", "simple energy", "revolt",
      "launch", "specs", "review", "price", "mileage", "cc", "bhp",
      "ev", "electric bike", "range", "charging", "recall", "racing",
      "motogp", "dakar", "superbike", "cruiser", "adventure",
    ],
  },
  sources: [
    "https://www.bikewale.com/",
    "https://www.bikedekho.com/",
    "https://auto.ndtv.com/motorcycles",
    "https://www.motorbeam.com/",
    "https://rushlane.com/two-wheelers",
  ],
  paths: {
    articlesDir: "./outputs/articles",
    imagesDir: "./outputs/images",
    logsDir: "./outputs/logs",
    dbPath: "./data/newsbot.db",
  },
};
```

---

### 3.4 `src/utils/logger.js`

**PURPOSE:** Winston-based structured logger. All modules import from here.

**Implementation rules:**
- Create a Winston logger with two transports: Console (colorized) + File (`./outputs/logs/app.log`)
- Log format: `[TIMESTAMP] [LEVEL] [MODULE] message { meta }`
- Export a `createLogger(moduleName)` factory that returns a child logger with `module` field set
- Log levels: `error`, `warn`, `info`, `debug`

---

### 3.5 `src/utils/sleep.js`

**PURPOSE:** Simple async sleep to respect Gemini rate limits.

```js
// FILE: src/utils/sleep.js | PURPOSE: Async sleep for rate limiting
export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
```

---

### 3.6 `src/utils/parseGeminiJSON.js`

**PURPOSE:** Safely parse Gemini responses that should be JSON. Strips markdown fences if present.

**Implementation rules:**
- Function signature: `parseGeminiJSON(responseText, context)`
- Strip ` ```json ` and ` ``` ` fences before parsing
- Wrap in try/catch; on failure log the raw text and `context`, then throw a typed `GeminiParseError`
- Export `parseGeminiJSON` as named export

---

### 3.7 `src/utils/fingerprint.js`

**PURPOSE:** Topic fingerprinting and Jaccard similarity for story deduplication.

**Implementation rules:**

```js
// FILE: src/utils/fingerprint.js | PURPOSE: Topic fingerprint + Jaccard similarity

const STOP_WORDS = new Set([
  "a","an","the","is","in","on","at","to","for","of","and","or",
  "but","with","from","by","as","that","this","was","are","be",
  "has","have","had","its","it","will","new","also","after","before",
]);

/**
 * Generates a topic fingerprint from a title string.
 * @param {string} title
 * @returns {Set<string>} - sorted set of significant nouns
 */
export function generateFingerprint(title) {
  // 1. lowercase
  // 2. remove punctuation
  // 3. split by whitespace
  // 4. filter out stop words and words < 3 chars
  // 5. take first 8 words
  // 6. return as Set
}

/**
 * Computes Jaccard similarity between two Sets.
 * @param {Set<string>} setA
 * @param {Set<string>} setB
 * @returns {number} - similarity score 0.0 to 1.0
 */
export function jaccardSimilarity(setA, setB) {
  const intersection = new Set([...setA].filter((x) => setB.has(x)));
  const union = new Set([...setA, ...setB]);
  return union.size === 0 ? 0 : intersection.size / union.size;
}
```

---

### 3.8 `src/db/migrations/001_initial_schema.sql`

**PURPOSE:** Full SQLite schema. Run once on first start.

```sql
-- FILE: src/db/migrations/001_initial_schema.sql

CREATE TABLE IF NOT EXISTS job_registry (
  run_id TEXT PRIMARY KEY,
  triggered_at TEXT NOT NULL,
  trigger_type TEXT NOT NULL DEFAULT 'scheduled',
  status TEXT NOT NULL DEFAULT 'running',
  completed_at TEXT,
  items_fetched INTEGER DEFAULT 0,
  items_passed_filter INTEGER DEFAULT 0,
  articles_generated INTEGER DEFAULT 0,
  articles_published INTEGER DEFAULT 0,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS raw_items (
  item_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  url_hash TEXT NOT NULL UNIQUE,
  published_at TEXT,
  snippet TEXT,
  full_text TEXT,
  language TEXT DEFAULT 'en',
  full_text_available INTEGER DEFAULT 0,
  relevance_score REAL DEFAULT 0.0,
  status TEXT DEFAULT 'pending',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (run_id) REFERENCES job_registry(run_id)
);

CREATE TABLE IF NOT EXISTS story_clusters (
  cluster_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  canonical_topic TEXT NOT NULL,
  source_count INTEGER DEFAULT 1,
  low_confidence INTEGER DEFAULT 0,
  item_ids TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (run_id) REFERENCES job_registry(run_id)
);

CREATE TABLE IF NOT EXISTS extracted_stories (
  story_id TEXT PRIMARY KEY,
  cluster_id TEXT NOT NULL,
  headline_summary TEXT,
  key_facts TEXT,
  entities TEXT,
  event_type TEXT,
  quoted_statements TEXT,
  field_confidences TEXT,
  validation_score REAL DEFAULT 0.0,
  hold_for_review INTEGER DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (cluster_id) REFERENCES story_clusters(cluster_id)
);

CREATE TABLE IF NOT EXISTS draft_articles (
  article_id TEXT PRIMARY KEY,
  story_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  title TEXT,
  meta_description TEXT,
  slug TEXT UNIQUE,
  body TEXT,
  tags TEXT,
  category TEXT,
  image_prompt TEXT,
  image_url TEXT,
  image_source TEXT,
  alt_text TEXT,
  image_status TEXT DEFAULT 'pending',
  source_urls TEXT,
  approval_status TEXT DEFAULT 'pending',
  approved_by TEXT,
  approved_at TEXT,
  rejected_by TEXT,
  rejected_reason TEXT,
  edit_count INTEGER DEFAULT 0,
  approval_expires_at TEXT,
  published_url TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (story_id) REFERENCES extracted_stories(story_id),
  FOREIGN KEY (run_id) REFERENCES job_registry(run_id)
);

CREATE TABLE IF NOT EXISTS published_slugs (
  slug TEXT PRIMARY KEY,
  article_id TEXT NOT NULL,
  published_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_items_run ON raw_items(run_id);
CREATE INDEX IF NOT EXISTS idx_raw_items_status ON raw_items(status);
CREATE INDEX IF NOT EXISTS idx_draft_articles_status ON draft_articles(approval_status);
CREATE INDEX IF NOT EXISTS idx_draft_articles_run ON draft_articles(run_id);
```

---

### 3.9 `src/db/database.js`

**PURPOSE:** Initialize SQLite connection, run migrations on first start.

**Implementation rules:**
- Import `better-sqlite3`
- On module load: create `./data/` directory if not exists
- Read and execute `001_initial_schema.sql` using `db.exec()`
- Export a singleton `db` instance
- Export `initDB()` function that runs the migration and logs success

---

### 3.10 `src/agents/crawlerAgent.js`

**PURPOSE:** Stage 2 — Discover motorcycle news using Gemini Search Grounding.

**Inputs:** `runId: string`, `sources: string[]`
**Output:** `RawItem[]`

**Implementation rules:**

```js
// FILE: src/agents/crawlerAgent.js | PURPOSE: Stage 2 — news crawl via Gemini Search grounding

import { GoogleGenAI } from "@google/genai";
import { CONFIG } from "../config/config.js";
import { sleep } from "../utils/sleep.js";
import { createLogger } from "../utils/logger.js";
import { crypto } from "crypto"; // for URL hashing
import { insertRawItem, urlHashExists } from "../db/queries/rawItems.js";

const logger = createLogger("crawlerAgent");

/**
 * Discovers recent motorcycle news using Gemini's Google Search grounding.
 * For each search query, calls Gemini with googleSearch tool enabled.
 * Parses grounding metadata to extract source URLs and snippets.
 *
 * @param {string} runId - current pipeline run ID
 * @returns {Promise<RawItem[]>} - array of raw news items persisted to DB
 */
export async function runCrawlerAgent(runId) {
  const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

  // Define 5 search queries covering different motorcycle news angles
  const searchQueries = [
    "new motorcycle launch India 2024 2025 price specs",
    "electric two-wheeler EV scooter India launch review",
    "motorcycle recall safety alert India",
    "superbike premium motorcycle India price update",
    "motorcycle racing MotoGP result India news",
  ];

  const rawItems = [];

  for (const query of searchQueries) {
    await sleep(CONFIG.gemini.rateLimitDelayMs);

    // Call Gemini with Google Search tool
    const response = await ai.models.generateContent({
      model: CONFIG.gemini.model,
      contents: `Find the 5 most recent and specific news items for: "${query}". 
                 For each item return: title, URL, published date, and a 2-3 sentence summary.
                 Focus only on news from the last 8 hours if possible, otherwise last 24 hours.`,
      config: {
        tools: [{ googleSearch: {} }],
        responseMimeType: "application/json",
        responseSchema: {
          type: "object",
          properties: {
            items: {
              type: "array",
              items: {
                type: "object",
                properties: {
                  title: { type: "string" },
                  url: { type: "string" },
                  published_at: { type: "string" },
                  snippet: { type: "string" },
                },
                required: ["title", "url", "snippet"],
              },
            },
          },
        },
      },
    });

    // Parse response, compute URL hash, check for duplicates, persist to DB
    // For each item: generate item_id as UUID, compute url_hash as SHA256 of URL
    // Skip if url_hash already exists in DB (deduplication)
    // Set full_text_available: false (full extraction happens in factAgent)
    // Persist via insertRawItem()
  }

  logger.info(`Crawler complete`, { runId, totalItems: rawItems.length });
  return rawItems;
}
```

---

### 3.11 `src/agents/filterAgent.js`

**PURPOSE:** Stage 3 — Score relevance of each raw item.

**Inputs:** `rawItems: RawItem[]`
**Output:** `RawItem[]` (only items with `relevance_score >= threshold`)

**Implementation rules:**

```js
// FILE: src/agents/filterAgent.js | PURPOSE: Stage 3 — keyword-based relevance scoring

/**
 * Scores each RawItem for motorcycle relevance.
 * Scoring logic (additive):
 *   +0.4 if title contains >= 1 keyword from CONFIG.keywords.motorcycle
 *   +0.3 if snippet contains >= 1 keyword
 *   +0.2 bonus if BOTH title AND snippet contain keywords
 *   -0.3 if title/snippet contains: "sponsored", "ad", "partner", "promoted"
 *   -0.2 if language !== 'en'
 * Clamp final score to [0.0, 1.0]
 * Update item.relevance_score and item.status in DB
 * Return only items where relevance_score >= CONFIG.pipeline.relevanceThreshold
 *
 * @param {RawItem[]} rawItems
 * @returns {Promise<RawItem[]>} filtered items
 */
export async function runFilterAgent(rawItems) { ... }
```

---

### 3.12 `src/agents/groupingAgent.js`

**PURPOSE:** Stage 4 — Cluster similar stories using Jaccard fingerprint similarity.

**Inputs:** `filteredItems: RawItem[]`
**Output:** `StoryCluster[]`

**Implementation rules:**

```js
// FILE: src/agents/groupingAgent.js | PURPOSE: Stage 4 — cluster stories by topic fingerprint

/**
 * Groups similar news items into StoryCluster objects.
 *
 * Algorithm:
 * 1. Compute topic_fingerprint for each item using generateFingerprint(item.title)
 * 2. Union-Find clustering: items with jaccardSimilarity >= 0.5 are in the same cluster
 * 3. For each cluster, set canonical_source = item with earliest published_at + highest relevance_score
 * 4. Check for near-duplicate clusters (cluster-level Jaccard >= 0.7) — merge them
 * 5. Single-item clusters get low_confidence: true
 * 6. Persist each cluster via insertStoryCluster()
 *
 * @param {RawItem[]} filteredItems
 * @param {string} runId
 * @returns {Promise<StoryCluster[]>}
 */
export async function runGroupingAgent(filteredItems, runId) { ... }
```

---

### 3.13 `src/agents/factAgent.js`

**PURPOSE:** Stage 5 — Extract structured facts from each story cluster using Gemini.

**Inputs:** `clusters: StoryCluster[]`
**Output:** `ExtractedStory[]`

**Implementation rules:**

```js
// FILE: src/agents/factAgent.js | PURPOSE: Stage 5 — Gemini-powered structured fact extraction

/**
 * For each StoryCluster, combines text from all items and calls Gemini
 * to extract structured facts as JSON.
 *
 * Gemini call config:
 *   - model: gemini-2.0-flash
 *   - responseMimeType: "application/json"
 *   - responseSchema: ExtractedStorySchema (defined below)
 *   - systemInstruction: "You are a motorcycle journalism fact-checker..."
 *
 * ExtractedStorySchema = {
 *   headline_summary: string (max 20 words),
 *   key_facts: string[] (max 8 items — prices, dates, model names, specs),
 *   entities: {
 *     bike_models: string[],
 *     brands: string[],
 *     people: string[],
 *     locations: string[],
 *     dates: string[],
 *   },
 *   event_type: enum["launch","update","recall","race_result","regulation","business_news","review"],
 *   quoted_statements: Array<{ speaker: string, quote: string }>,
 *   single_source_fields: string[] (fields only confirmed by 1 source),
 * }
 *
 * After parsing: persist to extracted_stories table.
 * Await sleep(CONFIG.gemini.rateLimitDelayMs) between each cluster.
 *
 * @param {StoryCluster[]} clusters
 * @returns {Promise<ExtractedStory[]>}
 */
export async function runFactAgent(clusters) { ... }
```

---

### 3.14 `src/agents/validationAgent.js`

**PURPOSE:** Stage 6 — Cross-source validation and conflict detection.

**Inputs:** `extractedStories: ExtractedStory[]`
**Output:** `ValidatedStory[]`

**Implementation rules:**

```js
// FILE: src/agents/validationAgent.js | PURPOSE: Stage 6 — cross-source fact validation

/**
 * Validates extracted facts against all sources in the cluster.
 *
 * For each story:
 * 1. Call Gemini with ALL source snippets combined and ask it to verify each key_fact
 *    - "For each fact, state: verified (seen in 2+ sources), unverified (1 source only),
 *       or conflict (sources disagree — list both values)"
 * 2. Parse structured response with per-fact validation status
 * 3. Compute validation_score = verified_count / total_facts
 * 4. If validation_score < 0.4 AND source_count < 2: set hold_for_review = true
 * 5. Update extracted_stories record in DB
 *
 * Gemini call uses responseMimeType: "application/json"
 * responseSchema includes: { facts_validation: Array<{ fact, status, conflict_values? }> }
 *
 * @param {ExtractedStory[]} stories
 * @returns {Promise<ValidatedStory[]>} stories with validation metadata
 */
export async function runValidationAgent(stories) { ... }
```

---

### 3.15 `src/agents/contentAgent.js`

**PURPOSE:** Stage 7 — Generate full article draft using Gemini.

**Inputs:** `validatedStory: ValidatedStory`
**Output:** `DraftArticle`

**Implementation rules:**

```js
// FILE: src/agents/contentAgent.js | PURPOSE: Stage 7 — article generation via Gemini

/**
 * Generates a complete blog article for a validated story.
 *
 * Gemini call:
 *   model: "gemini-2.0-flash"
 *   systemInstruction: (see SYSTEM_PROMPT below)
 *   responseMimeType: "application/json"
 *   responseSchema: DraftArticleSchema
 *   temperature: 0.75
 *   maxOutputTokens: 3000
 *
 * SYSTEM_PROMPT:
 * "You are a senior motorcycle journalist writing for NewsBot, India's leading
 *  two-wheeler fintech and content platform. Your audience is Indian motorcycle
 *  enthusiasts aged 22–38. Write in an engaging, knowledgeable tone. Use Indian
 *  context (INR prices, Indian roads, Indian brands first). For any fact flagged
 *  as 'unverified' or 'conflict', use hedging language like 'reportedly' or
 *  'according to sources'. Never invent specifications."
 *
 * DraftArticleSchema = {
 *   title: string (50-60 chars, SEO optimized),
 *   meta_description: string (150-160 chars),
 *   slug: string (URL-safe, max 60 chars),
 *   body: string (markdown, 800-1200 words, H2 subheadings),
 *   tags: string[] (3-6 tags),
 *   category: string (one of: launch|review|news|racing|ev|recall),
 *   image_prompt: string (descriptive prompt for Imagen),
 * }
 *
 * After generation:
 * - Validate all fields present and within length limits
 * - If any field missing, regenerate that field with a targeted prompt
 * - Persist to draft_articles table
 * - Set approval_expires_at = NOW + 48 hours
 *
 * @param {ValidatedStory} story
 * @param {string} runId
 * @returns {Promise<DraftArticle>}
 */
export async function runContentAgent(story, runId) { ... }

// Content user prompt template (fill with story data before sending):
export const CONTENT_USER_PROMPT = `
Write a complete blog article about the following motorcycle news story for NewsBot.

HEADLINE: {headline_summary}

KEY FACTS:
{key_facts_formatted}

ENTITIES:
- Bikes: {bike_models}
- Brands: {brands}
- Event type: {event_type}

UNVERIFIED/CONFLICTING FACTS (use hedging language for these):
{unverified_facts}

QUOTED STATEMENTS:
{quoted_statements}

Generate the full article as specified in the schema.
`;
```

---

### 3.16 `src/agents/imageAgent.js`

**PURPOSE:** Stage 8 — Generate or source article hero image using Imagen.

**Inputs:** `draft: DraftArticle`
**Output:** `DraftArticle` (with `image_url`, `image_source`, `alt_text` populated)

**Implementation rules:**

```js
// FILE: src/agents/imageAgent.js | PURPOSE: Stage 8 — image generation via Imagen 3

/**
 * Generates a hero image for the article using Google Imagen 3.
 *
 * Steps:
 * 1. Enhance the image_prompt from contentAgent:
 *    Append: ", professional motorcycle photography, high resolution,
 *    clean background, photorealistic, side profile view, Indian setting"
 * 2. Call ai.models.generateImages with imagen-3.0-generate-002
 *    config: { numberOfImages: 1, aspectRatio: "16:9", outputMimeType: "image/jpeg" }
 * 3. Get response.generatedImages[0].image.imageBytes (base64 string)
 * 4. Write to ./outputs/images/{slug}-hero.jpg using:
 *    Buffer.from(imageBytes, 'base64')
 * 5. Resize to 1200x630 using sharp (OG image standard)
 * 6. Also generate thumbnail at 400x300
 * 7. Set image_source: "generated", image_status: "ready"
 * 8. On any Imagen failure (after 2 retries): set image_source: "fallback",
 *    copy ./outputs/images/fallback-moto.jpg as the image
 * 9. Update draft_articles record in DB
 *
 * @param {DraftArticle} draft
 * @returns {Promise<DraftArticle>}
 */
export async function runImageAgent(draft) { ... }
```

---

### 3.17 `src/approval/approvalService.js`

**PURPOSE:** Stage 9 — Send approval email, track state, handle responses.

**Implementation rules:**

```js
// FILE: src/approval/approvalService.js | PURPOSE: Stage 9 — approval email workflow

/**
 * Sends an HTML approval email for a draft article.
 *
 * Email structure:
 * - Subject: "[NEWSAI APPROVAL] {title} — Action Required"
 * - Body (HTML):
 *   - Article preview section: title, meta, first 300 words of body, image thumbnail
 *   - Source URLs used
 *   - Conflict/unverified fields highlighted in yellow
 *   - Three CTA buttons (styled):
 *       [✅ APPROVE] → GET {BASE_URL}/approve/{article_id}?token={approval_token}&action=approve
 *       [❌ REJECT]  → GET {BASE_URL}/approve/{article_id}?token={approval_token}&action=reject
 *       [✏️ REQUEST EDIT] → GET {BASE_URL}/approve/{article_id}?token={approval_token}&action=edit
 *   - "This link expires in 48 hours"
 *
 * approval_token = SHA256(article_id + secret + expires_at)
 *
 * @param {DraftArticle} draft
 * @returns {Promise<void>}
 */
export async function sendApprovalEmail(draft) { ... }

/**
 * Marks article as approved, updates DB.
 * @param {string} articleId
 * @param {string} approverEmail
 */
export async function approveArticle(articleId, approverEmail) { ... }

/**
 * Marks article as rejected, updates DB.
 * @param {string} articleId
 * @param {string} reason
 */
export async function rejectArticle(articleId, reason) { ... }

/**
 * Checks all pending approvals for timeout (> 48h).
 * Archives timed-out articles. Should be called by cron every hour.
 */
export async function checkApprovalTimeouts() { ... }
```

---

### 3.18 `src/approval/approvalServer.js`

**PURPOSE:** Lightweight Express server to handle approval webhook callbacks.

**Implementation rules:**

```js
// FILE: src/approval/approvalServer.js | PURPOSE: Express server for approval callbacks

import express from "express";
const app = express();

// GET /approve/:articleId?token=...&action=approve|reject|edit
// 1. Validate token (must match expected HMAC)
// 2. Check article exists and is still pending
// 3. Check not expired (approval_expires_at > NOW)
// 4. Call approvalService.approveArticle() or rejectArticle()
// 5. If action=edit: render a simple HTML form for edit submission
// 6. Return styled HTML confirmation page ("Article approved! It will publish at 8am.")
// 7. POST /approve/:articleId/edit-submit to receive edit form submissions

app.get("/approve/:articleId", handleApprovalCallback);
app.post("/approve/:articleId/edit-submit", handleEditSubmit);
app.get("/health", (req, res) => res.json({ status: "ok" }));

app.listen(process.env.PORT || 3001);
```

---

### 3.19 `src/agents/publisherAgent.js`

**PURPOSE:** Stage 10 — Publish approved article to CMS and update records.

**Implementation rules:**

```js
// FILE: src/agents/publisherAgent.js | PURPOSE: Stage 10 — publish approved articles

/**
 * Publishes an approved article.
 *
 * Steps:
 * 1. Check publish timing:
 *    - If current local hour is 6–22: publish immediately
 *    - Else: schedule for 08:00 next day (set scheduled_publish_at in DB, cron picks it up)
 * 2. Write article to ./outputs/articles/{slug}.md (full markdown file with frontmatter)
 *    Frontmatter: title, meta_description, slug, tags, category, image_url, published_at
 * 3. If CMS_WEBHOOK_URL is set: POST to CMS with article payload (JSON)
 *    - Retry 3x with exponential backoff (1s, 5s, 15s)
 *    - On success: set published_url from CMS response
 *    - On failure after retries: alert ops (log ERROR), keep article in DB for retry
 * 4. Insert slug into published_slugs table
 * 5. Update draft_articles: approval_status='published', published_url, completed_at
 * 6. Update job_registry: articles_published += 1
 * 7. Log success with published_url
 *
 * @param {DraftArticle} draft
 * @returns {Promise<{ published_url: string }>}
 */
export async function runPublisherAgent(draft) { ... }
```

---

### 3.20 `src/pipeline/blogPipeline.js`

**PURPOSE:** Orchestrates all agents in sequence for a single run.

**Implementation rules:**

```js
// FILE: src/pipeline/blogPipeline.js | PURPOSE: Main pipeline orchestrator

/**
 * Runs the complete blog automation pipeline for one cycle.
 *
 * Sequence:
 * 1. Create JobRegistry entry (status: running)
 * 2. runCrawlerAgent(runId) → rawItems[]
 * 3. runFilterAgent(rawItems) → filteredItems[]
 *    - If filteredItems.length === 0: log no_relevant_news, update job status: no_news, return
 * 4. runGroupingAgent(filteredItems, runId) → clusters[]
 * 5. runFactAgent(clusters) → extractedStories[]
 * 6. runValidationAgent(extractedStories) → validatedStories[]
 * 7. For each story NOT hold_for_review:
 *    a. runContentAgent(story, runId) → draft
 *    b. runImageAgent(draft) → draft (with image)
 *    c. sendApprovalEmail(draft)
 * 8. Update JobRegistry (status: awaiting_approval, counts)
 * 9. Log pipeline summary
 *
 * Error handling: wrap entire pipeline in try/catch
 * On any unhandled error: update JobRegistry status: failed, error_message
 *
 * @param {string} runId
 * @returns {Promise<PipelineSummary>}
 */
export async function runBlogPipeline(runId) { ... }
```

---

### 3.21 `src/pipeline/pipelineRunner.js`

**PURPOSE:** Cron scheduler + duplicate run guard.

**Implementation rules:**

```js
// FILE: src/pipeline/pipelineRunner.js | PURPOSE: Cron trigger + run guard

import cron from "node-cron";
import { v4 as uuidv4 } from "uuid"; // add uuid to package.json deps
import { runBlogPipeline } from "./blogPipeline.js";
import { getActiveRun, createJobEntry } from "../db/queries/jobRegistry.js";
import { createLogger } from "../utils/logger.js";

const logger = createLogger("pipelineRunner");

let isRunning = false;

/**
 * Triggers a pipeline run with duplicate guard.
 * Sets isRunning flag, generates runId, calls runBlogPipeline.
 */
export async function triggerRun(triggerType = "scheduled") {
  if (isRunning) {
    logger.warn("Pipeline already running, skipping this cycle");
    return;
  }
  isRunning = true;
  const runId = uuidv4();
  try {
    logger.info("Pipeline triggered", { runId, triggerType });
    await createJobEntry(runId, triggerType);
    await runBlogPipeline(runId);
  } finally {
    isRunning = false;
  }
}

/**
 * Starts the cron scheduler.
 * Default: every 6 hours ("0 */6 * * *")
 * Also schedules approval timeout check every hour.
 */
export function startScheduler() {
  const interval = CONFIG.pipeline.crawlIntervalHours;
  const cronExpr = `0 */${interval} * * *`;
  cron.schedule(cronExpr, () => triggerRun("scheduled"));
  cron.schedule("0 * * * *", () => checkApprovalTimeouts()); // every hour
  logger.info("Scheduler started", { cronExpr });
}
```

---

### 3.22 `src/index.js`

**PURPOSE:** Application entry point.

```js
// FILE: src/index.js | PURPOSE: Application entry point

import "dotenv/config";
import { initDB } from "./db/database.js";
import { startScheduler, triggerRun } from "./pipeline/pipelineRunner.js";
import { createLogger } from "./utils/logger.js";

const logger = createLogger("index");

async function main() {
  logger.info("🏍️  NewsBot Blogs starting up...");

  // Initialize database
  await initDB();

  // If --run-now flag passed, trigger immediately
  if (process.argv.includes("--run-now")) {
    logger.info("Manual run triggered via --run-now flag");
    await triggerRun("manual");
  }

  // Start cron scheduler
  startScheduler();

  logger.info("NewsBot Blogs is running. Approval server on port", process.env.PORT);
}

main().catch((err) => {
  console.error("Fatal startup error:", err);
  process.exit(1);
});
```

---

## 4. DB QUERY MODULES

Each query file in `src/db/queries/` must export these exact functions:

### `rawItems.js`
- `insertRawItem(item)` → void
- `urlHashExists(urlHash)` → boolean
- `getRawItemsByRun(runId)` → RawItem[]
- `updateRawItemScore(itemId, score, status)` → void

### `storyClusters.js`
- `insertStoryCluster(cluster)` → void
- `getClustersByRun(runId)` → StoryCluster[]
- `getClusterWithItems(clusterId)` → StoryCluster & items[]

### `draftArticles.js`
- `insertDraftArticle(draft)` → void
- `updateDraftArticle(articleId, fields)` → void
- `getDraftByArticleId(articleId)` → DraftArticle
- `getPendingApprovals()` → DraftArticle[]
- `getExpiredApprovals(cutoffTime)` → DraftArticle[]

### `jobRegistry.js`
- `createJobEntry(runId, triggerType)` → void
- `updateJobStatus(runId, status, fields)` → void
- `getActiveRun()` → JobRegistry | null

---

## 5. ERROR HANDLING STANDARD

Every agent function must follow this pattern:

```js
try {
  // ... agent logic
} catch (error) {
  logger.error("Agent failed", {
    agent: "crawlerAgent",
    runId,
    error: error.message,
    stack: error.stack,
  });
  // For non-critical errors: log and continue
  // For critical errors: rethrow to pipeline orchestrator
  throw error;
}
```

Gemini API errors to handle:
- `429 Resource exhausted` → `await sleep(60000)` then retry once
- `503 Service unavailable` → retry with exponential backoff, max 3 attempts
- `400 Invalid argument` → log prompt + response, throw `GeminiInputError`

---

## 6. OUTPUT FILE FORMAT

Every published article written to `./outputs/articles/{slug}.md` must use this frontmatter:

```markdown
---
title: "Royal Enfield Guerrilla 450 Launched at ₹2.39 Lakh"
slug: "royal-enfield-guerrilla-450-launch-2024"
meta_description: "Royal Enfield Guerrilla 450 launched..."
category: "launch"
tags: ["royal-enfield", "guerrilla-450", "motorcycle-launch", "adventure"]
image_url: "./outputs/images/royal-enfield-guerrilla-450-launch-2024-hero.jpg"
image_alt: "2024 Royal Enfield Guerrilla 450 side profile"
published_at: "2024-11-15T08:00:00+05:30"
source_urls:
  - "https://source1.com/article"
  - "https://source2.com/article"
author: "NewsBot Editorial Team"
---

{article body in markdown}
```

---

## 7. TESTING REQUIREMENTS

Each test file uses Node.js built-in `node:test` module (no external test framework needed).

### `tests/utils/fingerprint.test.js`
- Test `generateFingerprint` removes stop words correctly
- Test `jaccardSimilarity` returns 1.0 for identical sets, 0.0 for disjoint sets
- Test clustering groups articles with Jaccard >= 0.5

### `tests/utils/parseGeminiJSON.test.js`
- Test strips markdown fences before parsing
- Test returns parsed object on valid JSON
- Test throws `GeminiParseError` on invalid JSON

### `tests/agents/filterAgent.test.js`
- Test items with motorcycle keywords score >= 0.6
- Test items with "sponsored" in title get penalty
- Test items below threshold are excluded

---

## 8. START SEQUENCE (for Codex to execute)

```bash
# 1. Navigate to project
cd newsbot-blogs

# 2. Install dependencies
npm install

# 3. Copy env file and fill in GEMINI_API_KEY
cp .env.example .env

# 4. Run DB migration
npm run migrate

# 5. Run one pipeline cycle immediately (for testing)
node src/index.js --run-now

# 6. Start full service with scheduler
npm start

# 7. Start approval server (separate terminal)
npm run approval-server
```

---

## 9. IMPORTANT NOTES FOR CODEX

1. **Do not use `googleapis` package** — use only `@google/genai` (the new Gen AI SDK)
2. **Model names as of 2025:** use `"gemini-2.0-flash"` for text, `"imagen-3.0-generate-002"` for images
3. **JSON schema in Gemini:** when using `responseMimeType: "application/json"`, always also provide `responseSchema` — Gemini enforces structured output
4. **Imagen response:** `response.generatedImages[0].image.imageBytes` is a base64-encoded JPEG string, NOT a URL — write it to disk as a Buffer
5. **Google Search grounding:** the `tools: [{ googleSearch: {} }]` config makes Gemini search the web and return grounding metadata — parse `response.candidates[0].groundingMetadata.groundingChunks` for source URLs
6. **SQLite vs async:** `better-sqlite3` is synchronous — do NOT use `await` with its methods. Wrap in regular `try/catch`
7. **ESM modules:** `"type": "module"` in package.json means all imports must use `.js` extensions
8. **Rate limits:** always `await sleep(2000)` between Gemini API calls in any loop. For Imagen, use `await sleep(6000)`
9. **The `uuid` package** must be added to `package.json` dependencies for `runId` generation
10. **fallback image:** create a placeholder `./outputs/images/fallback-moto.jpg` in the project — this is used when Imagen fails

---

*End of AGENT.md — NewsBot Blogs for Vehicles*
