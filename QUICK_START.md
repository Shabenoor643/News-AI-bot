# 🚀 Quick Start Guide - Upgraded NewsBot Blogs System

## What's New?

### ✅ Fixed Issues
1. **Email Batching** - Each article now gets its own email (not batched)
2. **Article Quality** - Full 1200-2000 word SEO-optimized articles (not summaries)
3. **Edit Workflow** - Articles are automatically regenerated when edits are requested

### 🎯 Key Improvements
- **SEO-Optimized Content**: Proper structure with intro, TOC, H2/H3 sections, FAQ, conclusion
- **Longer Articles**: 1200-2000 words (vs previous 3-4 lines)
- **Better Approval Flow**: Individual emails with regeneration support
- **Indian Market Focus**: ₹ pricing, local context, relevant comparisons

---

## Installation (No Changes)

```bash
# 1. Install dependencies
npm install

# 2. Configure environment
cp .env.example .env
# Edit .env and set:
# - GEMINI_API_KEY
# - SMTP credentials
# - APPROVER_EMAILS

# 3. Initialize database
npm run migrate

# 4. Test run
node src/index.js --run-now

# 5. Start service
npm start
```

---

## How It Works Now

### 1. Article Generation
```
News Discovery → Filtering → Clustering → Fact Extraction → 
SEO Article Generation (1200-2000 words) → Image Generation → 
Individual Email per Article → Approval → Publishing
```

### 2. Email Flow (NEW)
**Before**: All articles in ONE email  
**After**: ONE email per article

Each email contains:
- Subject: `"Article Review Required: [Article Title]"`
- Full article preview (1200-2000 words)
- Buttons: APPROVE | REJECT | EDIT | RETRY IMAGE

### 3. Article Structure (NEW)
Every article now includes:
- **SEO Title** (60-70 chars)
- **Meta Description** (150-160 chars)
- **Introduction** (150-200 words with hook)
- **Table of Contents**
- **Main Sections** (H2/H3):
  - Overview
  - Key Features & Specs
  - Performance & Engine
  - Design & Build
  - Price & Variants (₹)
  - Comparison
  - Pros & Cons
- **FAQ Section** (4-6 questions)
- **Conclusion** (verdict + CTA)

### 4. Edit Workflow (NEW)
**Before**: Edit requests were just recorded  
**After**: Full regeneration workflow

```
Edit Requested → Article Regenerated (with feedback) → 
Status Reset to Pending → New Email Sent
```

---

## Usage

### Run Pipeline Once
```bash
node src/index.js --run-now
```

### Start Scheduled Service (Every 6 hours)
```bash
npm start
```

### Check Status
```bash
# View logs
tail -f outputs/logs/app.log

# Check database
sqlite3 newsai.db "SELECT article_id, title, approval_status FROM draft_articles ORDER BY created_at DESC LIMIT 10;"

# Check generated articles
ls -lh outputs/articles/

# Check word count
wc -w outputs/articles/*.md
```

---

## Approval Workflow

### 1. Receive Email
You'll receive **one email per article** with:
- Article title in subject line
- Full article content (1200-2000 words)
- Action buttons

### 2. Review Article
Check for:
- Content quality and accuracy
- SEO structure (intro, sections, FAQ, conclusion)
- Indian context (₹ pricing)
- Proper specifications
- No hallucinated data

### 3. Take Action

#### Option A: APPROVE
- Click **"APPROVE"** button
- Article moves to publishing queue
- Image generation triggered (if not done)
- Published to CMS

#### Option B: REJECT
- Click **"REJECT"** button
- Article marked as rejected
- No further processing

#### Option C: REQUEST EDIT
- Click **"EDIT"** button
- Fill in feedback form:
  ```
  Email: reviewer@example.com
  Notes: Please add more details about fuel efficiency 
         and make the introduction more engaging.
  ```
- Submit
- **System automatically**:
  - Regenerates article based on feedback
  - Resets status to pending
  - Sends new email with updated article

#### Option D: RETRY IMAGE
- Click **"RETRY IMAGE"** button
- System regenerates image
- New email sent with updated image

---

## Configuration

### Environment Variables

```bash
# Required
GEMINI_API_KEY=your_gemini_api_key
SMTP_HOST=smtp.gmail.com
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
APPROVER_EMAILS=reviewer1@example.com,reviewer2@example.com
BASE_URL=http://your-server.com:3001

# Optional
CMS_WEBHOOK_URL=https://your-cms.com/api/publish
PORT=3001
```

### Article Generation Settings

Located in `src/agents/story_agent.py`:

```python
# Word count: 1200-2000 words
max_output_tokens=16000  # Increased for longer articles

# Temperature: 0.3 (balanced creativity)
temperature=0.3

# Model: gemini-2.0-flash
model=CONFIG.Gemini.model
```

---

## Monitoring

### Check Email Delivery
```bash
# Count emails sent
grep -c "Approval email sent for article" outputs/logs/app.log

# View email logs
grep "Approval email" outputs/logs/app.log
```

### Check Article Quality
```bash
# Word count for all articles
for file in outputs/articles/*.md; do
  echo "=== $file ==="
  wc -w "$file"
  echo ""
done

# Check for required sections
grep -E "^## (FAQ|Table of Contents|Conclusion)" outputs/articles/*.md
```

### Check Edit Workflow
```bash
# Articles with edits
sqlite3 newsai.db "SELECT article_id, title, edit_count, rejected_reason FROM draft_articles WHERE edit_count > 0;"

# Regeneration logs
grep "Regenerating article" outputs/logs/app.log
```

### Check Status Distribution
```bash
sqlite3 newsai.db "SELECT approval_status, COUNT(*) FROM draft_articles GROUP BY approval_status;"
```

---

## Troubleshooting

### Issue: Articles still too short

**Check**:
```bash
wc -w outputs/articles/*.md
```

**Solution**:
- Verify `max_output_tokens=16000` in `story_agent.py`
- Check Gemini API quota
- Review logs for truncation errors

### Issue: Multiple articles in one email

**Check**:
```bash
grep "Approval email sent for article" outputs/logs/app.log
```

**Solution**:
- Verify changes in `blog_pipeline.py`
- Check email sending loop
- Review error logs

### Issue: Edit workflow not working

**Check**:
```bash
grep "Regenerating article" outputs/logs/app.log
```

**Solution**:
- Verify `request_article_edit()` in `approval_service.py`
- Check LLM service initialization
- Review regeneration errors

### Issue: No emails received

**Check**:
```bash
grep "ERROR" outputs/logs/app.log | grep -i email
```

**Solution**:
- Verify SMTP credentials
- Check `APPROVER_EMAILS` in `.env`
- Test SMTP connection manually

---

## Performance Expectations

### Pipeline Timing
- **Crawl + Filter + Group**: 30-60s
- **Story Extraction**: 20-40s per cluster
- **Article Generation**: 30-60s per article (longer due to 1200+ words)
- **Image Generation**: 20-40s per article
- **Email Sending**: < 5s per email

### Resource Usage
- **Memory**: ~500MB-1GB (increased due to longer articles)
- **Disk**: ~10-50MB per article (with images)
- **API Calls**: ~3-5 per article (extraction, generation, validation)

---

## Best Practices

### 1. Review Articles Promptly
- Approval timeout: 48 hours
- Expired articles are auto-archived

### 2. Provide Specific Feedback
When requesting edits:
```
❌ Bad: "Make it better"
✅ Good: "Add more details about fuel efficiency in the Performance section 
         and include a comparison with Honda CB350 in the Comparison section"
```

### 3. Monitor Quality
- Check word count regularly
- Verify SEO structure
- Ensure Indian context (₹ pricing)
- Validate specifications

### 4. Manage Approvals
```bash
# Check pending approvals
sqlite3 newsai.db "SELECT article_id, title, created_at FROM draft_articles WHERE approval_status='pending' ORDER BY created_at;"

# Check expired approvals
sqlite3 newsai.db "SELECT article_id, title, approval_expires_at FROM draft_articles WHERE approval_status='pending' AND approval_expires_at < datetime('now');"
```

---

## API Limits

### Gemini API
- **Rate Limit**: 60 requests/minute
- **Token Limit**: 16000 output tokens per request
- **Daily Quota**: Check Google AI Studio

**Tip**: System includes rate limiting (`CONFIG.Gemini.rate_limit_delay_ms`)

### SMTP
- **Gmail**: 500 emails/day (free), 2000/day (paid)
- **Rate Limit**: ~1 email/second

---

## Backup & Recovery

### Backup Database
```bash
# Daily backup
sqlite3 newsai.db ".backup outputs/backups/newsai_$(date +%Y%m%d).db"

# Restore
cp outputs/backups/newsai_20260422.db newsai.db
```

### Backup Articles
```bash
# Backup articles and images
tar -czf outputs/backups/articles_$(date +%Y%m%d).tar.gz outputs/articles/ outputs/images/
```

---

## Support

### Documentation
- `UPGRADE_SUMMARY.md` - Detailed changes
- `SEO_ARTICLE_REFERENCE.md` - Article structure guide
- `TESTING_GUIDE.md` - Testing procedures
- `AGENT.md` - Technical specification

### Logs
```bash
# View all logs
tail -f outputs/logs/app.log

# Filter by component
grep "story_agent" outputs/logs/app.log
grep "approval_service" outputs/logs/app.log
grep "blog_pipeline" outputs/logs/app.log
```

### Database Queries
```bash
# Article statistics
sqlite3 newsai.db "SELECT 
  approval_status, 
  COUNT(*) as count,
  AVG(edit_count) as avg_edits
FROM draft_articles 
GROUP BY approval_status;"

# Recent activity
sqlite3 newsai.db "SELECT 
  article_id, 
  title, 
  approval_status, 
  created_at 
FROM draft_articles 
ORDER BY created_at DESC 
LIMIT 20;"
```

---

## Next Steps

1. **Test the system**:
   ```bash
   node src/index.js --run-now
   ```

2. **Review generated articles**:
   - Check word count (should be 1200+)
   - Verify SEO structure
   - Confirm Indian context

3. **Test approval workflow**:
   - Approve one article
   - Request edit for another
   - Verify regeneration

4. **Monitor performance**:
   - Check logs for timing
   - Verify email delivery
   - Monitor API usage

5. **Start production**:
   ```bash
   npm start
   ```

---

## Quick Reference

### Commands
```bash
# Run once
node src/index.js --run-now

# Start service
npm start

# Check logs
tail -f outputs/logs/app.log

# Check articles
ls -lh outputs/articles/

# Word count
wc -w outputs/articles/*.md

# Database status
sqlite3 newsai.db "SELECT approval_status, COUNT(*) FROM draft_articles GROUP BY approval_status;"
```

### File Locations
- **Articles**: `outputs/articles/`
- **Images**: `outputs/images/`
- **Logs**: `outputs/logs/app.log`
- **Database**: `newsai.db`
- **Config**: `.env`

### Key Changes
- ✅ One email per article
- ✅ 1200-2000 word articles
- ✅ Full SEO structure
- ✅ Edit regeneration workflow

---

**Version**: 2.0 (Upgraded)  
**Date**: 2026-04-22  
**Status**: ✅ Production Ready
