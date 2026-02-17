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

## 2. OpenReview

Base URL: `https://api2.openreview.net`

No auth needed for public data. Covers ICLR (2013+), NeurIPS (2019+), ICML (2023+), TMLR, workshops.

### 2a. Keyword Search

Elasticsearch-powered fulltext search.

```bash
curl -s "https://api2.openreview.net/notes/search?term=in-context+learning&source=forum&limit=10"
```

**Parameters:**
- `term` — search keywords
- `source` — `forum` (papers), `reply` (reviews/comments), `all`
- `limit` — max results (up to 1000)

Response: `{ "notes": [...], "count": N }`

### 2b. Venue-Specific Query

```bash
curl -s "https://api2.openreview.net/notes?content.venueid=ICLR.cc/2024/Conference&limit=50&select=id,forum,content.title,content.authors,content.abstract,content.venue,content.keywords"
```

Venue IDs: `ICLR.cc/2024/Conference`, `NeurIPS.cc/2024/Conference`, `ICML.cc/2024/Conference` (no trailing slash).

### 2c. Get Reviews

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

### 2d. Download PDF

```bash
curl -s "https://api2.openreview.net/pdf?id=<NOTE_ID>" -o paper.pdf
```

### 2e. Extract Content Fields

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

## 3. CrossRef

### 3a. BibTeX via dx.doi.org

Works for ALL DOI types (arXiv, ACL, ACM, Springer, etc.).

```bash
curl -s -L -H "Accept: application/x-bibtex" "https://dx.doi.org/10.48550/arXiv.1810.03292"
curl -s -L -H "Accept: application/x-bibtex" "https://dx.doi.org/10.18653/v1/N19-1423"
```

**Important:** Use `dx.doi.org`, NOT `api.crossref.org/works/{doi}/transform`.

### 3b. Keyword Search (find DOI by title)

```bash
curl -s "https://api.crossref.org/works?query=attention+is+all+you+need&rows=3&mailto=test@example.com&select=DOI,title,author,is-referenced-by-count"
```

### CrossRef Rate Limits

- `mailto=email` enables polite pool (~50 req/s). 5 concurrent OK.
