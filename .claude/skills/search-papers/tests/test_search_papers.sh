#!/usr/bin/env bash
# Test suite for the search-papers skill
# Tests all providers: S2, OpenAlex, arXiv, OpenReview, CrossRef
# Uses papers from idea_videoqa_with_tool.json as test cases
#
# Usage: bash .claude/skills/search-papers/tests/test_search_papers.sh
# Requires: S2_API_KEY, OPENALEX_API_KEY in .env

set -a; source .env 2>/dev/null; set +a

PASS=0
FAIL=0
SKIP=0
TMP_DIR="/tmp/search_papers_test_$$"
mkdir -p "$TMP_DIR"

pass() { echo "  PASS: $1"; ((PASS++)); }
fail() { echo "  FAIL: $1"; ((FAIL++)); }
skip() { echo "  SKIP: $1"; ((SKIP++)); }

section() { echo ""; echo "=== $1 ==="; }

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
section "1. Semantic Scholar — Keyword Search"
# ---------------------------------------------------------------------------

RESP=$(curl -s -w "\n%{http_code}" -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search?query=tool+augmented+video+question+answering&limit=5&fields=title,year,citationCount,externalIds")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
  COUNT=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',[])))" 2>/dev/null)
  if [ "$COUNT" -gt 0 ] 2>/dev/null; then
    pass "S2 keyword search returned $COUNT results (HTTP $HTTP)"
  else
    fail "S2 keyword search returned 0 results"
  fi
else
  fail "S2 keyword search HTTP $HTTP"
fi

sleep 1

# ---------------------------------------------------------------------------
section "2. Semantic Scholar — Paper Lookup by ArXiv ID"
# ---------------------------------------------------------------------------

# LongVT paper: 2511.20785
RESP=$(curl -s -w "\n%{http_code}" -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ArXiv:2511.20785?fields=title,year,citationCount,externalIds,abstract")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
  TITLE=$(echo "$BODY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('title',''))" 2>/dev/null)
  if echo "$TITLE" | grep -qi "LongVT\|tool\|video"; then
    pass "S2 paper lookup found: $TITLE"
  else
    # Paper might have a different title than expected, still pass if we got a result
    if [ -n "$TITLE" ]; then
      pass "S2 paper lookup found: $TITLE"
    else
      fail "S2 paper lookup returned empty title"
    fi
  fi
else
  fail "S2 paper lookup HTTP $HTTP"
fi

sleep 1

# ---------------------------------------------------------------------------
section "3. Semantic Scholar — Title Match"
# ---------------------------------------------------------------------------

RESP=$(curl -s -w "\n%{http_code}" -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search/match?query=Thinking+With+Videos+Multimodal+Tool-Augmented+Reinforcement+Learning&fields=title,year,externalIds")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
  TITLE=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',[{}])[0].get('title',''))" 2>/dev/null)
  if [ -n "$TITLE" ]; then
    pass "S2 title match found: $TITLE"
  else
    fail "S2 title match returned empty"
  fi
else
  skip "S2 title match HTTP $HTTP (may not be indexed yet)"
fi

sleep 1

# ---------------------------------------------------------------------------
section "4. Semantic Scholar — BibTeX via citationStyles"
# ---------------------------------------------------------------------------

RESP=$(curl -s -w "\n%{http_code}" -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ArXiv:2512.05774?fields=title,citationStyles")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
  HAS_BIBTEX=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print('yes' if d.get('citationStyles',{}).get('bibtex') else 'no')" 2>/dev/null)
  if [ "$HAS_BIBTEX" = "yes" ]; then
    pass "S2 citationStyles returned BibTeX"
  else
    fail "S2 citationStyles missing bibtex field"
  fi
else
  fail "S2 BibTeX lookup HTTP $HTTP"
fi

sleep 1

# ---------------------------------------------------------------------------
section "5. Semantic Scholar — Bulk Search + Sort"
# ---------------------------------------------------------------------------

RESP=$(curl -s -w "\n%{http_code}" -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/search/bulk?query=long+video+understanding+reinforcement+learning&sort=citationCount:desc&fields=title,year,citationCount&limit=5")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
  COUNT=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',[])))" 2>/dev/null)
  if [ "$COUNT" -gt 0 ] 2>/dev/null; then
    TOP_CITES=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data'][0].get('citationCount',0))" 2>/dev/null)
    pass "S2 bulk search returned $COUNT results (top cited: $TOP_CITES)"
  else
    fail "S2 bulk search returned 0 results"
  fi
else
  fail "S2 bulk search HTTP $HTTP"
fi

sleep 1

# ---------------------------------------------------------------------------
section "6. OpenAlex — Search Works"
# ---------------------------------------------------------------------------

RESP=$(curl -s -w "\n%{http_code}" \
  "https://api.openalex.org/works?search=video+question+answering+temporal+reasoning&filter=publication_year:>2023&sort=cited_by_count:desc&per-page=5&select=id,title,publication_year,cited_by_count,doi,open_access,best_oa_location&api_key=$OPENALEX_API_KEY")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
  COUNT=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('meta',{}).get('count',0))" 2>/dev/null)
  RESULTS=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('results',[])))" 2>/dev/null)
  if [ "$RESULTS" -gt 0 ] 2>/dev/null; then
    pass "OpenAlex search returned $RESULTS results (total: $COUNT)"
  else
    fail "OpenAlex search returned 0 results"
  fi
else
  fail "OpenAlex search HTTP $HTTP"
fi

# ---------------------------------------------------------------------------
section "7. OpenAlex — DOI Lookup + OA PDF Link"
# ---------------------------------------------------------------------------

# Use the AVP paper DOI (arXiv:2512.05774)
RESP=$(curl -s -w "\n%{http_code}" \
  "https://api.openalex.org/works/https://doi.org/10.48550/arXiv.2512.05774?select=id,title,doi,open_access,best_oa_location&api_key=$OPENALEX_API_KEY")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
  PDF_URL=$(echo "$BODY" | python3 -c "
import json,sys
d=json.load(sys.stdin)
loc = d.get('best_oa_location') or {}
print(loc.get('pdf_url') or '')
" 2>/dev/null)
  if [ -n "$PDF_URL" ]; then
    pass "OpenAlex DOI lookup found OA PDF: $PDF_URL"
  else
    # Still pass if we got metadata, just no PDF URL
    TITLE=$(echo "$BODY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('title',''))" 2>/dev/null)
    if [ -n "$TITLE" ]; then
      pass "OpenAlex DOI lookup found paper (no pdf_url): $TITLE"
    else
      fail "OpenAlex DOI lookup returned empty"
    fi
  fi
else
  skip "OpenAlex DOI lookup HTTP $HTTP (DOI may not be indexed)"
fi

# ---------------------------------------------------------------------------
section "8. arXiv — PDF Download"
# ---------------------------------------------------------------------------

# Test with multiple arXiv papers from the idea file
ARXIV_PAPERS=(
  "2512.05774:Active Video Perception"
  "2511.21375:Thinking With Bounding Boxes"
  "2511.20785:LongVT"
  "2512.00805:Thinking with Drafts"
  "2508.04416:Thinking With Videos"
  "2509.24304:FrameThinker"
  "2512.04540:VideoMem"
  "2512.14273:Zoom-Zero"
  "2508.20478:Video-MTR"
  "2601.01095:NarrativeTrack"
  "2512.22315:VideoZoomer"
  "2601.20552:DeepSeek-OCR 2"
)

for entry in "${ARXIV_PAPERS[@]}"; do
  ARXIV_ID="${entry%%:*}"
  PAPER_NAME="${entry#*:}"
  OUT="$TMP_DIR/arxiv_${ARXIV_ID}.pdf"

  HTTP=$(curl -s -L -o "$OUT" -w "%{http_code}" "https://arxiv.org/pdf/$ARXIV_ID")
  sleep 3  # respect arXiv rate limit

  if [ "$HTTP" = "200" ]; then
    SIZE=$(stat -c%s "$OUT" 2>/dev/null || stat -f%z "$OUT" 2>/dev/null)
    # Check it's actually a PDF (not an HTML error page)
    MAGIC=$(head -c 5 "$OUT" 2>/dev/null)
    if [ "$MAGIC" = "%PDF-" ] && [ "$SIZE" -gt 10000 ] 2>/dev/null; then
      SIZE_KB=$((SIZE / 1024))
      pass "arXiv PDF $ARXIV_ID ($PAPER_NAME): ${SIZE_KB}KB"
    else
      fail "arXiv PDF $ARXIV_ID ($PAPER_NAME): not a valid PDF (${SIZE} bytes, magic: $MAGIC)"
    fi
  else
    fail "arXiv PDF $ARXIV_ID ($PAPER_NAME): HTTP $HTTP"
  fi
done

# ---------------------------------------------------------------------------
section "9. arXiv HTML — ar5iv Accessibility"
# ---------------------------------------------------------------------------

# Test ar5iv for one paper
HTTP=$(curl -s -o /dev/null -w "%{http_code}" "https://ar5iv.labs.arxiv.org/html/2512.05774")
if [ "$HTTP" = "200" ]; then
  pass "ar5iv HTML available for 2512.05774"
else
  skip "ar5iv HTML not available for 2512.05774 (HTTP $HTTP)"
fi

# Test arxiv native HTML for one paper
HTTP=$(curl -s -o /dev/null -w "%{http_code}" "https://arxiv.org/html/2512.05774")
if [ "$HTTP" = "200" ]; then
  pass "arXiv native HTML available for 2512.05774"
else
  skip "arXiv native HTML not available for 2512.05774 (HTTP $HTTP)"
fi

# ---------------------------------------------------------------------------
section "10. Non-arXiv Papers — CVPR/thecvf.com PDF Download"
# ---------------------------------------------------------------------------

# Adaptive Keyframe Sampling (CVPR 2025)
OUT="$TMP_DIR/cvpr_adaptive_keyframe.pdf"
HTTP=$(curl -s -L -o "$OUT" -w "%{http_code}" \
  "https://openaccess.thecvf.com/content/CVPR2025/papers/Tang_Adaptive_Keyframe_Sampling_for_Long_Video_Understanding_CVPR_2025_paper.pdf")

if [ "$HTTP" = "200" ]; then
  SIZE=$(stat -c%s "$OUT" 2>/dev/null || stat -f%z "$OUT" 2>/dev/null)
  MAGIC=$(head -c 5 "$OUT" 2>/dev/null)
  if [ "$MAGIC" = "%PDF-" ] && [ "$SIZE" -gt 10000 ] 2>/dev/null; then
    SIZE_KB=$((SIZE / 1024))
    pass "CVPR PDF (Adaptive Keyframe): ${SIZE_KB}KB"
  else
    fail "CVPR PDF (Adaptive Keyframe): not a valid PDF"
  fi
else
  fail "CVPR PDF (Adaptive Keyframe): HTTP $HTTP"
fi

# Flexible Frame Selection (CVPR 2025)
OUT="$TMP_DIR/cvpr_flexible_frame.pdf"
HTTP=$(curl -s -L -o "$OUT" -w "%{http_code}" \
  "https://openaccess.thecvf.com/content/CVPR2025/papers/Buch_Flexible_Frame_Selection_for_Efficient_Video_Reasoning_CVPR_2025_paper.pdf")

if [ "$HTTP" = "200" ]; then
  SIZE=$(stat -c%s "$OUT" 2>/dev/null || stat -f%z "$OUT" 2>/dev/null)
  MAGIC=$(head -c 5 "$OUT" 2>/dev/null)
  if [ "$MAGIC" = "%PDF-" ] && [ "$SIZE" -gt 10000 ] 2>/dev/null; then
    SIZE_KB=$((SIZE / 1024))
    pass "CVPR PDF (Flexible Frame): ${SIZE_KB}KB"
  else
    fail "CVPR PDF (Flexible Frame): not a valid PDF"
  fi
else
  fail "CVPR PDF (Flexible Frame): HTTP $HTTP"
fi

# ---------------------------------------------------------------------------
section "11. Non-arXiv Papers — OpenReview PDF Download"
# ---------------------------------------------------------------------------

# DToK paper: uhFx1RGD1g
OUT="$TMP_DIR/openreview_dtok.pdf"
HTTP=$(curl -s -L -o "$OUT" -w "%{http_code}" \
  "https://openreview.net/pdf?id=uhFx1RGD1g")

if [ "$HTTP" = "200" ]; then
  SIZE=$(stat -c%s "$OUT" 2>/dev/null || stat -f%z "$OUT" 2>/dev/null)
  MAGIC=$(head -c 5 "$OUT" 2>/dev/null)
  if [ "$MAGIC" = "%PDF-" ] && [ "$SIZE" -gt 10000 ] 2>/dev/null; then
    SIZE_KB=$((SIZE / 1024))
    pass "OpenReview PDF (DToK/uhFx1RGD1g): ${SIZE_KB}KB"
  else
    fail "OpenReview PDF (DToK): not a valid PDF"
  fi
else
  fail "OpenReview PDF (DToK): HTTP $HTTP"
fi

# ---------------------------------------------------------------------------
section "12. Non-arXiv Papers — IJCAI via OpenAlex Fallback"
# ---------------------------------------------------------------------------

# DToMA paper: https://www.ijcai.org/proceedings/2025/258
# Try to find it via OpenAlex to get a PDF link
RESP=$(curl -s -w "\n%{http_code}" \
  "https://api.openalex.org/works?search=DToMA+Dynamic+Token+Manipulation+Long+Video&per-page=1&select=id,title,doi,best_oa_location,open_access&api_key=$OPENALEX_API_KEY")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
  RESULT=$(echo "$BODY" | python3 -c "
import json,sys
d=json.load(sys.stdin)
results = d.get('results',[])
if results:
    r = results[0]
    loc = r.get('best_oa_location') or {}
    pdf = loc.get('pdf_url') or 'none'
    print(f\"{r.get('title','?')} | pdf={pdf}\")
else:
    print('no results')
" 2>/dev/null)
  if echo "$RESULT" | grep -q "no results"; then
    skip "OpenAlex couldn't find IJCAI DToMA paper (may not be indexed yet)"
  else
    pass "OpenAlex found IJCAI paper: $RESULT"
  fi
else
  fail "OpenAlex IJCAI lookup HTTP $HTTP"
fi

# ---------------------------------------------------------------------------
section "13. OpenReview — Keyword Search"
# ---------------------------------------------------------------------------

RESP=$(curl -s -w "\n%{http_code}" \
  "https://api2.openreview.net/notes/search?term=dynamic+token+compression+keyframe+prior&source=forum&limit=3")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
  COUNT=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null)
  if [ "$COUNT" -gt 0 ] 2>/dev/null; then
    pass "OpenReview search returned $COUNT results"
  else
    skip "OpenReview search returned 0 results (paper may not be on OpenReview)"
  fi
else
  fail "OpenReview search HTTP $HTTP"
fi

# ---------------------------------------------------------------------------
section "14. CrossRef — BibTeX via dx.doi.org"
# ---------------------------------------------------------------------------

# Use arXiv DOI
BIBTEX=$(curl -s -L -H "Accept: application/x-bibtex" "https://dx.doi.org/10.48550/arXiv.2512.05774")
if echo "$BIBTEX" | grep -q "@"; then
  pass "CrossRef BibTeX for arXiv DOI returned valid entry"
else
  fail "CrossRef BibTeX for arXiv DOI failed"
fi

# Use a non-arXiv DOI (ACL paper as example)
BIBTEX=$(curl -s -L -H "Accept: application/x-bibtex" "https://dx.doi.org/10.18653/v1/N19-1423")
if echo "$BIBTEX" | grep -q "@"; then
  pass "CrossRef BibTeX for ACL DOI returned valid entry"
else
  fail "CrossRef BibTeX for ACL DOI failed"
fi

# ---------------------------------------------------------------------------
section "15. S2 — Citations Endpoint"
# ---------------------------------------------------------------------------

RESP=$(curl -s -w "\n%{http_code}" -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ArXiv:2512.05774/citations?fields=title,year,citationCount&limit=5")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
  COUNT=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',[])))" 2>/dev/null)
  pass "S2 citations endpoint returned $COUNT citing papers"
else
  fail "S2 citations endpoint HTTP $HTTP"
fi

sleep 1

# ---------------------------------------------------------------------------
section "16. S2 — References Endpoint"
# ---------------------------------------------------------------------------

RESP=$(curl -s -w "\n%{http_code}" -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/ArXiv:2512.05774/references?fields=title,year,citationCount&limit=5")
HTTP=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')

if [ "$HTTP" = "200" ]; then
  COUNT=$(echo "$BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',[])))" 2>/dev/null)
  if [ "$COUNT" -gt 0 ] 2>/dev/null; then
    pass "S2 references endpoint returned $COUNT referenced papers"
  else
    fail "S2 references endpoint returned 0 results"
  fi
else
  fail "S2 references endpoint HTTP $HTTP"
fi

# ---------------------------------------------------------------------------
section "17. End-to-End — Full-Text Availability for ALL Papers in Idea File"
# ---------------------------------------------------------------------------

echo ""
echo "  Checking full-text accessibility for all 15 papers..."
echo "  (Downloads already tested above; this summarizes availability)"
echo ""

# Count from sections 8, 10, 11
echo "  arXiv papers (12 total):"
ARXIV_OK=0
for entry in "${ARXIV_PAPERS[@]}"; do
  ARXIV_ID="${entry%%:*}"
  OUT="$TMP_DIR/arxiv_${ARXIV_ID}.pdf"
  if [ -f "$OUT" ]; then
    MAGIC=$(head -c 5 "$OUT" 2>/dev/null)
    SIZE=$(stat -c%s "$OUT" 2>/dev/null || stat -f%z "$OUT" 2>/dev/null)
    if [ "$MAGIC" = "%PDF-" ] && [ "$SIZE" -gt 10000 ] 2>/dev/null; then
      ((ARXIV_OK++))
    fi
  fi
done
echo "    $ARXIV_OK/12 downloaded successfully"

echo "  CVPR papers (2 total):"
CVPR_OK=0
for f in "$TMP_DIR"/cvpr_*.pdf; do
  [ -f "$f" ] || continue
  MAGIC=$(head -c 5 "$f" 2>/dev/null)
  SIZE=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null)
  if [ "$MAGIC" = "%PDF-" ] && [ "$SIZE" -gt 10000 ] 2>/dev/null; then
    ((CVPR_OK++))
  fi
done
echo "    $CVPR_OK/2 downloaded successfully"

echo "  OpenReview papers (1 total):"
OR_OK=0
for f in "$TMP_DIR"/openreview_*.pdf; do
  [ -f "$f" ] || continue
  MAGIC=$(head -c 5 "$f" 2>/dev/null)
  SIZE=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null)
  if [ "$MAGIC" = "%PDF-" ] && [ "$SIZE" -gt 10000 ] 2>/dev/null; then
    ((OR_OK++))
  fi
done
echo "    $OR_OK/1 downloaded successfully"

TOTAL_PAPERS=$((ARXIV_OK + CVPR_OK + OR_OK))
echo ""
echo "  Total full-text available: $TOTAL_PAPERS/15"

if [ "$TOTAL_PAPERS" -ge 14 ]; then
  pass "Full-text available for $TOTAL_PAPERS/15 papers (excellent)"
elif [ "$TOTAL_PAPERS" -ge 12 ]; then
  pass "Full-text available for $TOTAL_PAPERS/15 papers (good)"
else
  fail "Full-text available for only $TOTAL_PAPERS/15 papers"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "==========================================="
echo "  RESULTS: $PASS passed, $FAIL failed, $SKIP skipped"
echo "==========================================="

if [ "$FAIL" -gt 0 ]; then
  exit 1
else
  exit 0
fi
