---
name: search-papers
description: Search for academic papers using Semantic Scholar, OpenReview, and CrossRef. Use when you need to find related work, check novelty, gather citations, download PDFs, or get BibTeX.
argument-hint: "[query or topic]"
allowed-tools: Bash, Read
---

# Academic Paper Search (3-API Stack)

Search query: $ARGUMENTS

Three APIs, each with a clear role:

| API | Role | Auth |
|-----|------|------|
| **Semantic Scholar (S2)** | Search, citation graph, sort by impact | `$S2_API_KEY` header (optional but recommended) |
| **OpenReview** | PDFs, peer reviews, BibTeX for ML venues | None needed for public data |
| **CrossRef** | BibTeX for any paper by DOI | None (use `mailto` for polite pool) |

**Important:** Source `.env` before using S2 with a key:
```bash
set -a; source .env; set +a  # loads S2_API_KEY
```

For detailed API reference with all endpoints and parameters, see [reference.md](reference.md).

---

## Decision Guide: Which API When?

| I want to... | Use |
|--------------|-----|
| Find papers on a topic | S2 keyword search (`/paper/search`) |
| Find most-cited papers | S2 bulk search (`/paper/search/bulk?sort=citationCount:desc`) |
| Look up a specific paper | S2 paper lookup (by ArXiv ID, DOI, or S2 ID) |
| Find exact title match | S2 title match (`/paper/search/match`) |
| Get citation graph | S2 citations + references endpoints |
| Resolve multiple papers at once | S2 batch POST (up to 500 IDs) |
| Download a PDF | OpenReview (`/pdf?id=<note_id>`) |
| Read peer reviews + scores | OpenReview (`/notes?forum=<id>`) |
| Browse a venue's papers | OpenReview (`/notes?content.venueid=...`) |
| Get BibTeX | S2 `citationStyles` field (fastest), or CrossRef via `dx.doi.org` (most reliable) |

---

## Quick Start: Common Workflows

### Literature search (find related work)

```bash
# 1. Relevance-ranked search
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search?query=YOUR+TOPIC&limit=10&fields=title,year,citationCount,abstract,externalIds,citationStyles"

# 2. Most-cited papers on the topic
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search/bulk?query=YOUR+TOPIC&sort=citationCount:desc&fields=title,year,citationCount&limit=10"
```

### Get BibTeX for a paper

```bash
# Option A: From S2 (include citationStyles field — has bibtex key)
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ArXiv:1706.03762?fields=title,citationStyles"

# Option B: From CrossRef via DOI (works for ALL DOI types)
curl -s -L -H "Accept: application/x-bibtex" "https://dx.doi.org/$DOI"
```

### Deep dive on a paper (reviews + PDF)

```bash
# Search OpenReview for the paper
curl -s "https://api2.openreview.net/notes/search?term=PAPER+TITLE&source=forum&limit=1"

# Get reviews (use forum ID from above)
curl -s "https://api2.openreview.net/notes?forum=$FORUM_ID&limit=50"

# Download PDF
curl -s "https://api2.openreview.net/pdf?id=$NOTE_ID" -o paper.pdf
```

### Check novelty

1. S2 keyword search for your exact idea
2. S2 bulk search sorted by citations to find seminal work
3. Check citations/references of the closest papers
4. Search OpenReview for recent ICLR/NeurIPS/ICML submissions

---

## Search Tips

- **Use keyword phrases, not sentences** — S2 natural language queries return 0 results
- **Start broad, then narrow**: "regularization" → "L2 regularization neural networks"
- **Filter by year** for recent work: `&year=2023-`
- **Use minCitationCount** to skip low-impact: `&minCitationCount=50`
- **Multiple searches**: 3-5 queries with different angles for coverage

## Gotchas

- **S2 abstracts** may contain control chars (ESC/0x1b). Strip with: `re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)`
- **S2 openAccessPdf** is often empty — use OpenReview for PDFs
- **S2 `/paper/search`** does NOT support sort — use `/paper/search/bulk` instead
- **S2 `/paper/{id}/citations`** does NOT support sort — newest first only
- **CrossRef `/transform`** fails for arXiv DOIs — always use `dx.doi.org`
- **CrossRef references** unreliable — use S2 for reference lists
- **OpenReview V2** wraps values: `content.title.value`, not `content.title`
- **OpenReview venue IDs** have no trailing slash: `ICLR.cc/2024/Conference`
