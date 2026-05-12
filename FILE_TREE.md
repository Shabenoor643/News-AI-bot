# FILE_TREE.md — NewsBot Blogs
# Every file the agent must create, with its exact purpose

newsbot-blogs/
│
├── AGENT.md                          ← Full codex spec (primary build file)
├── README.md                         ← Human-readable project overview
├── FILE_TREE.md                      ← This file
├── package.json                      ← ESM, all deps, npm scripts
├── .env.example                      ← All required env vars with descriptions
├── .gitignore                        ← Ignores: node_modules, .env, data/, outputs/
│
├── src/
│   │
│   ├── index.js
│   │   PURPOSE: App entry point. Calls initDB(), startScheduler(). Handles --run-now flag.
│   │
│   ├── config/
│   │   └── config.js
│   │       PURPOSE: All constants. Gemini model names, thresholds, keyword list, source URLs.
│   │
│   ├── agents/
│   │   ├── crawlerAgent.js
│   │   │   PURPOSE: Calls Gemini with Google Search grounding. Returns RawItem[].
│   │   │   GEMINI FEATURE: tools: [{ googleSearch: {} }]
│   │   │
│   │   ├── filterAgent.js
│   │   │   PURPOSE: Keyword relevance scoring. No Gemini call needed (pure JS logic).
│   │   │
│   │   ├── groupingAgent.js
│   │   │   PURPOSE: Union-Find clustering by Jaccard fingerprint similarity.
│   │   │
│   │   ├── factAgent.js
│   │   │   PURPOSE: Structured JSON extraction via Gemini.
│   │   │   GEMINI FEATURE: responseMimeType: "application/json" + responseSchema
│   │   │
│   │   ├── validationAgent.js
│   │   │   PURPOSE: Cross-source fact verification via Gemini.
│   │   │   GEMINI FEATURE: responseMimeType: "application/json" + systemInstruction
│   │   │
│   │   ├── contentAgent.js
│   │   │   PURPOSE: Full article generation via Gemini.
│   │   │   GEMINI FEATURE: systemInstruction + responseMimeType: "application/json" + temperature: 0.75
│   │   │
│   │   ├── imageAgent.js
│   │   │   PURPOSE: Hero image generation via Imagen 3.
│   │   │   GEMINI FEATURE: ai.models.generateImages() with imagen-3.0-generate-002
│   │   │
│   │   └── publisherAgent.js
│   │       PURPOSE: Writes .md file, POSTs to CMS webhook, updates DB.
│   │
│   ├── pipeline/
│   │   ├── blogPipeline.js
│   │   │   PURPOSE: Sequential orchestrator. Calls all agents in order. Error boundary.
│   │   │
│   │   └── pipelineRunner.js
│   │       PURPOSE: node-cron scheduler. Duplicate run guard. Triggers blogPipeline.
│   │
│   ├── approval/
│   │   ├── approvalService.js
│   │   │   PURPOSE: Builds and sends HTML approval email via nodemailer.
│   │   │            Exposes approveArticle(), rejectArticle(), checkApprovalTimeouts().
│   │   │
│   │   └── approvalServer.js
│   │       PURPOSE: Express app. Handles GET /approve/:id callbacks.
│   │                Renders HTML confirmation page. Handles edit form POST.
│   │
│   ├── db/
│   │   ├── database.js
│   │   │   PURPOSE: better-sqlite3 singleton. Runs SQL migration on init.
│   │   │
│   │   ├── migrations/
│   │   │   └── 001_initial_schema.sql
│   │   │       PURPOSE: Full DB schema — 6 tables, indexes.
│   │   │
│   │   ├── models/
│   │   │   ├── RawItem.js            ← JSDoc type definition (no logic)
│   │   │   ├── StoryCluster.js       ← JSDoc type definition
│   │   │   ├── DraftArticle.js       ← JSDoc type definition
│   │   │   └── JobRegistry.js        ← JSDoc type definition
│   │   │
│   │   └── queries/
│   │       ├── rawItems.js           ← CRUD for raw_items table
│   │       ├── storyClusters.js      ← CRUD for story_clusters table
│   │       ├── draftArticles.js      ← CRUD for draft_articles table
│   │       └── jobRegistry.js        ← CRUD for job_registry table
│   │
│   └── utils/
│       ├── logger.js                 ← Winston factory. createLogger(moduleName) → child logger.
│       ├── errorHandler.js           ← Typed errors: GeminiParseError, GeminiInputError, DBError
│       ├── sleep.js                  ← export const sleep = (ms) => new Promise(...)
│       ├── parseGeminiJSON.js        ← Strips markdown fences, parses JSON, throws on failure
│       ├── fingerprint.js            ← generateFingerprint(title) + jaccardSimilarity(setA, setB)
│       ├── emailer.js                ← nodemailer transporter factory + sendMail wrapper
│       └── imageUtils.js            ← Base64 → file writer, sharp resize helper
│
├── data/
│   └── .gitkeep                      ← SQLite DB created here at runtime (git-ignored)
│
├── outputs/
│   ├── articles/
│   │   └── .gitkeep
│   ├── images/
│   │   ├── .gitkeep
│   │   └── fallback-moto.jpg         ← MUST EXIST: placeholder when Imagen fails
│   └── logs/
│       └── .gitkeep
│
└── tests/
    ├── agents/
    │   ├── crawlerAgent.test.js
    │   ├── filterAgent.test.js
    │   └── contentAgent.test.js
    └── utils/
        ├── fingerprint.test.js
        └── parseGeminiJSON.test.js

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOTAL FILES TO CREATE: 37
CRITICAL: fallback-moto.jpg must exist in outputs/images/
CRITICAL: All 4 DB model files are type-only (JSDoc @typedef, no logic)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
