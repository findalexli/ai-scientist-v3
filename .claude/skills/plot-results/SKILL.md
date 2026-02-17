---
name: plot-results
description: Generate publication-quality plots from experiment results. Use after experiments are complete and before writing the paper.
allowed-tools: Bash, Read, Write, Edit, Glob
---

# Publication Plot Generation

Generate professional, publication-quality plots from experiment results.

## Process

1. **Find results**: Look for `.npy` files in `experiment_results/`
2. **Plan plots**: Decide what visualizations best tell the story
3. **Write aggregator script**: Create `auto_plot_aggregator.py` that reads all results and generates plots
4. **Run it**: Execute the script, check output in `figures/`
5. **Review visually**: Use the `Read` tool on each generated PNG file to visually inspect it. Claude Code is multimodal and can see images directly. Check for:
   - Correct data rendering (values match expected results)
   - Readable labels, legends, and titles
   - Appropriate styling and color choices
   - No overlapping text, clipped elements, or layout issues
6. **Iterate**: Fix issues found during visual review, re-run the script, and inspect again until all plots meet publication quality

## Plot Standards

- **Professional styling**: Use clean matplotlib with appropriate font sizes
- **Informative labels**: Axis labels, legends, titles that a reader can understand
- **No underscores in labels**: Replace `_` with spaces in all display text
- **Color scheme**: Use colorblind-friendly palettes (e.g., seaborn defaults)
- **Error bars**: Include them when you have multiple seeds
- **Combine related plots**: Use subplots (up to 3 per figure) for related comparisons
- **Max 12 figures**: Keep the total manageable (4-6 in main paper, rest in appendix)
- **File format**: Save as PNG at 150+ DPI

## Output

Save all plots to `figures/` directory:
```
figures/
├── main_comparison.png          # Key result comparison
├── dataset_performance.png      # Performance across datasets
├── ablation_study.png           # Component ablation
├── training_curves.png          # Learning dynamics
└── ...
```

## Aggregator Script Template

Write `auto_plot_aggregator.py`:
```python
import numpy as np
import matplotlib.pyplot as plt
import os

os.makedirs('figures', exist_ok=True)

# Load results
baseline = np.load('experiment_results/baseline_results.npy', allow_pickle=True).item()
main = np.load('experiment_results/main_results.npy', allow_pickle=True).item()

# Create plots...
plt.figure(figsize=(8, 5))
# ...
plt.savefig('figures/main_comparison.png', dpi=150, bbox_inches='tight')
plt.close()
```

## Common Plot Types

- **Bar charts**: Comparing methods across datasets
- **Line plots**: Training curves, learning dynamics
- **Heatmaps**: Hyperparameter sensitivity
- **Box plots**: Distribution of results across seeds
- **Ablation tables**: Can be visualized as grouped bar charts
