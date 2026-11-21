# Gemini 4 model routing

The application explicitly uses two of the four core Gemini 4 models:

| Stage | Model | Reason |
| --- | --- | --- |
| Video reconstruction | `gemini-4-hydrogen` | Multimodal observation and structured extraction |
| Workcell design | `gemini-4-carbon` | Reasoning across equipment, geometry and assumptions |
| Reference segment authoring | `gemini-4-carbon` | Cross-step scene consistency |
| Runtime task binding | `gemini-4-carbon` | Dependency and skill-contract reasoning |
| Visual endpoint comparison | `gemini-4-hydrogen` | Evidence-grounded visual review |
| Robot observe/act/reobserve | `gemini-4-hydrogen` | Repeated bounded decisions from live state |

`antigravity-preview-09-2026` is the agent harness identifier, not the core
model identifier. The shared client sends:

```json
{"agent":"antigravity-preview-09-2026","agent_config":{"type":"antigravity","model":"gemini-4-carbon"}}
```

The model is selected explicitly at every application call site. Provider errors
propagate rather than falling back to another model. Existing saved runs retain
their original evidence; they are not relabeled as two-model runs. Generate a new
run to exercise the complete two-model pipeline.

## Verification

With `GEMINI_API_KEY` exported, independently test both configured models:

```bash
python3 examples/managed_agent_smoke.py --model gemini-4-hydrogen
python3 examples/managed_agent_smoke.py --model gemini-4-carbon
```

Each smoke test performs two real API interactions, reuses its remote sandbox,
downloads its artifact, and checks its exact contents. It is not an end-to-end
video or robot execution test.

Live checks passed on 2026-11-21:
- Hydrogen: `artifacts/managed-agents/c7dbf570856b4211a2e0a5acb2a5b31e/`
- Carbon: `artifacts/managed-agents/1ff24717eed54df7bafe7eb724781df5/`

`model-<turn>.json` records the requested model, returned agent configuration
(when supplied), interaction ID and completion status. `turn-<turn>.json` retains
the unmodified provider response; requested routing is not a model self-report.

## Official sources

- [Antigravity model selection](https://aistudio.google.com/docs/antigravity-agent#model-selection): Hydrogen is the default; all four Gemini 4 models are supported via `agent_config.model`.
- [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models): exact core model IDs and capabilities.
- [Gemini 4 NYC Hackathon](https://cerebralvalley.ai/e/gemini-4-nyc): event context for Argon, Carbon, Neon and Hydrogen.
