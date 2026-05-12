# 🧪 Testing Guide - NewsBot Blogs System Upgrade

## Pre-Testing Checklist

- [ ] Environment variables configured (`.env` file)
- [ ] Database initialized (`npm run migrate`)
- [ ] Dependencies installed (`npm install`)
- [ ] SMTP credentials valid
- [ ] Gemini API key active

---

## Test 1: Email Batching Fix

### Objective
Verify each article receives a separate email (not batched).

### Steps
1. Run the pipeline:
   ```bash
   node src/index.js --run-now
   ```

2. Wait for pipeline completion

3. Check your email inbox (approver emails)

### Expected Results
✅ **PASS Criteria**:
- Each article has its own email
- Subject line format: `"Article Review Required: [Article Title]"`
- Each email contains only ONE article
- All emails received within reasonable time

❌ **FAIL Criteria**:
- Multiple articles in one email
- Generic subject lines
- Missing emails

### Verification
```bash
# Check logs
tail -f outputs/logs/app.log | grep "Approval email sent"

# Should see:
# "Approval email sent for article: <article_id_1>"
# "Approval email sent for article: <article_id_2>"
# "Approval email sent for article: <article_id_3>"
```

---

## Test 2: Article Quality & Length

### Objective
Verify articles are 1200-2000 words with proper SEO structure.

### Steps
1. After pipeline run, check generated articles:
   ```bash
   ls -lh outputs/articles/
   ```

2. Open any article:
   ```bash
   cat outputs/articles/[article-slug].md
   ```

3. Count words:
   ```bash
   wc -w outputs/articles/[article-slug].md
   ```

### Expected Results
✅ **PASS Criteria**:
- Word count: 1200-2000 words (minimum 1200)
- Has frontmatter with:
  - `title` (60-70 chars)
  - `meta_description` (150-160 chars)
  - `slug`
  - `tags` (array)
  - `category`
- Article structure includes:
  - Introduction with hook
  - Table of Contents
  - Multiple H2 sections
  - FAQ section
  - Conclusion with verdict
- Indian context (₹ pricing)
- No generic filler content

❌ **FAIL Criteria**:
- Word count < 1200
- Missing required sections
- Just a summary with links
- No SEO metadata

### Verification Script
```bash
# Check word count for all articles
for file in outputs/articles/*.md; do
  echo "File: $file"
  wc -w "$file"
  echo "---"
done

# Check for required sections
grep -E "^## (FAQ|Table of Contents|Conclusion)" outputs/articles/*.md
```

### Manual Review Checklist
- [ ] Title is compelling and keyword-rich
- [ ] Meta description is 150-160 chars
- [ ] Introduction has a hook
- [ ] Table of contents present
- [ ] At least 5 H2 sections
- [ ] FAQ section with 4-6 questions
- [ ] Conclusion with verdict and CTA
- [ ] Proper heading hierarchy (H1 → H2 → H3)
- [ ] Short paragraphs (3-4 lines)
- [ ] Bullet points used appropriately
- [ ] Indian pricing in ₹
- [ ] No hallucinated specs

---

## Test 3: Article Status Tracking

### Objective
Verify article status transitions work correctly.

### Steps
1. Check database after pipeline run:
   ```bash
   sqlite3 newsbot.db "SELECT article_id, title, approval_status, pipeline_stage FROM draft_articles ORDER BY created_at DESC LIMIT 5;"
   ```

2. Expected initial status:
   - `approval_status`: `pending`
   - `pipeline_stage`: `approval_sent`

3. Approve an article via email button

4. Check status again:
   ```bash
   sqlite3 newsbot.db "SELECT article_id, approval_status, approved_by, approved_at FROM draft_articles WHERE article_id='<article_id>';"
   ```

### Expected Results
✅ **PASS Criteria**:
- Initial status: `pending`
- After approval: `approved`
- `approved_by` field populated
- `approved_at` timestamp set

### Status Transition Tests

| Action | Expected Status | Expected Stage |
|--------|----------------|----------------|
| Article generated | `pending` | `draft` |
| Image generated | `pending` | `image_done` |
| Email sent | `pending` | `approval_sent` |
| Approved | `approved` | `approval_sent` |
| Rejected | `rejected` | `approval_sent` |
| Edit requested | `edit_requested` | `approval_sent` |
| After regeneration | `pending` | `approval_sent` |
| Published | `published` | `published` |

---

## Test 4: Edit Request Workflow

### Objective
Verify article regeneration and re-approval workflow.

### Steps
1. Open approval email for any article

2. Click **"REQUEST EDIT"** button

3. Fill in feedback:
   ```
   Email: reviewer@example.com
   Notes: Please add more details about fuel efficiency and make the introduction more engaging.
   ```

4. Submit

5. Check database:
   ```bash
   sqlite3 newsbot.db "SELECT article_id, approval_status, edit_count, rejected_reason FROM draft_articles WHERE article_id='<article_id>';"
   ```

6. Wait for regeneration (check logs):
   ```bash
   tail -f outputs/logs/app.log | grep "Regenerating article"
   ```

7. Check for new approval email

8. Compare old vs new article

### Expected Results
✅ **PASS Criteria**:
- Status changes to `edit_requested` briefly
- `edit_count` increments by 1
- `rejected_reason` contains feedback
- Article is regenerated (content changes)
- Status resets to `pending`
- New approval email sent
- New article addresses feedback

❌ **FAIL Criteria**:
- No regeneration occurs
- Same article content
- No new email sent
- Feedback ignored

### Verification
```bash
# Check edit count
sqlite3 newsbot.db "SELECT article_id, title, edit_count FROM draft_articles WHERE edit_count > 0;"

# Check regeneration logs
grep "Regenerating article" outputs/logs/app.log

# Check re-sent emails
grep "Article.*regenerated and re-sent" outputs/logs/app.log
```

---

## Test 5: SEO Optimization

### Objective
Verify SEO elements are properly implemented.

### Manual Checklist

#### Metadata
- [ ] Title: 60-70 characters
- [ ] Meta description: 150-160 characters
- [ ] Slug: clean, keyword-focused, no special chars
- [ ] Tags: 3-6 relevant keywords

#### Keyword Optimization
- [ ] Primary keyword in title
- [ ] Primary keyword in first paragraph
- [ ] Primary keyword in at least one H2
- [ ] Primary keyword in conclusion
- [ ] Secondary keywords distributed naturally
- [ ] Long-tail variations present (3-5)
- [ ] No keyword stuffing

#### Structure
- [ ] Proper H1 → H2 → H3 hierarchy
- [ ] Table of contents with H2 list
- [ ] FAQ section (4-6 questions)
- [ ] Conclusion with summary + CTA
- [ ] Short paragraphs (3-4 lines max)
- [ ] Bullet points for lists
- [ ] Tables for comparisons/specs

#### Content Quality
- [ ] 1200+ words
- [ ] Clear explanations
- [ ] Data-driven (specs, numbers, dates)
- [ ] Indian context (₹ pricing)
- [ ] Engaging tone
- [ ] No generic filler
- [ ] Real value (examples, insights)

#### Readability
- [ ] Clear introduction with hook
- [ ] Logical section flow
- [ ] Technical terms explained
- [ ] Pros/cons clearly listed
- [ ] Strong conclusion

---

## Test 6: Error Handling

### Objective
Verify system handles errors gracefully.

### Test Cases

#### 6.1: Email Failure
1. Temporarily break SMTP config
2. Run pipeline
3. Check logs for error handling
4. Verify other articles still process

**Expected**: Individual email failures don't stop pipeline

#### 6.2: Gemini API Failure
1. Use invalid API key
2. Run pipeline
3. Check error logs

**Expected**: Clear error message, graceful failure

#### 6.3: Database Error
1. Lock database file
2. Try to update article
3. Check error handling

**Expected**: Error logged, no crash

---

## Test 7: Performance

### Objective
Measure system performance with new longer articles.

### Metrics to Track

```bash
# Run pipeline and time it
time node src/index.js --run-now

# Check logs for timing
grep "took.*s" outputs/logs/app.log
```

### Expected Benchmarks
- Crawl + Grouping: < 60s
- Story processing (per article): 30-60s (longer due to 1200+ words)
- Image generation: 20-40s per article
- Email sending: < 5s per email

### Performance Checklist
- [ ] Pipeline completes without timeout
- [ ] No memory issues
- [ ] Logs show reasonable timing
- [ ] Database queries efficient

---

## Test 8: Integration Test (Full Pipeline)

### Objective
End-to-end test of complete workflow.

### Steps
1. **Start fresh**:
   ```bash
   rm newsbot.db
   npm run migrate
   ```

2. **Run pipeline**:
   ```bash
   node src/index.js --run-now
   ```

3. **Verify stages**:
   - Crawling
   - Filtering
   - Grouping
   - Story extraction
   - Article generation
   - Image generation
   - Email sending

4. **Check outputs**:
   ```bash
   ls -lh outputs/articles/
   ls -lh outputs/images/
   ```

5. **Test approval flow**:
   - Approve one article
   - Reject one article
   - Request edit for one article

6. **Verify publishing**:
   ```bash
   sqlite3 newsbot.db "SELECT article_id, title, approval_status FROM draft_articles WHERE approval_status='published';"
   ```

### Expected Results
✅ **PASS Criteria**:
- All stages complete successfully
- Articles generated (1200+ words)
- Images generated
- Emails sent (one per article)
- Approval actions work
- Edit workflow works
- Publishing succeeds

---

## Debugging Commands

### Check Pipeline Status
```bash
sqlite3 newsbot.db "SELECT run_id, status, created_at FROM job_registry ORDER BY created_at DESC LIMIT 5;"
```

### Check Article Status
```bash
sqlite3 newsbot.db "SELECT article_id, title, approval_status, pipeline_stage, edit_count FROM draft_articles ORDER BY created_at DESC;"
```

### Check Logs
```bash
# All logs
tail -f outputs/logs/app.log

# Email logs only
grep "Approval email" outputs/logs/app.log

# Error logs only
grep "ERROR" outputs/logs/app.log

# Regeneration logs
grep "Regenerating" outputs/logs/app.log
```

### Check Article Word Count
```bash
for file in outputs/articles/*.md; do
  echo "=== $file ==="
  wc -w "$file"
  echo ""
done
```

### Check Email Count
```bash
grep -c "Approval email sent for article" outputs/logs/app.log
```

---

## Rollback Procedure

If tests fail and you need to rollback:

```bash
# 1. Backup current state
cp -r src src.backup
cp -r outputs outputs.backup

# 2. Revert changes
git checkout HEAD -- src/pipeline/blog_pipeline.py
git checkout HEAD -- src/approval/approval_service.py
git checkout HEAD -- src/agents/story_agent.py

# 3. Restart system
npm start
```

---

## Success Criteria Summary

### Critical (Must Pass)
- ✅ Each article gets separate email
- ✅ Articles are 1200+ words
- ✅ Edit workflow regenerates articles
- ✅ No system crashes

### Important (Should Pass)
- ✅ SEO structure complete
- ✅ Status tracking works
- ✅ Performance acceptable
- ✅ Error handling graceful

### Nice to Have
- ✅ All articles high quality
- ✅ Fast pipeline execution
- ✅ Clean logs

---

## Reporting Issues

If you find issues, collect:

1. **Logs**:
   ```bash
   tail -n 500 outputs/logs/app.log > issue_logs.txt
   ```

2. **Database state**:
   ```bash
   sqlite3 newsbot.db ".dump draft_articles" > issue_db.sql
   ```

3. **Sample article**:
   ```bash
   cp outputs/articles/[problematic-article].md issue_article.md
   ```

4. **System info**:
   ```bash
   node --version
   npm --version
   python --version
   ```

---

**Testing Date**: _____________  
**Tester**: _____________  
**Status**: ⬜ Pass | ⬜ Fail | ⬜ Partial
