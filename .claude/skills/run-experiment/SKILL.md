---
name: run-experiment
description: Write and execute experiment code. Use when implementing, debugging, or iterating on experiments. Use proactively during the research phase.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, WebSearch, WebFetch
---

# Experiment Execution

You are implementing and running ML experiments. Use whatever tools, repos, and resources you need.

## Process

1. **Read the idea**: Load `idea.json` (or `idea.md`) to understand what to implement
2. **Research**: Search the web and literature for existing implementations, baselines, datasets
3. **Set up**: Clone repos, install packages (`uv pip install --system`), download datasets — whatever the experiment needs
4. **Implement**: Write experiment code in `experiment_results/`, or adapt code from cloned repos
5. **Run it**: Execute via Bash, watch for errors
6. **Debug if needed**: Read tracebacks, fix issues, re-run
7. **Evaluate results**: Check metrics, look for patterns
8. **Iterate**: Try variations, different hyperparameters, additional datasets
9. **Save results**: Persist metrics in any standard format (`.npy`, `.csv`, `.json`, `.pt`, etc.)

## Environment

- **Package manager**: Use `uv pip install --system` (fast, preferred over pip)
- **Repos**: `git clone` any relevant open-source implementations for baselines or reference
- **Datasets**: HuggingFace `datasets`, Kaggle, UCI ML, OpenML, torchvision, or any public source
- **Frameworks**: Use whatever fits — scikit-learn, PyTorch, JAX, etc.
- **Hardware**: Be self-aware of the current host's capabilities (check GPU availability, RAM, etc.) and design experiments accordingly. Do not assume resources beyond what's available on this machine unless told otherwise

## Code Standards

- **Reproducibility**: Set random seeds, log hyperparameters
- **Print progress**: Show key metrics during execution so the log captures them
- **Timeout awareness**: The container has a finite runtime. Prefer faster iterations over one long run

## When to Stop Experimenting

You decide when experiments are sufficient. Good signals:
- You have baselines AND your method results
- You've done at least one ablation showing which components matter
- Results are stable and consistent
- You have enough data points to make meaningful plots
