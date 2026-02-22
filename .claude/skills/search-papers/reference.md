# API Reference — Academic Paper Search

## 1. Semantic Scholar (S2)

Base URL: `https://api.semanticscholar.org/graph/v1`

### 1a. Keyword Search

Relevance-ranked results. Max 100 per page, 1000 total.

```bash
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search?query=regularization+neural+networks&limit=10&fields=title,authors,venue,year,abstract,citationCount,citationStyles,tldr,openAccessPdf,externalIds"
```

**Parameters:**
- `query` — search terms (URL-encoded, `+` for spaces)
- `limit` — results per page (max 100)
- `offset` — pagination offset
- `year` — year range: `2022-2025`, `2023-`, `-2020`
- `fieldsOfStudy` — filter: `Computer Science`, `Mathematics`, etc.
- `minCitationCount` — only papers with >= N citations
- `fields` — comma-separated fields to return

### 1b. Bulk Search + Sort by Citations

Loses relevance ranking but gains sort control. Token-based pagination.

```bash
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search/bulk?query=saliency+maps&sort=citationCount:desc&fields=title,year,citationCount&limit=20"
```

**Sort options:** `citationCount:desc`, `citationCount:asc`, `publicationDate:desc`, `publicationDate:asc`, `paperId:asc` (default).

### 1c. Title Match

Exact title lookup. Returns `matchScore`.

```bash
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search/match?query=Attention+Is+All+You+Need&fields=title,year,citationCount,externalIds"
```

### 1d. Paper Lookup (by ID)

Supports S2 hash, ArXiv ID, DOI, CorpusId prefixes.

```bash
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ArXiv:1706.03762?fields=title,abstract,authors,citationCount,citationStyles,externalIds"

curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/DOI:10.18653/v1/N19-1423?fields=title,abstract,citationCount"
```

### 1e. Batch Paper Lookup (POST)

Resolve up to 500 IDs in one request.

```bash
curl -s -X POST -H "x-api-key: $S2_API_KEY" -H "Content-Type: application/json" \
  "https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,year,citationCount,externalIds" \
  -d '{"ids": ["ArXiv:1810.03292", "ArXiv:1706.03762", "ArXiv:1810.04805"]}'
```

### 1f. Citations (who cites this paper)

Returns newest first. No sort — sort client-side if needed.

```bash
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ArXiv:1706.03762/citations?fields=title,authors,year,citationCount&limit=20"
```

Response: `{ "data": [{ "citingPaper": { ... } }, ...], "next": <offset> }`

### 1g. References (what does this paper cite)

```bash
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ArXiv:1706.03762/references?fields=title,authors,year,citationCount&limit=20"
```

Response: `{ "data": [{ "citedPaper": { ... } }, ...] }`

### S2 Fields Reference

| Field | Description |
|-------|-------------|
| `title` | Paper title |
| `authors` | List of `{authorId, name}` |
| `venue` | Publication venue |
| `year` | Publication year |
| `abstract` | Full abstract (may contain control chars — strip with `re.sub`) |
| `citationCount` | Number of citations |
| `citationStyles` | Contains `bibtex` key with BibTeX entry |
| `externalIds` | `{ArXiv, DOI, MAG, CorpusId, DBLP}` |
| `tldr` | AI-generated summary: `{model, text}` |
| `openAccessPdf` | `{url}` to free PDF (often empty — use OpenReview instead) |
| `fieldsOfStudy` | Research areas |

### S2 Rate Limits

- **With API key:** 1 req/s dedicated pool. Concurrent bursts (10+) work fine.
- **Without key:** Shared pool, frequent 429s. Unreliable.
- **429** — back off 2-5s and retry
- **404** — paper ID not found
- Check status: add `-w "\nHTTP: %{http_code}"` to curl

---

## 2. OpenAlex

Base URL: `https://api.openalex.org`

Auth: `api_key=$OPENALEX_API_KEY` query parameter. Free tier: $1/day budget. Singleton lookups (single work by ID) are free. List queries cost $0.0001. Search queries cost $0.001.

### 2a. Search Works

```bash
# Full-text search (title + abstract + fulltext)
curl -s "https://api.openalex.org/works?search=neural+architecture+search&filter=publication_year:>2020&sort=cited_by_count:desc&per-page=10&select=id,title,publication_year,cited_by_count,doi,open_access,best_oa_location,authorships&api_key=$OPENALEX_API_KEY"
```

**Parameters:**
- `search` — full-text search across title/abstract/fulltext
- `filter` — filter results (see filter syntax below)
- `sort` — e.g., `cited_by_count:desc`, `publication_year:desc`
- `per-page` — results per page (default 25, max 200)
- `select` — limit returned fields (faster responses)
- `api_key` — your API key

**Common filters:**
- `publication_year:2023` or `publication_year:>2020` or `publication_year:2020-2024`
- `cited_by_count:>100`
- `is_oa:true` — open access only
- `has_doi:true`
- Multiple filters with comma (AND): `publication_year:>2020,is_oa:true`

### 2b. Lookup by DOI

Free (singleton request, no budget cost).

```bash
curl -s "https://api.openalex.org/works/https://doi.org/10.48550/arXiv.1706.03762?select=id,title,doi,open_access,best_oa_location,authorships&api_key=$OPENALEX_API_KEY"
```

### 2c. Get OA PDF Link

The `best_oa_location` field contains the best open access PDF URL:

```json
{
  "best_oa_location": {
    "pdf_url": "https://arxiv.org/pdf/1706.03762",
    "landing_page_url": "https://arxiv.org/abs/1706.03762",
    "source": { "display_name": "arXiv" }
  }
}
```

Download the PDF:
```bash
curl -s -L -o literature/paper_name.pdf "$PDF_URL"
```

### 2d. Batch Lookup by DOIs

Up to 50 DOIs per request using pipe separator:

```bash
curl -s "https://api.openalex.org/works?filter=doi:https://doi.org/10.1234/a|https://doi.org/10.1234/b|https://doi.org/10.1234/c&per-page=50&select=id,title,doi,best_oa_location&api_key=$OPENALEX_API_KEY"
```

### OpenAlex Rate Limits

- Max 100 requests per second
- Daily budget: $1/day (free tier)
  - Singleton (single work by ID): free
  - List request: $0.0001
  - Search request: $0.001
- Budget resets every 24 hours
- Get API key at openalex.org/settings/api

---

## 3. arXiv Direct Download

No API key needed. Works for any paper on arXiv.

### 3a. Download PDF

```bash
mkdir -p literature
curl -s -L -o literature/1706.03762.pdf "https://arxiv.org/pdf/1706.03762"
```

Then read with Claude's `Read` tool:
```
Read(file_path="literature/1706.03762.pdf", pages="1-15")
```

For papers longer than 20 pages, make multiple `Read` calls with different page ranges.

### 3b. Read HTML Version (alternative — text only, no figures)

ar5iv has the broadest coverage (including older papers):
```
WebFetch(url="https://ar5iv.labs.arxiv.org/html/1706.03762", prompt="Extract the methodology and results")
```

arXiv native HTML (recent papers only):
```
WebFetch(url="https://arxiv.org/html/1706.03762v7", prompt="Extract the methodology and results")
```

### arXiv Rate Limits

- Wait at least 3 seconds between consecutive downloads
- No API key needed
- Bulk automated downloads are prohibited — only download papers you actually need to read

---

## 4. OpenReview

Base URL: `https://api2.openreview.net`

No auth needed for public data. Covers ICLR (2013+), NeurIPS (2019+), ICML (2023+), TMLR, workshops.

### 4a. Keyword Search

Elasticsearch-powered fulltext search.

```bash
curl -s "https://api2.openreview.net/notes/search?term=in-context+learning&source=forum&limit=10"
```

**Parameters:**
- `term` — search keywords
- `source` — `forum` (papers), `reply` (reviews/comments), `all`
- `limit` — max results (up to 1000)

Response: `{ "notes": [...], "count": N }`

### 4b. Venue-Specific Query

```bash
curl -s "https://api2.openreview.net/notes?content.venueid=ICLR.cc/2024/Conference&limit=50&select=id,forum,content.title,content.authors,content.abstract,content.venue,content.keywords"
```

Venue IDs: `ICLR.cc/2024/Conference`, `NeurIPS.cc/2024/Conference`, `ICML.cc/2024/Conference` (no trailing slash).

### 4c. Get Reviews

```bash
curl -s "https://api2.openreview.net/notes?forum=$FORUM_ID&limit=50" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for n in d.get('notes', []):
    invs = n.get('invitations', [])
    c = n.get('content', {})
    if any('Official_Review' in i for i in invs):
        rating = c.get('rating', {}).get('value', '?') if isinstance(c.get('rating'), dict) else c.get('rating', '?')
        confidence = c.get('confidence', {}).get('value', '?') if isinstance(c.get('confidence'), dict) else c.get('confidence', '?')
        print(f'Review: rating={rating} confidence={confidence}')
    elif any('Decision' in i for i in invs):
        decision = c.get('decision', {}).get('value', '?') if isinstance(c.get('decision'), dict) else c.get('decision', '?')
        print(f'Decision: {decision}')
"
```

### 4d. Download PDF

```bash
curl -s "https://api2.openreview.net/pdf?id=<NOTE_ID>" -o paper.pdf
```

### 4e. Extract Content Fields

V2 wraps values: `content.title.value`, not `content.title`.

```bash
curl -s "https://api2.openreview.net/notes?content.venueid=ICLR.cc/2024/Conference&limit=1" | python3 -c "
import json, sys
d = json.load(sys.stdin)
n = d['notes'][0]; c = n['content']
print(f'Title: {c[\"title\"][\"value\"]}')
print(f'Authors: {c[\"authors\"][\"value\"]}')
print(f'Venue: {c[\"venue\"][\"value\"]}')
print(f'URL: https://openreview.net/forum?id={n[\"forum\"]}')
"
```

### OpenReview Rate Limits

- No published limits. 5 concurrent requests OK.
- Max 1000 items/request. Use offset for pagination.

---

## 5. CrossRef

### 5a. BibTeX via dx.doi.org

Works for ALL DOI types (arXiv, ACL, ACM, Springer, etc.).

```bash
curl -s -L -H "Accept: application/x-bibtex" "https://dx.doi.org/10.48550/arXiv.1810.03292"
curl -s -L -H "Accept: application/x-bibtex" "https://dx.doi.org/10.18653/v1/N19-1423"
```

**Important:** Use `dx.doi.org`, NOT `api.crossref.org/works/{doi}/transform`.

### 5b. Keyword Search (find DOI by title)

```bash
curl -s "https://api.crossref.org/works?query=attention+is+all+you+need&rows=3&mailto=test@example.com&select=DOI,title,author,is-referenced-by-count"
```

### CrossRef Rate Limits

- `mailto=email` enables polite pool (~50 req/s). 5 concurrent OK.
