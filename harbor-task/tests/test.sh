#!/bin/bash
# Verify the agent produced all required research artifacts,
# copy them to the mounted logs directory, and snapshot dependencies.

SCORE=0
TOTAL=4

# Snapshot Python dependencies for reproducibility and resume
uv pip freeze --system > /app/requirements.txt 2>/dev/null || pip freeze > /app/requirements.txt 2>/dev/null

# Copy artifacts to both mounted dirs (agent for Docker, verifier as backup for Modal)
for dest in /logs/agent/artifacts /logs/verifier/artifacts; do
    mkdir -p "$dest"
    cp -r /app/experiment_results/ "$dest/" 2>/dev/null
    cp -r /app/figures/ "$dest/" 2>/dev/null
    cp /app/latex/template.pdf "$dest/paper.pdf" 2>/dev/null
    cp /app/latex/template.tex "$dest/paper.tex" 2>/dev/null
    cp /app/latex/references.bib "$dest/references.bib" 2>/dev/null
    cp /app/review.json "$dest/" 2>/dev/null
    cp /app/requirements.txt "$dest/requirements.txt" 2>/dev/null
done

# Check experiment results
if [ -d /app/experiment_results ] && [ -n "$(ls /app/experiment_results/*.npy 2>/dev/null)" ]; then
    SCORE=$((SCORE + 1))
    echo "OK: experiment results"
else
    echo "MISSING: experiment results (.npy files)"
fi

# Check plots
if [ -d /app/figures ] && [ -n "$(ls /app/figures/*.png 2>/dev/null)" ]; then
    SCORE=$((SCORE + 1))
    echo "OK: plots"
else
    echo "MISSING: plots (.png files)"
fi

# Check compiled paper
if [ -f /app/latex/template.pdf ]; then
    SCORE=$((SCORE + 1))
    echo "OK: paper"
else
    echo "MISSING: compiled paper (latex/template.pdf)"
fi

# Check review
if [ -f /app/review.json ]; then
    SCORE=$((SCORE + 1))
    echo "OK: review"
else
    echo "MISSING: review.json"
fi

echo ""
echo "Score: $SCORE/$TOTAL"
echo "Dependencies: $(wc -l < /app/requirements.txt 2>/dev/null || echo 0) packages"

# Harbor expects all reward.json values to be numeric
mkdir -p /logs/verifier
if [ "$SCORE" -eq "$TOTAL" ]; then
    echo '{"reward": 1}' > /logs/verifier/reward.json
else
    echo "{\"reward\": 0.$((SCORE * 100 / TOTAL))}" > /logs/verifier/reward.json
fi
