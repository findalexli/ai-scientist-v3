---
name: search-papers
description: Search for academic papers using Semantic Scholar, OpenReview, OpenAlex, and CrossRef. Use when you need to find related work, check novelty, gather citations, download/read full papers, or get BibTeX.
argument-hint: "[query or topic]"
---

# Academic Paper Search

Search query: $ARGUMENTS

Four APIs, each with a clear role:

| API | Role | Auth |
|-----|------|------|
| **Semantic Scholar (S2)** | Search, citation graph, sort by impact | `$S2_API_KEY` header (optional but recommended) |
| **OpenAlex** | Expanded search, OA PDF links, metadata | `$OPENALEX_API_KEY` query param (free, $1/day budget) |
| **OpenReview** | Peer reviews, BibTeX for ML venues | None needed for public data |
| **CrossRef** | BibTeX for any paper by DOI | None (use `mailto` for polite pool) |

**Important:** Source `.env` before API calls:
```bash
set -a; source .env; set +a  # loads S2_API_KEY, OPENALEX_API_KEY
```

For detailed API reference with all endpoints and parameters, see [reference.md](reference.md).

---

## Decision Guide: Which API When?

| I want to... | Use |
|--------------|-----|
| Find papers on a topic | S2 keyword search (`/paper/search`) or OpenAlex (`/works?search=...`) |
| Find most-cited papers | S2 bulk search (`/paper/search/bulk?sort=citationCount:desc`) |
| Look up a specific paper | S2 paper lookup (by ArXiv ID, DOI, or S2 ID) |
| Find exact title match | S2 title match (`/paper/search/match`) |
| Get citation graph | S2 citations + references endpoints |
| Resolve multiple papers at once | S2 batch POST (up to 500 IDs) |
| **Read full text of a paper** | **See "Reading Full Papers" below** |
| Read peer reviews + scores | OpenReview (`/notes?forum=<id>`) |
| Browse a venue's papers | OpenReview (`/notes?content.venueid=...`) |
| Get BibTeX | S2 `citationStyles` field (fastest), or CrossRef via `dx.doi.org` (most reliable) |

---

## Reading Full Papers

**You must read the full text of the 3-5 most important papers.** Abstracts alone are not sufficient for understanding methodology, experimental details, or making accurate comparisons.

**Always download papers to `literature/`** and record notes in `literature/README.md`:

```bash
mkdir -p literature
```

Use this priority chain:

### Priority 1: Paper has an arXiv ID → Direct download (free, 100% reliable)

Most ML/AI papers are on arXiv. Check the `externalIds.ArXiv` field from S2 results.

```bash
# Download PDF directly from arXiv
curl -s -L -o literature/1706.03762.pdf "https://arxiv.org/pdf/1706.03762"
```

Then read with the `Read` tool using the `pages` parameter (max 20 pages per call):
```
Read(file_path="literature/1706.03762.pdf", pages="1-15")
```

**Alternative — HTML for quick text extraction** (no figures, but fast):
```
WebFetch(url="https://ar5iv.labs.arxiv.org/html/1706.03762", prompt="Extract the full methodology and results sections")
```

**Rate limit:** Wait 3 seconds between consecutive arXiv downloads.

### Priority 2: Paper has no arXiv ID → OpenAlex OA links (free)

Query OpenAlex for the paper's open access PDF URL:

```bash
# Look up by DOI
curl -s "https://api.openalex.org/works/https://doi.org/10.1234/example?api_key=$OPENALEX_API_KEY&select=id,title,best_oa_location,open_access"
```

The response includes `best_oa_location.pdf_url` — a direct link to the PDF hosted by the publisher, PMC, or a repository. Download it:

```bash
curl -s -L -o literature/paper_name.pdf "$PDF_URL"
```

Then read with the `Read` tool as above.

### Priority 3: No OA PDF available → WebFetch the publisher page

Use `WebFetch` to read the paper directly from the publisher's website:

```
WebFetch(url="https://doi.org/10.1234/example", prompt="Extract the full methodology, experimental setup, and key results")
```

Many publisher pages include the full text in HTML even when the PDF is paywalled. If the publisher page doesn't have full text, try searching for the paper title + "pdf" to find alternative sources.

### After reading each paper

Update `literature/README.md` with the paper's filename, title, and key takeaways. This serves as a persistent index so you (and future sessions) can quickly see what's been read and what was learned.

---

## Quick Start: Common Workflows

### Literature search (find related work)

```bash
# 1. Relevance-ranked search (S2)
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search?query=YOUR+TOPIC&limit=10&fields=title,year,citationCount,abstract,externalIds,citationStyles"

# 2. Most-cited papers on the topic (S2)
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search/bulk?query=YOUR+TOPIC&sort=citationCount:desc&fields=title,year,citationCount&limit=10"

# 3. Search with OpenAlex (broader coverage, includes OA links)
curl -s "https://api.openalex.org/works?search=YOUR+TOPIC&filter=publication_year:>2020&sort=cited_by_count:desc&per-page=10&select=id,title,publication_year,cited_by_count,doi,open_access,best_oa_location&api_key=$OPENALEX_API_KEY"
```

### Get BibTeX for a paper

```bash
# Option A: From S2 (include citationStyles field — has bibtex key)
curl -s -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ArXiv:1706.03762?fields=title,citationStyles"

# Option B: From CrossRef via DOI (works for ALL DOI types)
curl -s -L -H "Accept: application/x-bibtex" "https://dx.doi.org/$DOI"
```

### Deep dive on a paper (reviews + full text)

```bash
# Search OpenReview for the paper
curl -s "https://api2.openreview.net/notes/search?term=PAPER+TITLE&source=forum&limit=1"

# Get reviews (use forum ID from above)
curl -s "https://api2.openreview.net/notes?forum=$FORUM_ID&limit=50"

# Read full text — use arXiv if available (see "Reading Full Papers" above)
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
- **Filter by year** for recent work: `&year=2023-` (S2) or `&filter=publication_year:>2022` (OpenAlex)
- **Use minCitationCount** to skip low-impact: `&minCitationCount=50` (S2) or `&filter=cited_by_count:>50` (OpenAlex)
- **Multiple searches**: 3-5 queries with different angles for coverage
- **Read full text**: After identifying key papers, always download and read them — see "Reading Full Papers"

## Gotchas

- **S2 abstracts** may contain control chars (ESC/0x1b). Strip with: `re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)`
- **S2 openAccessPdf** is often empty — use arXiv direct download or OpenAlex `best_oa_location` instead
- **S2 `/paper/search`** does NOT support sort — use `/paper/search/bulk` instead
- **S2 `/paper/{id}/citations`** does NOT support sort — newest first only
- **CrossRef `/transform`** fails for arXiv DOIs — always use `dx.doi.org`
- **CrossRef references** unreliable — use S2 for reference lists
- **OpenReview V2** wraps values: `content.title.value`, not `content.title`
- **OpenReview venue IDs** have no trailing slash: `ICLR.cc/2024/Conference`
- **arXiv rate limit** — wait 3 seconds between consecutive downloads
- **OpenAlex budget** — $1/day free tier; list queries cost $0.0001, search costs $0.001; singleton lookups are free
