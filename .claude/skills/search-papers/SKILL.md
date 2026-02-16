---
name: search-papers
description: Search Semantic Scholar for academic papers. Use when you need to find related work, check novelty, or gather citations.
allowed-tools: Bash, Read
---

# Semantic Scholar API

Call the S2 API directly with `curl`. No wrapper script needed.

## Authentication

```bash
# With API key (1 request/sec, dedicated pool)
curl -s -H "x-api-key: $S2_API_KEY" "https://api.semanticscholar.org/graph/v1/..."

# Without key (shared pool, expect 429s under load)
curl -s "https://api.semanticscholar.org/graph/v1/..."
```

**Rate limits:** 1 request per second with a key. Without a key you share a public pool — back off on 429.

## Endpoints

### 1. Paper Search (keyword)

Find papers by keyword query. Returns up to 100 results per page.

```bash
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search?query=regularization+neural+networks&limit=10&fields=title,authors,venue,year,abstract,citationCount,citationStyles,tldr,openAccessPdf"
```

**Useful parameters:**
- `query` — search terms (URL-encoded, use `+` for spaces)
- `limit` — results per page (default 10, max 100)
- `offset` — pagination offset
- `year` — filter by year range: `2022-2025`, `2023-`, `-2020`
- `fieldsOfStudy` — filter: `Computer Science`, `Mathematics`, etc.
- `fields` — comma-separated list of fields to return (see Fields below)

### 2. Paper Lookup (by ID)

Get details for a specific paper by its Semantic Scholar ID, DOI, ArXiv ID, or other identifier.

```bash
# By Semantic Scholar paper ID
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/649def34f8be52c8b66281af98ae884c09aef38b?fields=title,abstract,authors,citationCount,citationStyles,references"

# By DOI
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/DOI:10.18653/v1/N19-1423?fields=title,abstract,citationCount"

# By ArXiv ID
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ArXiv:1706.03762?fields=title,abstract,citationCount,citationStyles"
```

### 3. Citations (papers that cite a given paper)

```bash
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ArXiv:1706.03762/citations?fields=title,authors,year,citationCount&limit=20"
```

Returns `{ "data": [{ "citingPaper": { ... } }, ...] }`.

### 4. References (papers cited by a given paper)

```bash
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ArXiv:1706.03762/references?fields=title,authors,year,citationCount&limit=20"
```

Returns `{ "data": [{ "citedPaper": { ... } }, ...] }`.

### 5. Snippet Search (keyword search with context snippets)

Returns text snippets from papers matching the query — useful for finding specific claims or results.

```bash
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search?query=dropout+hurts+transformers&limit=5&fields=title,year,citationCount,tldr"
```

Tip: use specific natural-language queries (e.g., "dropout hurts transformer performance") for more targeted results.

### 6. Paper Recommendations

Get papers similar to a given paper.

```bash
# Single-paper recommendations
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/recommendations/v1/papers/forpaper/ArXiv:1706.03762?fields=title,authors,year,citationCount&limit=10"

# Multi-paper recommendations (POST)
curl -s -X POST -H "x-api-key: $S2_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"positivePaperIds": ["ArXiv:1706.03762", "ArXiv:1810.04805"], "negativePaperIds": []}' \
  "https://api.semanticscholar.org/recommendations/v1/papers/?fields=title,authors,year,citationCount&limit=10"
```

## Fields Reference

Request only what you need to minimize response size:

| Field | Description |
|-------|-------------|
| `title` | Paper title |
| `authors` | List of `{authorId, name}` objects |
| `venue` | Publication venue (conference/journal) |
| `year` | Publication year |
| `abstract` | Full abstract |
| `citationCount` | Number of citations |
| `citationStyles` | Contains `bibtex` key with BibTeX entry |
| `fieldsOfStudy` | Research areas (e.g., "Computer Science") |
| `tldr` | AI-generated summary: `{model, text}` |
| `openAccessPdf` | `{url}` to free PDF if available |
| `references` | List of referenced papers |
| `citations` | List of citing papers |

## Error Handling

- **429 Too Many Requests** — Back off 2-5 seconds and retry. Exponential backoff for repeated 429s.
- **404 Not Found** — Paper ID doesn't exist. Check the ID format.
- **400 Bad Request** — Usually a malformed `fields` parameter. Check field names.

Add `-w "\n%{http_code}"` to curl to check status codes:
```bash
curl -s -w "\n%{http_code}" -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1&fields=title"
```

## Search Tips

- **Start broad, then narrow**: "regularization" → "L2 regularization neural networks"
- **Use technical terms**: "contrastive learning" not "comparing things"
- **Check different angles**: Search for the method, the problem, and the application
- **Filter by year** for recent work: `&year=2023-`
- **Multiple searches**: Do 3-5 searches with different queries for comprehensive coverage

## For Citation Collection

1. Search for key topics in your paper (2-3 searches)
2. Search for specific methods you use or compare against
3. Search for datasets you use
4. Include `citationStyles` in fields to get BibTeX entries
5. Clean citation keys: lowercase, no accents, no special characters
6. Parse results with `python3 -c "import sys,json; ..."` for extraction
