# Benchmark comparison matrix and planned target values

**Status:** Pre-registered *proposal*, 2026-11-21. **No Video-to-Workcell experiments have been run and no results are claimed.** Numeric targets below are project design goals, **not** published benchmark results or calibrated expectations. Do not move a target after observing the held-out test outcomes without explicitly recording a new protocol version.

This document supplements [docs/evaluation.md](evaluation.md). It answers: **what values do we compare, against whom, under what conditions, and what would count as a meaningful improvement?**

## 1. Comparison principle

We make **two separate kinds of comparisons**, which must not be combined into one leaderboard score:

1. **Benchmark-native reproduction:** On the *original task, test split, inputs, permitted tools, metric implementation and evaluation mode*, compare against the source benchmark's published/reproduced baseline. Use the benchmark's official evaluation scripts and report its native scores. A benchmark for video interpretation is **not** evidence of physical robot execution.
2. **Derived end-to-end evaluation:** On independently specified Video-to-Workcell tasks (video → Process IR → workcell → feasible plan → execution → checked final state), compare matched versions of our own pipeline using the *same source task IDs, held-out conditions, equipment budget, hardware/simulator and success predicate*. This is **our benchmark**, not an official score on IndustReal, LongVILBench, RoboCasa, or DexBench.

A numerical result is eligible for a public “beats baseline” claim only if it uses comparable task conditions and includes denominators, uncertainty, evaluator version, sources, and execution traces.

## 2. Original benchmarks and native metrics

| Source and exact protocol to pin | Benchmark-native measurements to report | What it evaluates | What it **cannot** prove by itself |
| --- | --- | --- | --- |
| **IndustReal** (WACV 2024; official procedure step recognition) | Procedure Order Similarity (**POS**, [0,1], ↑), correct-step completion **F1** ([0,1], ↑), average step detection delay (seconds, ↓) | Video-based completion and order of procedure steps, including erroneous execution | Machine reachability, physical execution or workcell design |
| **IMPACT v1.1** (official PSR/ASR tasks and S1 split) | **PSR:** step completion F1, detection delay, POS; **ASR:** macro-F1, transition F1, final-state **recognition** accuracy | Visual step recognition and component assembly state from industrial video | Executed robotic final-state achievement; ASR final-state accuracy is *recognition*, not robot success |
| **LongVILBench** (original levels, clean/complex splits) | Exact Match Accuracy (**EMA**, ↑), Step-wise Matching Score (**SMS**, ↑), Final State Accuracy (**FSA**, ↑) | Video-to-sequence/program matching and simulated state achieved by execution | Real-world hardware transfer or automated workcell design |
| **Assembly101** (official temporal segmentation split) | Segmental F1@10/25/50 (↑), normalized edit score (↑), mean over frames / frame accuracy (**MoF**, ↑) | Fine-grained activity segmentation, distinct from procedure verification | Machine plans or physical execution |
| **CaptainCook4D** (official error-recognition / localization tasks and splits) | Task-specific error recognition and multi-step localization metrics from official evaluation scripts; pin the exact task and metric in each run | Detection/localization of mistakes in procedural activity | Workcell feasibility or embodied task success |
| **RoboCasa** (pinned task set, simulation version and evaluation split) | Mean binary task success rate (↑), also stratify atomic/composite and seen/unseen | Simulated robotic policy execution in kitchen environments | Automatic derivation of workcells from human videos |
| **DexBench** (pinned world/action/skill/scenario and evaluation revision) | Task success and breakdown across object/physics/spatial generalization axes **GA-O / GA-P / GA-S**; use the exact released evaluator | Industrial manipulation and generalization under benchmark-fixed workcells | End-to-end process reconstruction or redesigned-workcell performance |

**Published numeric anchors — reference examples only (not our scores):**

| Benchmark and reference method | Published values | Use and comparability restriction |
| --- | --- | --- |
| Assembly101, C2F-TCN baseline, original paper temporal-segmentation table | **F1@10 = 33.3; F1@25 = 29.0; F1@50 = 21.3; Edit = 32.4; MoF = 39.2** (scores on a 0–100 scale) | Compare **only** if we reproduce the same temporal segmentation split, class granularity, evaluation script and inputs; do not equate these with Process IR operation F1 |
| RoboCasa365, GR00T N1.5 baseline, published multi-task table | **Atomic-Seen = 43.0%; Composite-Seen = 9.6%; Composite-Unseen = 4.4%; average = 20.0%** | Compare **only** on the pinned RoboCasa task suite, policy inputs and simulation protocol; this is **not** a Video-to-Workcell success target |

For IndustReal, IMPACT, LongVILBench, DexBench and CaptainCook4D, **numeric reference scores remain TBD pending selection of the exact official checkpoint, protocol and split**. Never populate a “published” cell using a different task, a community reproduction with altered inputs, or a score invented for planning.

## 3. Video-to-Workcell derived end-to-end scorecard

The **unit of evaluation** is a held-out production objective and initial world state, tied to a demonstration video and a predeclared independent final-state predicate. Count an upstream parsing/planning failure as **not completed**, rather than dropping it from the denominator.

| ID | Metric and unit | Exact calculation / reporting rule | Provisional acceptance goal (not observed) | Baseline comparison |
| --- | --- | --- | --- | --- |
| **E2E-01** | **Verified end-to-end completion rate**, % | 100 × trials with independent final-state success / **all assigned trials**; separate simulated vs physical | **≥70%** on the initial *supported* derived task suite, **and ≥+15 percentage points** over B1 | B1, B2, B3 on identical paired trials |
| **REC-01** | **Operation reconstruction F1**, [0,1] | Matched precision/recall F1 for operation type, actor, target and state transition under frozen matching rules; report exact fields separately | **≥0.80** on held-out annotated derived tasks | B1 vs B3; separately native PSR/F1 or EMA where compatible |
| **REC-02** | **Dependency edge F1**, [0,1] | Precision/recall of required precedence edges in Process IR vs independently annotated reference DAG; exclude valid reorderings | **≥0.75** | B1 vs B3; not interchangeable with benchmark POS |
| **PLAN-01** | **Plan validity / supported coverage**, % | **Validity:** independently validated plans / plans submitted on **predeclared supported tasks**. **Coverage:** supported tasks / all assigned tasks. Report both; do not hide unsupported tasks | **≥90% validity** on supported tasks; coverage explicitly reported, **no target yet** | B1, B2, B3; same validator |
| **SAFE-01** | **Unsupported action dispatch**, count | Number of accepted commands with an unsupported skill or violated hard capability precondition; separately report proposals rejected before dispatch | **0 unsupported dispatches**; count all invalid proposals too | All systems behind the same independent safety gate |
| **RECO-01** | **Recovery success rate**, % | 100 × eligible failures ultimately recovered / predeclared recoverable failure cases; fixed retry/time budget and failure taxonomy | **≥50%**, conditional on supported recoverable perturbations | B1 vs B3; also report recovery latency/retries |
| **GEN-01** | **Generalization gap**, percentage points | Seen-condition E2E completion − unseen-condition E2E completion, using separately fixed strata and balanced trial counts | **≤15 percentage points**, *provided unseen success is nontrivial* | B1 vs B3, by variation axis |
| **EFF-01** | **Human engineering effort**, minutes/task | Hands-on setup, configuration, debugging and manual intervention needed to deploy a successful supported task; report failed-task effort separately and account for fixed-program authoring | **≥25% reduction** versus a comparable human-configured baseline; **hypothesis only** | B0 vs B3; publish procedure for time logging |
| **EFF-02** | **End-to-end latency**, seconds and cost | Video ingest → independent outcome; report planning, simulation/robot runtime, inference calls/tokens, tool use and cost per *verified* success | **No numerical threshold yet**; report median/p90 and costs | B1, B2, B3 with declared budgets |

All percentages should show **numerator / denominator** as well as the percentage. The numeric goals above are intended to make an initial experiment falsifiable, not to establish what is realistic before calibration.

**Priority order:** E2E-01 (primary outcome) → PLAN-01 / REC-01 / REC-02 (why it worked or failed) → RECO-01 / GEN-01 (robustness) → EFF-01 / EFF-02 (economic relevance). Do not aggregate into an arbitrary weighted score.

## 4. Systems to compare (ablation ladder)

| ID | System | What changes | Fixed across comparisons |
| --- | --- | --- | --- |
| **B0** | Human-configured fixed procedure | Human designs workcell and action sequence for known task; no autonomous adaptation | Same target objective, available equipment and outcome verifier; log manual setup hours |
| **B1** | Single Gemini model call / simple tool pipeline | Video → flat or directly executable action list; no typed Process IR, workcell adaptation or dedicated diagnostic agent | Same video, support actions, observation access, physical setup and execution safety checks |
| **B2** | Two agents + typed Process IR, fixed workcell | Process reconstruction → planning; **no workcell modification or autonomous recovery** | Same Gemini models where applicable, budget, evaluator, hardware/physics, scenario seeds |
| **B3** | Full Video-to-Workcell | Two agents + Process IR + reconfigurable workcell + feasibility checks + limited feedback-driven recovery | Same objective, equipment/resource budget, ground-truth predicate and trial distributions |

**Fairness guardrails:**

- For **execution-policy** comparisons, freeze workcell geometry, robot, sensors, actuators and physics; then compare policy/planner contributions only.
- For **workcell synthesis** comparisons, permit redesign only in explicitly designated tracks, with identical allowed equipment catalogs, budgets and objective. Report added fixtures/tools and engineering cost. These results are **not** official fixed-world DexBench scores.
- All agents see **permitted observations**, not hidden simulation truth or the evaluator's private success labels. The verifier owns ground truth.
- Fix model identifiers, versions, prompts, temperature, tool APIs, context budget, maximum retries, runtime budget and hardware/simulator versions. B1 gets a fair comparable budget; report actual token and tool usage.
- Never score a rendering or keyframe animation as a physically verified assembly.

## 5. Proposed pilot test matrix and locked splits

**Initial research candidates:** (a) **IndustReal** for video-based procedure step completion; (b) **LongVILBench** for video → program → simulated final state, if we can run its supported executor. **IMPACT** is a strong alternate for partial-order and error/recovery supervision. These data sources do **not** automatically include OpenIndustries-ready robots or runnable execution adapters.

**Pilot: 60 paired, held-out derived scenarios**, each evaluated for B1, B2 and B3 with the *same* initial conditions and reproducible seeds:

| Stratum | Planned count | Variation to test | Score breakdown |
| --- | ---: | --- | --- |
| Nominal / previously specified configuration | 20 | Fixed supported equipment, clean video, no disturbances | E2E, REC, PLAN, latency |
| Spatial + observation perturbation | 20 | Placement/viewpoint changes within declared feasible bounds; some occlusions | E2E, GEN, failure types |
| Recoverable process disturbance | 20 | Predeclared missing/moved item or recoverable failed operation, fixed recovery budget | E2E, RECO, retries, latency |

The 60-trial pilot is **not** statistically powered to prove all small improvements. Include 95% uncertainty intervals for rates, paired discordant-case counts and a paired comparison (e.g. McNemar test for binary completion) where appropriate. Expand to **≥200 paired trials** for a stronger claim when the variance and effect size justify it.

**Leakage prevention:** Partition by source video / procedure family **before** synthetic generation; keep all descendants of a source demonstration in one split. Select procedures, predicates, perturbation distributions and success criteria **before** observing final test results. Data or prompts tuned using held-out failures must be assigned to a new evaluation version.

**Synthetic controls:** Store object transforms, physical parameter sources, generator version, seeds, rejection reasons and accepted variation counts. Reject infeasible synthetic states using declared physical/logic checks. Do not confuse “physically plausible under a simulator” with hardware validation.

## 6. Result record and evidence requirements

Each row of the result table must be backed by a machine-readable record containing:

| Field | Description |
| --- | --- |
| identity | experiment_id, scenario_id, source_video_id, benchmark_name/version/split, source artifact hashes |
| system | B0/B1/B2/B3, model names/versions, prompt revision, software commit, tool access and retry budget |
| execution | hardware or simulator + version, workcell/geometry hashes, initial state, allowed actions, execution mode |
| outcomes | per-operation predictions, operation ground truth, plan validity, constraint violations, verified final state and verifier version |
| human/effort | intervention count and minutes, manual setup minutes, tokens, runtime seconds, estimated monetary cost |
| analysis | successful numerator/denominator, failure category, recovery eligibility, recovery count, matched pair ID, seed and 95% interval |

**Required publication table:**

| Metric | B0 | B1 | B2 | B3 | Published benchmark anchor (same protocol only) |
| --- | --- | --- | --- | --- | --- |
| E2E success (n/N, %) | TBD | TBD | TBD | TBD | N/A: no matching public Video-to-Workcell protocol |
| Reconstruction operation F1 | N/A | TBD | TBD | TBD | Report separately on *native* IndustReal / IMPACT / Assembly101 metrics |
| Process-order / graph correctness | Human authored | TBD | TBD | TBD | Native POS, SMS or edit metrics **only** when identical task/protocol |
| Executable final-state success | TBD | TBD | TBD | TBD | LongVILBench FSA or RoboCasa task success only under original execution protocol |
| Plan validity / supported coverage | TBD | TBD | TBD | TBD | N/A for incompatible benchmarks |
| Recovery success (n/N, %) | N/A if no recovery | TBD | TBD | TBD | Relevant IMPACT / CaptainCook4D error metrics reported separately |
| Human setup and intervention minutes | TBD | TBD | TBD | TBD | No benchmark-native comparator established |
| Runtime and cost per success | TBD | TBD | TBD | TBD | Only compare with same hardware/compute accounting |

Replace **TBD** only with traceable experiment outputs. Use **N/A** when a metric genuinely does not apply, never as a substitute for a failed experiment. Report failure causes by perception, process reconstruction, constraint planning, machine execution, final-state verification and insufficient evidence.

## 7. Sources and source of numeric values

These are benchmark specifications / original references, not proof of Video-to-Workcell performance.

1. **IndustReal** — [official project/evaluation definitions](https://timschoonbeek.github.io/industreal.html), [WACV 2024 paper](https://openaccess.thecvf.com/content/WACV2024/html/Schoonbeek_IndustReal_A_Dataset_for_Procedure_Step_Recognition_Handling_Execution_Errors_WACV_2024_paper.html).
2. **IMPACT** — [official v1.1 benchmark protocol](https://github.com/Kratos-Wen/IMPACT/blob/main/docs/BENCHMARK.md) and [project page](https://diwen.ai/IMPACT/).
3. **LongVILBench** — [benchmark and metric definitions](https://huggingface.co/datasets/cq838/LongVILBench/blob/main/README.md), [evaluation source](https://github.com/chenquan2002/LongVIL).
4. **Assembly101** — [original paper, Table 7](https://assembly-101.github.io/assets/Assembly101.pdf) (C2F-TCN published anchor).
5. **CaptainCook4D** — [official project and evaluation releases](https://github.com/CaptainCook4D/CaptainCook4D).
6. **RoboCasa365** — [official multi-task baseline table](https://robocasa.ai/docs/build/html/benchmarking/multitask_learning.html) (GR00T N1.5 numeric anchor); [official benchmarking protocol](https://robocasa.ai/docs/build/html/benchmarking/benchmarking_overview.html).
7. **DexBench** — [task/generalization framework](https://dexbench.org/en/).

## 8. Prerequisites before any “beat benchmark” statement

- [ ] Freeze dataset versions, licenses, supported task subset and official evaluator versions.
- [ ] Specify which metric is **native** vs **derived**, and select a genuine comparable published/reproduced baseline.
- [ ] Write independent success predicates and instrument the final-state verifier.
- [ ] Freeze supported action set, equipment catalog, allowable workcell changes and budget.
- [ ] Partition source videos by family before generating synthetic variants.
- [ ] Run B1/B2/B3 on the same held-out episode IDs/seeds; include B0 with explicitly accounted manual effort.
- [ ] Record both successes and failures with reproducible execution traces.
- [ ] Compute denominators, intervals, generalization gaps and paired effects.
- [ ] Report physical and simulated claims separately; do not imply a video-only score proves real robot automation.

**Decision rule:** If B3 is not significantly and practically better on the *same* derived execution tasks, describe the system as a feasibility prototype; do not claim a superior automation benchmark result. If only process-recognition metrics improve, make that narrower claim instead.
