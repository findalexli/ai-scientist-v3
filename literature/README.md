# Literature Review: Multi-User-Turn-CodeBench

**Project:** Benchmark for multi-turn coding agent evaluation using real user sessions from Data Claw (real Claude Code interactions). Core metrics: **turns-to-acceptance** and **intent gap**.

**Date:** 2026-03-06

---

## Index of Downloaded Papers

| Filename | Title | Year | Citations | ArXiv |
|---|---|---|---|---|
| `swebench_2310.06770.pdf` | SWE-bench: Can Language Models Resolve Real-World GitHub Issues? | 2023 | 1612 | 2310.06770 |
| `swe_agent_2405.15793.pdf` | SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering | 2024 | 774 | 2405.15793 |
| `intercode_2306.14898.pdf` | InterCode: Standardizing and Benchmarking Interactive Coding with Execution Feedback | 2023 | 182 | 2306.14898 |
| `interactive_tdd_2208.05950.pdf` | Interactive Code Generation via Test-Driven User-Intent Formalization | 2022 | 88 | 2208.05950 |
| `llm_tdd_2404.10100.pdf` | LLM-Based Test-Driven Interactive Code Generation: User Study and Empirical Evaluation | 2024 | 92 | 2404.10100 |
| `ambig_swe_2502.13069.pdf` | Ambig-SWE: Interactive Agents to Overcome Underspecificity in Software Engineering | 2025 | 16 | 2502.13069 |
| `convcodewold_2502.19852.pdf` | ConvCodeWorld: Benchmarking Conversational Code Generation in Reproducible Feedback Environments | 2025 | 13 | 2502.19852 |
| `taubench_2406.12045.pdf` | tau-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains | 2024 | ~80 | 2406.12045 |
| `webarena_2307.13854.pdf` | WebArena: A Realistic Web Environment for Building Autonomous Agents | 2023 | 974 | 2307.13854 |
| `user_sim_tod_2105.03748.pdf` | Simulating User Satisfaction for the Evaluation of Task-oriented Dialogue Systems | 2021 | 72 | 2105.03748 |
| `why_agents_need_you_2506.12347.pdf` | Why AI Agents Still Need You: Findings from Developer-Agent Collaborations in the Wild | 2025 | 5 | 2506.12347 |

---

## Detailed Paper Notes

---

### 1. SWE-bench: Can Language Models Resolve Real-World GitHub Issues?

**File:** `swebench_2310.06770.pdf`
**Year:** 2023 | **Citations:** 1612 | **ArXiv:** 2310.06770

**Methodology Summary:**
SWE-bench constructs 2,294 tasks from real GitHub issues across 12 popular Python repositories, filtered from ~90,000 pull requests through a three-stage pipeline. Each task is presented as a single-shot query: given a codebase snapshot and an issue description, produce a patch file. Success is measured as a binary pass/fail: whether "fail-to-pass" tests (validating the fix) and "pass-to-pass" tests (regressions) all pass after applying the model-generated patch. There is no multi-turn interaction—the model generates one patch per task.

**Key Results:**
- Claude 2 resolves 4.8% (oracle retrieval) / 1.96% (realistic BM25 retrieval)
- GPT-4 resolves 1.7%; all single-shot approaches perform poorly
- Modern agents (SWE-agent, Agentless) now reach 30–50% on SWE-bench Verified

**Relevance to multi-user-turn-codebench:**
SWE-bench is the canonical benchmark we must position against. Its single-turn, pass/fail design is precisely the gap we fill. SWE-bench measures agent capability on a fixed, fully-specified task with execution-based oracle—it cannot measure how many corrections users need, how agents handle ambiguity, or how close they get before acceptance. Our benchmark captures the correction trajectory.

**BibTeX:**
```bibtex
@misc{jimenez2023swebench,
  doi = {10.48550/ARXIV.2310.06770},
  url = {https://arxiv.org/abs/2310.06770},
  author = {Jimenez, Carlos E. and Yang, John and Wettig, Alexander and Yao, Shunyu and Pei, Kexin and Press, Ofir and Narasimhan, Karthik},
  title = {SWE-bench: Can Language Models Resolve Real-World GitHub Issues?},
  publisher = {arXiv},
  year = {2023}
}
```

---

### 2. SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering

**File:** `swe_agent_2405.15793.pdf`
**Year:** 2024 | **Citations:** 774 | **ArXiv:** 2405.15793

**Methodology Summary:**
SWE-agent introduces the Agent-Computer Interface (ACI) abstraction, arguing that LM agents need purpose-built interfaces just as human engineers benefit from IDEs. The ACI provides specialized search/navigation commands, a file viewer with scrolling, a file editor with syntax checking guardrails, and context management. The agent operates in a loop: at each step it generates a thought and a command, then receives concise, informative feedback. It is evaluated on SWE-bench (single-turn pass/fail) and HumanEvalFix.

**Key Results:**
- GPT-4 Turbo + SWE-agent: 12.47% on SWE-bench (vs. 3.8% baseline)
- Claude 3 Opus + SWE-agent: 10.5% on SWE-bench
- ACI ablations show 10.7 pp gain over raw Linux shell on SWE-bench Lite

**Relevance to multi-user-turn-codebench:**
SWE-agent demonstrates that agent-environment interface design dramatically affects performance on single-turn benchmarks. Our benchmark should capture whether agents with better ACIs also require fewer correction turns from users. The multi-turn trajectory data from our benchmark could inform future ACI design. SWE-agent also shows that execution feedback is essential—our benchmark's use of real execution environments aligns with this finding.

**BibTeX:**
```bibtex
@misc{yang2024sweagent,
  doi = {10.48550/ARXIV.2405.15793},
  url = {https://arxiv.org/abs/2405.15793},
  author = {Yang, John and Jimenez, Carlos E. and Wettig, Alexander and Lieret, Kilian and Yao, Shunyu and Narasimhan, Karthik and Press, Ofir},
  title = {SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering},
  publisher = {arXiv},
  year = {2024}
}
```

---

### 3. InterCode: Standardizing and Benchmarking Interactive Coding with Execution Feedback

**File:** `intercode_2306.14898.pdf`
**Year:** 2023 | **Citations:** 182 | **ArXiv:** 2306.14898

**Methodology Summary:**
InterCode is the first framework to treat code generation natively as an interactive reinforcement learning (RL) problem, with code actions and execution feedback as observations. It uses Docker containers for safe, reproducible execution and provides Bash, SQL, and Python task environments built on existing static datasets (NL2Bash, Spider, MBPP). Agents interact in episodes with up to n=10 turns; success is binary (0/1) at the episode level. It compares "Single Turn" (one-shot) against "Try Again" (multi-turn with execution feedback) settings.

**Key Results:**
- GPT-4 on InterCode-SQL: 9.1% (single turn) → 73.7% (Try Again, 10 turns)—a 8x improvement
- GPT-4 on InterCode-Bash: 34.0% (single turn) → 51.7% (Try Again, 10 turns)
- GPT-3.5 showed similar gains; models use later turns for context discovery, error correction, and modular problem solving
- Plateauing in success at later turns due to context accumulation

**Relevance to multi-user-turn-codebench:**
InterCode is the closest predecessor to our work in multi-turn coding evaluation, but it evaluates agent-environment interaction (execution feedback from a machine), not agent-user interaction (natural language correction turns from humans). It does not model the gap between user intent and agent output, user satisfaction, or session acceptance. Our benchmark fills this gap by using real user correction sessions.

**BibTeX:**
```bibtex
@misc{yang2023intercode,
  doi = {10.48550/ARXIV.2306.14898},
  url = {https://arxiv.org/abs/2306.14898},
  author = {Yang, John and Prabhakar, Akshara and Narasimhan, Karthik and Yao, Shunyu},
  title = {InterCode: Standardizing and Benchmarking Interactive Coding with Execution Feedback},
  publisher = {arXiv},
  year = {2023}
}
```

---

### 4. Interactive Code Generation via Test-Driven User-Intent Formalization

**File:** `interactive_tdd_2208.05950.pdf`
**Year:** 2022 | **Citations:** 88 | **ArXiv:** 2208.05950

**Methodology Summary:**
TiCoder proposes formalizing ambiguous user intent through generated tests rather than natural language. The system generates candidate code and tests, then queries users with concrete "does `function(input)` return `expected_output`?" questions (Yes/No/Undefined). User responses prune the code hypothesis space. Discriminative test ranking maximizes information gain per query. Evaluated on MBPP and HumanEval using reference implementations as oracle users. Metric: `pass@k@m` (code accuracy after m user queries).

**Key Results:**
- MBPP: pass@1@1 improved from 48.24% to 70.73% (+22.5 pp); pass@1@5 = 85.94% (+37.7 pp)
- HumanEval: pass@1@1 from 30.49% to 55.28% (+24.8 pp); pass@1@5 = 84.47% (+54.0 pp)
- Average ~1.7 queries per task (MBPP) and ~1.5 (HumanEval) to reach accepted test
- Test ranking is the most critical component

**Relevance to multi-user-turn-codebench:**
TiCoder formalizes user-intent via test queries—a specific, structured form of interaction. Our benchmark captures the broader, naturalistic case where users provide free-form corrections, not structured Yes/No to generated tests. The `pass@k@m` metric (performance as a function of interaction rounds) directly inspires our "turns-to-acceptance" metric. The use of reference implementations as oracle users is a methodological pattern we can adapt.

**BibTeX:**
```bibtex
@misc{lahiri2022interactive,
  doi = {10.48550/ARXIV.2208.05950},
  url = {https://arxiv.org/abs/2208.05950},
  author = {Lahiri, Shuvendu K. and Fakhoury, Sarah and Naik, Aaditya and Sakkas, Georgios and Chakraborty, Saikat and Musuvathi, Madanlal and Choudhury, Piali and von Veh, Curtis and Inala, Jeevana Priya and Wang, Chenglong and Gao, Jianfeng},
  title = {Interactive Code Generation via Test-Driven User-Intent Formalization},
  publisher = {arXiv},
  year = {2022}
}
```

---

### 5. LLM-Based Test-Driven Interactive Code Generation: User Study and Empirical Evaluation

**File:** `llm_tdd_2404.10100.pdf`
**Year:** 2024 | **Citations:** 92 | **ArXiv:** 2404.10100

**Methodology Summary:**
This is the user study follow-up to TiCoder (above), validating that test-driven interactive code generation works with real human participants. 15 programmers (8 industry professionals, 7 academic researchers) evaluated 3 code tasks using three conditions: (1) random code suggestions, (2) TiCoder with Pass/Fail test responses, (3) TiCoder with explicit Output responses. Within-subject design, ~45-minute sessions, with correctness, time, and NASA TLX cognitive load measured. Also includes a large-scale benchmark comparison across 4 LLMs on MBPP and HumanEval.

**Key Results:**
- Correctness: 0.40 (control) → 0.84 (TiCoder-PassFail, p=0.001) → 0.64 (TiCoder-Output)
- Cognitive load significantly reduced with TiCoder; time overhead not significant
- Across 4 LLMs: average +38.43% absolute improvement in code accuracy within 5 user interactions
- TiCoder-Output achieves the best benchmark accuracy; TiCoder-PassFail wins the user study

**Relevance to multi-user-turn-codebench:**
The user study shows that structured interaction (test-driven) dramatically improves correctness and reduces cognitive load vs. unstructured code browsing. Our benchmark uses real unstructured correction sessions, capturing the naturalistic analog. We can borrow the correctness/cognitive-load framing: our "turns-to-acceptance" metric parallels their "interactions-to-correct-code" measure. The gap between simulated and real user behavior (oracle vs. actual users) motivates using real session data.

**BibTeX:**
```bibtex
@article{fakhoury2024llmtdd,
  doi = {10.48550/ARXIV.2404.10100},
  url = {https://arxiv.org/abs/2404.10100},
  author = {Fakhoury, Sarah and Naik, Aaditya and Sakkas, Georgios and Chakraborty, Saikat and Lahiri, Shuvendu K.},
  title = {LLM-Based Test-Driven Interactive Code Generation: User Study and Empirical Evaluation},
  publisher = {arXiv},
  year = {2024}
}
```

---

### 6. Ambig-SWE: Interactive Agents to Overcome Underspecificity in Software Engineering

**File:** `ambig_swe_2502.13069.pdf`
**Year:** 2025 | **Citations:** 16 | **ArXiv:** 2502.13069

**Methodology Summary:**
Ambig-SWE operationalizes underspecificity in SWE-bench tasks by using GPT-4o to generate shortened summaries of full GitHub issues (preserving terminology but reducing detail). Agents are evaluated in three settings: (1) Hidden (only summary, no interaction), (2) Interaction (summary + access to GPT-4o proxy user with full issue knowledge), (3) Full (complete issue text). The proxy user can only answer questions using information from the original issue or say "I don't have that information." Metrics include resolve rate, cosine embedding distance, LLM-as-judge specificity scores (1–5), and question patterns.

**Key Results:**
- Interaction improves performance by up to 74% over Hidden setting
- Proprietary models (Claude Sonnet/Haiku) reach ~80% of Full-setting performance via interaction; open-weight models only 54–59%
- Only Claude Sonnet 3.5 reliably detects ambiguity (84% accuracy); others default to non-interactive behavior
- Claude models ask balanced context-aware questions; Llama 3.1 generates generic templated questions

**Relevance to multi-user-turn-codebench:**
Ambig-SWE is directly relevant as the closest existing work to our project. It studies the underspecification gap in SWE tasks and measures how interaction resolves it. Key differences: (1) Ambig-SWE uses synthetically constructed underspecified tasks; we use real user sessions where intent gap is naturally present. (2) Ambig-SWE evaluates the agent's ability to ask clarifying questions; our benchmark evaluates the full correction trajectory with user-side acceptance. (3) Ambig-SWE doesn't measure turns-to-acceptance. We position our benchmark as providing the naturalistic complement to Ambig-SWE's controlled study.

**BibTeX:**
```bibtex
@misc{vijayvargiya2025ambigswe,
  doi = {10.48550/ARXIV.2502.13069},
  url = {https://arxiv.org/abs/2502.13069},
  author = {Vijayvargiya, Sanidhya and Zhou, Xuhui and Yerukola, Akhila and Sap, Maarten and Neubig, Graham},
  title = {Ambig-SWE: Interactive Agents to Overcome Underspecificity in Software Engineering},
  publisher = {arXiv},
  year = {2025}
}
```

---

### 7. ConvCodeWorld: Benchmarking Conversational Code Generation in Reproducible Feedback Environments

**File:** `convcodewold_2502.19852.pdf`
**Year:** 2025 | **Citations:** 13 | **ArXiv:** 2502.19852

**Methodology Summary:**
ConvCodeWorld formalizes conversational code generation as iterative refinement with a structured feedback taxonomy. At each turn t, the model generates code given prior history and feedback type Ω_t. Feedback types include: compilation feedback (syntax/type errors, always present), partial execution feedback (limited test coverage), full execution feedback (complete test suite), novice verbal feedback (GPT-4o, restates errors), and expert verbal feedback (GPT-4o, provides guided diagnosis). Nine distinct feedback scenarios are studied. Metrics: Mean Reciprocal Rank (MRR, efficiency) and Recall (coverage over n=10 turns).

**Key Results:**
- Expert verbal feedback enables weaker models to surpass state-of-the-art single-turn models
- Strong tension between MRR (efficiency) and Recall (coverage): fast solvers have lower overall rates
- Models trained on one feedback type struggle to generalize to unseen feedback combinations
- Novice feedback provides limited improvement over compilation-only feedback

**Relevance to multi-user-turn-codebench:**
ConvCodeWorld is the most recent direct predecessor. It systematically studies feedback type effects on multi-turn code generation. Key gap vs. our work: (1) Feedback is synthetic and controlled—our benchmark uses real user utterances. (2) ConvCodeWorld uses standardized algorithmic problems (HumanEval-style); our tasks come from real production coding sessions (open-ended, repository-level). (3) The user in ConvCodeWorld is a GPT-4o oracle; our "user" is the actual developer whose session we replay. MRR is directly analogous to our "turns-to-acceptance" metric—we can borrow this framing.

**BibTeX:**
```bibtex
@misc{han2025convcodewrold,
  doi = {10.48550/ARXIV.2502.19852},
  url = {https://arxiv.org/abs/2502.19852},
  author = {Han, Hojae and Hwang, Seung-won and Samdani, Rajhans and He, Yuxiong},
  title = {ConvCodeWorld: Benchmarking Conversational Code Generation in Reproducible Feedback Environments},
  publisher = {arXiv},
  year = {2025}
}
```

---

### 8. tau-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains

**File:** `taubench_2406.12045.pdf`
**Year:** 2024 | **Citations:** ~80 | **ArXiv:** 2406.12045

**Methodology Summary:**
tau-bench frames agent evaluation as a POMDP where an LM agent interacts with both database APIs (tools) and a simulated user (LM-powered) to complete customer service tasks across two domains: retail and airline. Users are simulated using GPT-4-0613 with detailed scenario instructions; the agent must gather information via multi-turn dialogue. Evaluation compares database end-state against annotated goal state (objective, execution-grounded). Introduces the `pass^k` metric: fraction of k i.i.d. trials where the agent succeeds, measuring reliability/consistency. Agent cannot see the API interaction history; user cannot see API calls.

**Key Results:**
- GPT-4o achieves ~61% pass^1 on retail and ~35% on airline
- pass^8 drops to <25% on retail (high inconsistency across runs)
- Simple function-calling and ReAct agents both fail frequently; complex reasoning, policy following, and compound requests are main failure modes

**Relevance to multi-user-turn-codebench:**
tau-bench establishes the key pattern of evaluating agents via simulated user interaction with grounded outcome validation. Its `pass^k` consistency metric is directly relevant: our benchmark should similarly measure turn-to-acceptance variance across different agent runs on the same session. The main difference: tau-bench is for customer service agents with structured databases; our benchmark is for coding agents with real software state. Tau-bench's user simulation approach (LM given scenario description) is a template for how we could generate synthetic counterfactual users to replay sessions.

**BibTeX:**
```bibtex
@misc{yao2024taubench,
  doi = {10.48550/ARXIV.2406.12045},
  url = {https://arxiv.org/abs/2406.12045},
  author = {Yao, Shunyu and Shinn, Noah and Razavi, Pedram and Narasimhan, Karthik},
  title = {$\tau$-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains},
  publisher = {arXiv},
  year = {2024}
}
```

---

### 9. WebArena: A Realistic Web Environment for Building Autonomous Agents

**File:** `webarena_2307.13854.pdf`
**Year:** 2023 | **Citations:** 974 | **ArXiv:** 2307.13854

**Methodology Summary:**
WebArena provides 812 tasks across four realistic website domains (e-commerce, social forum, GitLab, CMS), deployed via self-contained Docker images. Tasks are defined as natural language intent; evaluation uses programmatic functional correctness checking (intermediate execution state) or LLM-as-judge for information-seeking tasks. Human baseline: 78.24% success. Agents operate without multi-turn user correction—they receive only environmental feedback (page state) not human corrections.

**Key Results:**
- Best model (GPT-4): 14.41% end-to-end success vs. 78.24% human baseline
- GPT-4 incorrectly marks 54.9% of achievable tasks as impossible (early stopping bias)
- Inconsistent performance across task template variations

**Relevance to multi-user-turn-codebench:**
WebArena exemplifies the state-of-the-art in realistic, execution-grounded agent evaluation. Key lessons: (1) Docker-based reproducible environments are now standard—we should follow this. (2) Programmatic evaluation of execution state is scalable and reliable. (3) The huge gap between human and agent performance (78% vs. 14%) motivates multi-turn benchmarks where agents can recover with user guidance. WebArena does not model user correction turns, which is our key differentiator.

**BibTeX:**
```bibtex
@misc{zhou2023webarena,
  doi = {10.48550/ARXIV.2307.13854},
  url = {https://arxiv.org/abs/2307.13854},
  author = {Zhou, Shuyan and Xu, Frank F. and Zhu, Hao and Zhou, Xuhui and Lo, Robert and Sridhar, Abishek and Cheng, Xianyi and Ou, Tianyue and Bisk, Yonatan and Fried, Daniel and Alon, Uri and Neubig, Graham},
  title = {WebArena: A Realistic Web Environment for Building Autonomous Agents},
  publisher = {arXiv},
  year = {2023}
}
```

---

### 10. Simulating User Satisfaction for the Evaluation of Task-oriented Dialogue Systems

**File:** `user_sim_tod_2105.03748.pdf`
**Year:** 2021 | **Citations:** 72 | **ArXiv:** 2105.03748

**Methodology Summary:**
This paper proposes a task combining user action simulation with satisfaction modeling: jointly predicting the next user action and satisfaction level given dialogue context. A dataset (USS) of 6,800 annotated dialogues across 5 domains is constructed, with per-exchange satisfaction ratings (1–5 scale, Fleiss Kappa = 0.574). Models tested include TF-IDF, GRU/HiGRU, and BERT. Key finding: 36% of very dissatisfied conversations arise when the system fails to understand user needs; 43% when it understands but cannot provide solutions. When users are dissatisfied: ~64% provide additional information, ~17% switch to manual service, ~10% quit.

**Key Results:**
- BERT achieves 0.661 accuracy on user action prediction (SGD domain)
- HiGRU best in-domain satisfaction prediction (UAR 0.339 on JDDC)
- BERT generalizes better across domains

**Relevance to multi-user-turn-codebench:**
This work motivates the user simulation component of our benchmark. When replaying real sessions, we need a user simulator that models natural correction behavior. The finding that ~64% of dissatisfied users provide additional information (rather than quitting) suggests that iterative correction is the dominant user strategy—exactly what our benchmark measures. The satisfaction annotation framework informs how we can label the "acceptance" event in real sessions.

**BibTeX:**
```bibtex
@article{sun2021simulating,
  doi = {10.48550/ARXIV.2105.03748},
  url = {https://arxiv.org/abs/2105.03748},
  author = {Sun, Weiwei and Zhang, Shuo and Balog, Krisztian and Ren, Zhaochun and Ren, Pengjie and Chen, Zhumin and de Rijke, Maarten},
  title = {Simulating User Satisfaction for the Evaluation of Task-oriented Dialogue Systems},
  publisher = {arXiv},
  year = {2021}
}
```

---

### 11. Why AI Agents Still Need You: Findings from Developer-Agent Collaborations in the Wild

**File:** `why_agents_need_you_2506.12347.pdf`
**Year:** 2025 | **Citations:** 5 | **ArXiv:** 2506.12347

**Methodology Summary:**
A qualitative study of 19 professional software developers using Cursor Agent on 33 real GitHub issues over 60-minute sessions. Data collection: video/audio recordings, questionnaires, two custom taxonomies applied with high inter-rater reliability (κ=0.92 for participant actions; κ=0.89 for chat trajectories). Key finding: incremental (multi-prompt) strategies achieve 83% success vs. 38% for one-shot strategies. Participants follow agent execution in 84% of prompts and review code diffs after 67% of code-change responses.

**Key Results:**
- Overall success rate: 55% (16/29 issues)
- Incremental (multi-prompt) strategy: 83% success, avg 11 prompts; one-shot: 38% success, avg 7 prompts
- Expert domain knowledge provision: 64% success vs. 29% without it
- 7 communication barriers identified: tacit knowledge gaps, unsolicited actions, synchronicity issues, verbosity, sycophancy, overconfidence, poor follow-up suggestions
- Agent-proposed next steps matched actual needs in only 7% of cases

**Relevance to multi-user-turn-codebench:**
This study provides ground truth for the user-correction patterns our benchmark captures. The key finding—that incremental, multi-turn strategies dramatically outperform single-shot approaches—directly motivates measuring "turns-to-acceptance." The 7 failure modes are a qualitative taxonomy of the intent gap our metric targets. The study is qualitative (19 participants, 33 issues); our benchmark provides quantitative evaluation at scale using real session logs.

**BibTeX:**
```bibtex
@misc{kumar2025whyagents,
  doi = {10.48550/ARXIV.2506.12347},
  url = {https://arxiv.org/abs/2506.12347},
  author = {Kumar, Aayush and Bajpai, Yasharth and Gulwani, Sumit and Soares, Gustavo and Murphy-Hill, Emerson},
  title = {Why AI Agents Still Need You: Findings from Developer-Agent Collaborations in the Wild},
  publisher = {arXiv},
  year = {2025}
}
```

---

## Additional Papers Identified (Not Downloaded, Reviewed by Abstract)

### MT-Bench and Chatbot Arena (Judging LLM-as-a-Judge)
**ArXiv:** 2306.05685 | **Citations:** 7223

MT-Bench comprises 80 multi-turn questions (exactly 2 turns per question) across 8 categories including coding. LLM-as-judge with GPT-4 achieves >80% agreement with human experts. Key finding: multi-turn evaluation better differentiates advanced model capabilities than single-turn. Chatbot Arena collects ~30K crowdsourced preference votes on open-ended conversations.

**Relevance:** MT-Bench is the only major benchmark with multi-turn coding questions, but it has only 2 turns (one follow-up) and uses synthetic tasks. Chatbot Arena uses real user preferences but doesn't focus on coding agents or turns-to-acceptance. Both motivate our work by showing multi-turn evaluation reveals capabilities invisible in single-turn settings.

```bibtex
@misc{zheng2023judging,
  doi = {10.48550/ARXIV.2306.05685},
  url = {https://arxiv.org/abs/2306.05685},
  author = {Zheng, Lianmin and Chiang, Wei-Lin and Sheng, Ying and others},
  title = {Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena},
  publisher = {arXiv},
  year = {2023}
}
```

### Training Long-Context, Multi-Turn Software Engineering Agents with Reinforcement Learning
**ArXiv:** 2508.03501 | **Citations:** 14

Treats SWE tasks as POMDPs and trains agents with RL. Multi-turn means agent-environment interaction (execution feedback across dozens of steps), not user-correction turns. Achieves 39% pass@1 on SWE-bench Verified. The gap between pass@1 (39%) and pass@10 (58.4%) motivates multi-turn evaluation.

**Relevance:** Distinguishes agent-environment multi-turn (execution feedback) from user-agent multi-turn (correction turns)—a distinction central to our benchmark's novelty. The pass@1 vs. pass@10 gap shows there's value in allowing multiple attempts.

```bibtex
@misc{golubev2025training,
  doi = {10.48550/ARXIV.2508.03501},
  url = {https://arxiv.org/abs/2508.03501},
  author = {Golubev, Alexander and others},
  title = {Training Long-Context, Multi-Turn Software Engineering Agents with Reinforcement Learning},
  publisher = {arXiv},
  year = {2025}
}
```

### TOM-SWE: User Mental Modeling for Software Engineering Agents
**ArXiv:** 2510.21903 | **Citations:** 3

Applies Theory of Mind to SWE agents—agents should model what the user knows and wants. Explicitly addresses the gap between stated issue and underlying user intent.

**Relevance:** Directly addresses our "intent gap" concept from a cognitive modeling perspective. Supports our framing that current single-turn benchmarks miss the intent inference problem.

### AppWorld: A Controllable World of Apps and People for Benchmarking Interactive Coding Agents
**ArXiv:** 2407.18901 | **Citations:** 107

Benchmarks agents on coding tasks within a simulated world of apps with interacting synthetic users. Closer to our work than SWE-bench but still uses synthetic users/tasks.

**Relevance:** Another execution-grounded multi-step agent benchmark. Confirms the trend toward interactive, environment-grounded evaluation.

---

## Search Results Summary by Angle

### Angle 1: Coding Agent Benchmarks
Top papers by citation count relevant to our work:
- SWE-bench (2310.06770): 1612 citations — canonical single-turn benchmark
- SWE-agent (2405.15793): 774 citations — multi-step agent, single-turn eval
- InterCode (2306.14898): 182 citations — most relevant interactive coding eval
- Ambig-SWE (2502.13069): 16 citations — underspecificity in SWE tasks (most direct prior work)

Also noted: `Training Long-Context Multi-Turn SWE Agents` (2508.03501, 14 citations) addresses multi-turn but from RL training perspective, not evaluation.

### Angle 2: Multi-Turn / Dialogue Code Generation
Top papers:
- LLM-TDD user study (2404.10100): 92 citations
- TiCoder / Interactive TDD (2208.05950): 88 citations
- ConvCodeWorld (2502.19852): 13 citations — most directly relevant benchmark
- Let's Fix this Together: Conversational Debugging with GitHub Copilot (19 citations, no ArXiv) — real user debugging study

### Angle 3: User Intent & Preference Revelation
- Interactive TDD (2208.05950): formalization of user intent via test queries
- Ambig-SWE (2502.13069): underspecification gap
- Asking Clarification Questions for Code Generation (2022): 3 citations
- TOM-SWE (2510.21903): Theory of Mind for user modeling in SWE

### Angle 4: Execution-Based / Environment-Grounded Evaluation
- WebArena (2307.13854): 974 citations — Docker sandbox, realistic env
- InterCode (2306.14898): 182 citations — Docker-based execution
- tau-bench (2406.12045): ~80 citations — database state grounding

### Angle 5: Related Benchmarks
- Chatbot Arena / MT-Bench (2306.05685): 7223 citations — multi-turn preference eval (general, not coding)
- WebArena (2307.13854): 974 citations
- LiveCodeBench (2403.07974): 1166 citations — contamination-free coding eval
- AppWorld (2407.18901): 107 citations — interactive coding agent world

---

## Gaps and Our Contribution

### What Existing Work Does NOT Do

**1. No benchmark uses real user sessions as ground truth.**
All existing benchmarks—SWE-bench, InterCode, ConvCodeWorld, Ambig-SWE, tau-bench—either synthesize tasks from scratch or extract them from GitHub with synthetic annotation. None uses actual recorded sessions where a real developer iteratively guided a real AI coding agent to task completion. Our benchmark (multi-user-turn-codebench) mines Data Claw (Claude Code interaction logs) to build a dataset of authentic multi-turn coding interactions.

**2. No benchmark measures turns-to-acceptance as a primary metric.**
SWE-bench measures binary resolve rate. InterCode counts turns but measures binary success at the episode level. ConvCodeWorld uses MRR (an efficiency proxy) but over synthetic feedback. MT-Bench uses 2 fixed turns. None provides a metric grounded in *when a real user actually accepted the output*. Our "turns-to-acceptance" is the first benchmark metric tied to authentic user acceptance events from production logs.

**3. No benchmark captures the intent gap from real user sessions.**
The intent gap—the difference between what a user can initially articulate and what they ultimately want—has been studied synthetically (Ambig-SWE) or via small user studies (Why AI Agents Still Need You, n=19). Our benchmark provides this at scale: each real session contains the full arc from initial (potentially underspecified) prompt through successive corrections to the acceptance event, giving a naturalistic measure of intent gap magnitude.

**4. Existing multi-turn benchmarks use synthetic or constrained feedback.**
InterCode restricts feedback to execution signals (compiler/interpreter output). TiCoder uses Yes/No test queries. ConvCodeWorld uses GPT-4o-generated verbal feedback at fixed expertise levels. tau-bench uses LLM-simulated users with scripted scenario descriptions. None captures the diversity and naturalness of real developer correction utterances—which include implicit feedback ("this isn't quite right"), domain context, stylistic preferences, and follow-on requirements.

**5. No benchmark measures session-level success with user-side acceptance as the oracle.**
In SWE-bench and InterCode, "success" is defined by test pass/fail—a proxy for user satisfaction. In real sessions, users may accept code even when some tests fail (good-enough solution) or reject code that passes all tests (wrong interpretation of intent). Our benchmark grounds success in actual acceptance events from real sessions, providing a more valid measure of what users actually want.

**6. No benchmark distinguishes agent capability under naturalistic correction from synthetic correction.**
The "Why AI Agents Still Need You" study found that incremental multi-turn strategies achieve 83% success vs. 38% one-shot, but this is qualitative (n=19). ConvCodeWorld shows feedback type matters at scale but uses synthetic tasks. Our benchmark provides the first large-scale, execution-grounded comparison of agent performance under real user correction trajectories.

### Our Contribution

Multi-user-turn-codebench fills these gaps by:
1. **Real sessions as tasks**: Mining Data Claw Claude Code session logs to extract (session, acceptance event) pairs
2. **Turns-to-acceptance metric**: Counting turns from initial prompt to acceptance, normalized by session complexity
3. **Intent gap metric**: Measuring the semantic distance between the initial prompt and the full specification revealed through the session
4. **Execution-grounded validation**: Replaying sessions in sandboxed environments to verify agent outputs match acceptance criteria
5. **User simulator for counterfactual evaluation**: Training a user simulator on real correction patterns, enabling evaluation of new agents on historical sessions without requiring new human-agent interactions
6. **Scale**: Providing hundreds to thousands of real sessions, vs. the 19-session qualitative study in prior work

This positions our benchmark as the naturalistic, large-scale complement to the controlled synthetic benchmarks (SWE-bench, InterCode, ConvCodeWorld, Ambig-SWE) and the small-scale qualitative studies (Why AI Agents Still Need You, TiCoder user study).
