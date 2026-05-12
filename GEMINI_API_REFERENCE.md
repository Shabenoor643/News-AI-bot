# GEMINI_API_REFERENCE.md
# Quick Reference for NewsAI Blogs — All Gemini Calls Used in This Project

## Install
```bash
npm install @google/genai
```

## Client Init (use in every agent file)
```js
import { GoogleGenAI } from "@google/genai";
const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
```

---

## 1. Basic Text Generation
**Used in:** `validationAgent.js`
```js
const response = await ai.models.generateContent({
  model: "gemini-2.0-flash",
  contents: "Your prompt here",
});
const text = response.text;
```

---

## 2. Text with System Instruction + Temperature
**Used in:** `contentAgent.js`
```js
const response = await ai.models.generateContent({
  model: "gemini-2.0-flash",
  contents: userPrompt,
  config: {
    systemInstruction: "You are a motorcycle journalist for NewsAI...",
    temperature: 0.75,
    maxOutputTokens: 3000,
  },
});
const text = response.text;
```

---

## 3. Structured JSON Output (most important pattern)
**Used in:** `factAgent.js`, `contentAgent.js`, `validationAgent.js`
```js
const response = await ai.models.generateContent({
  model: "gemini-2.0-flash",
  contents: prompt,
  config: {
    responseMimeType: "application/json",
    responseSchema: {
      type: "object",
      properties: {
        headline_summary: { type: "string" },
        key_facts: {
          type: "array",
          items: { type: "string" },
        },
        event_type: {
          type: "string",
          enum: ["launch", "update", "recall", "race_result", "regulation", "business_news", "review"],
        },
        entities: {
          type: "object",
          properties: {
            bike_models: { type: "array", items: { type: "string" } },
            brands: { type: "array", items: { type: "string" } },
          },
        },
      },
      required: ["headline_summary", "key_facts", "event_type"],
    },
  },
});
// ALWAYS parse through parseGeminiJSON utility:
import { parseGeminiJSON } from "../utils/parseGeminiJSON.js";
const data = parseGeminiJSON(response.text, "factAgent");
```

---

## 4. Google Search Grounding
**Used in:** `crawlerAgent.js`
```js
const response = await ai.models.generateContent({
  model: "gemini-2.0-flash",
  contents: "Latest motorcycle launches in India this week",
  config: {
    tools: [{ googleSearch: {} }],
  },
});

// The text response contains Gemini's synthesis of search results
const synthesizedText = response.text;

// Access individual source URLs from grounding metadata:
const chunks = response.candidates?.[0]?.groundingMetadata?.groundingChunks ?? [];
const sourceUrls = chunks.map(chunk => chunk.web?.uri).filter(Boolean);
```

---

## 5. Image Generation (Imagen 3)
**Used in:** `imageAgent.js`
```js
const response = await ai.models.generateImages({
  model: "imagen-3.0-generate-002",
  prompt: "Professional studio photograph of 2024 Royal Enfield Guerrilla 450, side profile, white background, photorealistic, high resolution",
  config: {
    numberOfImages: 1,
    aspectRatio: "16:9",       // Options: "1:1", "16:9", "9:16", "3:4", "4:3"
    outputMimeType: "image/jpeg",
  },
});

// imageBytes is a BASE64-ENCODED string (NOT a URL)
const imageBase64 = response.generatedImages[0].image.imageBytes;

// Write to disk:
import fs from "fs";
import path from "path";
const buffer = Buffer.from(imageBase64, "base64");
fs.writeFileSync(path.join("./outputs/images", `${slug}-hero.jpg`), buffer);
```

---

## 6. Rate Limiting (MANDATORY in all loops)
```js
import { sleep } from "../utils/sleep.js";
import { CONFIG } from "../config/config.js";

for (const item of items) {
  await sleep(CONFIG.gemini.rateLimitDelayMs); // 2000ms for text models
  const response = await ai.models.generateContent({ ... });
}

// For Imagen, use longer delay:
await sleep(6000); // 6 seconds between image generation calls
```

---

## 7. Error Handling for Gemini Calls
```js
async function callGeminiWithRetry(params, maxRetries = 3) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await ai.models.generateContent(params);
    } catch (error) {
      if (error.status === 429) {
        // Rate limited — wait 60 seconds then retry
        logger.warn("Rate limited, waiting 60s", { attempt });
        await sleep(60000);
      } else if (error.status === 503) {
        // Service unavailable — exponential backoff
        await sleep(attempt * 5000);
      } else if (attempt === maxRetries) {
        throw error; // Rethrow on final attempt
      }
    }
  }
}
```

---

## 8. Model Names (current as of 2025)

| Use Case | Model ID |
|---|---|
| All text tasks | `gemini-2.0-flash` |
| Image generation | `imagen-3.0-generate-002` |
| High-quality text (if needed) | `gemini-1.5-pro` |

---

## 9. Response Schema Type Reference

```js
// Primitive types
{ type: "string" }
{ type: "number" }
{ type: "boolean" }
{ type: "integer" }

// Array
{ type: "array", items: { type: "string" } }

// Object
{
  type: "object",
  properties: {
    fieldName: { type: "string" }
  },
  required: ["fieldName"]
}

// Enum (string with limited values)
{ type: "string", enum: ["option1", "option2", "option3"] }

// Nested array of objects
{
  type: "array",
  items: {
    type: "object",
    properties: {
      speaker: { type: "string" },
      quote: { type: "string" }
    }
  }
}
```

---

## 10. Common Mistakes to Avoid

1. ❌ Don't use `googleapis` package — use only `@google/genai`
2. ❌ Don't assume `response.text` is valid JSON — always use `parseGeminiJSON()`
3. ❌ Don't skip `await sleep()` between calls in loops — you will hit rate limits
4. ❌ Don't try to use `responseSchema` without also setting `responseMimeType: "application/json"`
5. ❌ Don't treat `imageBytes` as a URL — it's base64, write it to disk as a Buffer
6. ❌ Don't forget `.js` extension on all ESM imports
7. ❌ Don't use `await` with `better-sqlite3` methods — it's synchronous
