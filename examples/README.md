# Gemini Managed Agents smoke test

This sample invokes Google's hosted Antigravity managed agent through the Gemini
Interactions REST API. It uses Python 3.10+ with no third-party dependencies.

## Run

Copy the template from the repository root:

```bash
cp example.env .env
```

Edit `.env` and replace the placeholder with a Gemini API key with Managed Agents
access. `.env` is ignored by Git. Load it and run the sample in Bash:

```bash
set -a
source .env
set +a
python3 examples/managed_agent_smoke.py
```

Alternatively, enter the key interactively without putting it in shell history:

```bash
read -rsp 'Gemini API key: ' GEMINI_API_KEY
export GEMINI_API_KEY
python3 examples/managed_agent_smoke.py
```

The script also accepts `GOOGLE_API_KEY`. It does not load `.env` automatically.
Live calls use your API account and may incur charges.

## What passes mean

1. Provision a remote sandbox using `antigravity-preview-09-2026`.
2. Ask the agent to execute Python and create a uniquely named JSON artifact.
3. Continue with the same conversation and sandbox, updating the existing file.
4. Download the sandbox snapshot through the Files API.
5. Independently verify the file's run ID, number sequence, sum, and completion flag.

The script prints `PASS` only after checking the downloaded file. Agent prose
alone is not accepted as proof. Responses, IDs, snapshot, and verified result are
saved under ignored `artifacts/managed-agents/<run-id>/` directories.

Each turn is polled for up to ten minutes, plus any in-flight HTTP request time.
Timeouts do not cancel remote execution; inspect the saved interaction ID before
starting another run. API errors and invalid artifacts return a nonzero exit code.

Override the preview agent ID when Google updates it:

```bash
python3 examples/managed_agent_smoke.py --agent YOUR_AGENT_ID
```

This is a runtime smoke test, not the Video-to-Workcell pipeline. In particular,
Google's current managed-agent documentation lists text and image inputs; native
video ingestion requires a separately verified integration strategy.

## Sources

- [Managed Agents quickstart](https://ai.google.dev/gemini-api/docs/managed-agents-quickstart)
- [Antigravity agent and background execution](https://ai.google.dev/gemini-api/docs/antigravity-agent)

## Verification status

The live runtime smoke test passed: both turns completed, the sandbox persisted,
and the downloaded JSON matched the run ID, sequence, sum 28, and completion flag.
Local evidence is under
`artifacts/managed-agents/63dab2b91b674872b733caf1348d24b1/` (ignored by Git).

## Workcell planning trial

This trial gives one managed agent a short assembly procedure, operation catalog,
and equipment inventory from `fixtures/cap_assembly.json`. The agent writes a task
graph and scheduled machine assignments. A local validator checks the downloaded
plan independently using the fixture's trusted operation semantics.

With credentials loaded as above:

```bash
python3 examples/workcell_trial.py
```

Checks cover operation completeness, mandatory dependency edges, dependency timing,
machine capabilities, fixture existence, resource conflicts, fixed durations,
symbolic preconditions, and final-state predicates. All operations reserve the
same fixture, so the accepted schedule is sequential. Agent-supplied effects are
never used by the evaluator.

Run offline validator tests:

```bash
python3 -m unittest discover -s examples -p 'test_*.py' -v
```

Tests include both valid loading orders and rejection of missing operations,
unsupported equipment, resource overlap, missing dependencies, invalid timings,
cyclic dependencies, missing initial objects, and fabricated effects.

### First live result

One trial passed on the first generated plan with `antigravity-preview-09-2026`:

| Operation | Machine | Required predecessors | Start | Duration |
| --- | --- | --- | --- | --- |
| Load base | `robot_1` | None | 0 s | 2 s |
| Load cap | `robot_1` | None | 2 s | 2 s |
| Seat cap | `press_1` | Load base, load cap | 4 s | 3 s |
| Inspect | `camera_1` | Seat cap | 7 s | 1 s |

The independent evaluator reported zero violations and a symbolic final state of
`assembly=seated`, `inspection=passed`. The 8-second makespan comes from declared
toy operation durations; it is not measured robot or API execution time.

Run ID: `f5cd40498e074e148e22950399835f71`. The prompt, input task, API response,
sandbox snapshot, generated plan, and validation trace are saved locally under
`artifacts/workcell-trials/<run-id>/` and ignored by Git.

This is one text-grounded, single-agent planning trial. Inspection success is a
declared deterministic transition, not a camera measurement. This trial does not
evaluate video understanding, multi-agent performance, geometry, contact dynamics,
OpenIndustries execution, or physical task completion.
