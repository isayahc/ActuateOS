# Proposed evaluation protocol

This document specifies a starting protocol for future experiments. No experiments or results are included yet.

See [Benchmark comparison matrix and planned target values](benchmark-comparison.md) for native benchmark metrics, proposed numeric thresholds, ablations, published reference anchors, and matched-trial comparison rules.

## 1. Define the experiment

Record the research question, task domain, source benchmark version, dataset access conditions, and supported operation vocabulary. Define independent task-success predicates before running any system.

For every task, record:

- Source demonstration and annotation identifiers.
- Component geometry and equipment metadata provenance.
- Initial state, target state, and valid procedural dependencies.
- Available capabilities, fixtures, sensors, and resource constraints.
- Unknown properties and explicitly declared simulation assumptions.
- Evaluation mode: reconstruction-only, simulated execution, or physical execution.

## 2. Construct splits and variations

Honor published benchmark splits when applicable. For derived scenarios, split source tasks or demonstration families before generating variations so related instances do not cross training and evaluation boundaries.

Record generator version, random seed, perturbation ranges, rejection criteria, and accepted scenario identifiers. Apply identical held-out scenarios to all compared systems. Report invalid generated instances and rejection rates separately.

## 3. Compare systems

Evaluate direct video-to-action, fixed procedures, and the structured multi-agent approach. Declare whether equipment selection and layout modification are allowed for each comparison. Include a fixed-workcell comparison to help distinguish planning improvements from gains due to changed equipment.

Record model versions, prompts, available observations, tool access, compute budgets, retry limits, and execution timeouts. Account for human-provided plans and workcell setup in engineering-effort measurements.

## 4. Verify outcomes

Check reconstruction against reference annotations where available. Check plans against independently specified capabilities and constraints. Verify final states using benchmark-native evaluators or separately defined predicates, rather than accepting an agent's self-reported success.

For continuous conditions, declare tolerances and measurement methods. Distinguish static constraint validation from dynamically validated execution.

Use these outcome categories:

- Reconstruction failure.
- Unsupported or infeasible plan.
- Execution failure.
- Verification failure or insufficient evidence.
- Verified success.

Log recovery attempts and distinguish successful completion on the first attempt from completion after recovery. Define a recoverable failure and the recovery budget before calculating recovery rates.

## 5. Report results

Use benchmark-native metrics for original tasks. For derived workcell experiments, report at minimum:

| Metric | Reporting requirement |
| --- | --- |
| Reconstruction accuracy | Annotation granularity and matching rules for operations, states, and graph edges. |
| Plan validity | Fraction of evaluated tasks yielding plans that pass the declared checks; list checks and coverage. |
| End-to-end success | Verified successful tasks divided by all evaluated tasks, including upstream failures. |
| Recovery success | Recovered tasks divided by eligible failed tasks, with eligibility rules and budgets. |
| Execution time | Timing boundaries; report planning and recovery time separately where possible. |
| Human intervention | Number, type, and duration of interventions and setup work. |
| Generalization | Metrics grouped by held-out task family and variation type. |

Report trial counts, seeds, uncertainty estimates, and failure distributions. Do not merge simulation and physical-hardware results into one success rate.

## Experiment record template

```yaml
experiment_id: null
research_question: null
repository_commit: null
benchmark:
  name: null
  version: null
  split: null
scenario:
  source_task_ids: []
  generator_version: null
  seeds: []
  assumptions: []
system:
  baseline_or_ablation: null
  model_versions: []
  prompt_version: null
  equipment_configuration: null
  reconfiguration_allowed: null
  retry_budget: null
  timeout_seconds: null
execution:
  mode: null
  adapter_version: null
  simulator_or_hardware_version: null
verification:
  evaluator_version: null
  success_predicates: []
  tolerances: {}
artifacts:
  plans: null
  execution_traces: null
  validation_reports: null
  intervention_log: null
results:
  trial_count: null
  metrics: {}
  uncertainty_method: null
  failure_breakdown: {}
```

This template is a reporting aid, not an implemented configuration schema.
