# Gemini 4 NYC Hackathon — Element 119 track

**Track selection: Element 119 (Multimodal AI).** This is the **primary submission track** for Video-to-Workcell. **5 Sigma is not our primary track.** We will borrow baseline comparisons and failure analysis from 5 Sigma as supporting evidence, not as our submission category.

**Status:** Plan / submission intent only. This document does not claim that the pipeline, two-model integration, Managed Agents integration, or execution validation are implemented.

## Why Element 119

Video-to-Workcell starts from **human demonstration video**, rather than a typed procedural description. Gemini must extract information that a text summary alone would omit: object identity and location, action order, hand–object interactions, before/after state changes, temporal relationships, tool usage, and ambiguous or missing observations.

The proposed novel output is a **machine-readable physical process plus a configured workcell and checkable execution trace** — not merely a video summary or an image analyzer.

The participant guide asks Element 119 teams to push multimodal capabilities, demonstrate what is gained from raw media, evaluate difficult inputs, and show where the approach fails.

## Planned distinct model responsibilities

| Component | Responsibility | Required evidence |
| --- | --- | --- |
| **Gemini 4 model A — Video reconstruction** | Ingest one or more demonstration videos and produce grounded `ProcessIR` with timed operations, entities, dependencies, state changes, and uncertainty | Source video identifiers/timestamps and schema-valid IR |
| **Gemini 4 model B — Workcell planner / managed engineering agent** | Consume `ProcessIR` plus supported machine/space metadata; propose a serialized workcell and operational plan; revise on verifier feedback | Validated proposed scene, machine capability mapping, action plan and revision trace |
| **Deterministic verifier and execution adapter (non-model)** | Reject unsupported actions; evaluate constraints; run only implemented operations and independently check final-state predicates | Constraint report, actual command/observation trace, explicit outcome classification |

Use **at least two distinct Gemini 4 models**, each with a clear job, consistent with the event-wide rules. Record the actual model IDs used at submission time; names/availability are not frozen by this document.

**Optional bonus target:** Best Use of Managed Agents. The engineering/planning agent is the proposed integration point for Google's hosted Managed Agents environment, with carefully scoped OpenIndustries tools. Running two ordinary Gemini API calls alone is not proof of a Managed Agents integration.

## Planned live demonstration: end-to-end

1. **Unrehearsed video input:** Take an unfamiliar demonstration of one supported assembly or preparation task. Show the input footage, not merely a text description.
2. **Visual extraction:** Model A creates a timestamp-grounded `ProcessIR`, including uncertain/unsupported observations rather than fabricating missing physical properties.
3. **Physical synthesis:** Model B uses capabilities and scene data to propose a workcell configuration and executable sequence.
4. **Independent verification:** Validate prerequisites, available tools, resource limits and supported motions. Reject impossible plans without mislabeling them as execution successes.
5. **Execution attempt:** Dispatch supported operations to a simulation or physical adapter; record observations and independent final-state checks. Clearly distinguish simulated, unsupported and hardware-verified outcomes.
6. **Stress test:** Change camera viewpoint, occlude a key step, move a component or tool, or introduce an allowed disturbance. Show what breaks and whether the system detects and adapts.

**Minimum demo criterion:** A video materially changes the structured task and downstream proposed workcell/plan. A canned animation or a pipeline that only transcribes the video is not sufficient.

## Evaluation to support Element 119

Use [the evaluation protocol](evaluation.md) and [benchmark comparison matrix](benchmark-comparison.md) where available. These are supporting proofs, **not** a claim of beating an official robotics leaderboard.

| Question | Evidence to collect |
| --- | --- |
| Does raw video add information beyond text? | Compare video-conditioned reconstruction with a **text-only summary baseline**, matched on goal and allowable context; show at least one state, ordering or spatial fact resolved from frames |
| Can the system handle unfamiliar inputs? | Held-out source videos and variable camera views, clutter, occlusion or procedural deviations, with source-family split before synthetic augmentation |
| Is the result actionable? | `ProcessIR` schema validity, supported-operation coverage, independently checked plans, and verified final-state success when an executable adapter exists |
| Does agent specialization matter? | Ablation: direct single-model/video-to-plan baseline vs two-model + explicit IR and verifier on matched cases |
| Where does it fail? | Per-trial failure taxonomy, missing observations, unsupported tools, runtime outcomes, incomplete postconditions and recovery attempts |

**Do not** claim a completed physical task on the basis of plausible model text, a rendered scene, or keyframe animation. Report measured results only after running the applicable evaluator.

## Hackathon submission checklist

- [ ] Repository is public and the new hackathon work is distinguishable from pre-existing OpenIndustries / Video-to-Workcell work.
- [ ] Submission explicitly identifies **Element 119** as the primary track.
- [ ] Two Gemini 4 models with separately demonstrated responsibilities and logged identifiers.
- [ ] Video/image/audio/document content is central, not a conventional text-only chatbot.
- [ ] At least one real, unrehearsed input and a demonstrated multimodal advantage over text alone.
- [ ] Stress test with difficult media and a visible failure/boundary analysis.
- [ ] Independently check outcomes; label simulation vs physical execution accurately.
- [ ] Show a three-minute live demo and prepare a one-minute submission video, consistent with the participant guide.
- [ ] If seeking the Managed Agents bonus, demonstrate actual use of the hosted agent runtime rather than simply calling it “managed.”
