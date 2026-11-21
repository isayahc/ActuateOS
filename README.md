# Video-to-Workcell

Turn a human demonstration into a structured procedure, a proposed workcell, and
an explicit task plan that can be tested in simulation.

The current workflow uses one **IndustReal assembly recording**. Gemini analyzes
sampled video frames and proposes the scene; OpenIndustries (OI) displays the
workcell; a server-owned MuJoCo runtime executes supported tasks and records their
results. Task IDs, object bindings, targets and dependencies come from each run's
plan rather than fixed demo names.

**Two Gemini 4 models:** Hydrogen (`gemini-4-hydrogen`) reconstructs video
evidence, compares rendered endpoints, and makes live robot decisions. Carbon
(`gemini-4-carbon`) designs the workcell, authors reference segments, and binds
the runtime task graph. Both run through Antigravity Managed Agents with explicit
`agent_config.model` selection. Each call saves `model-<turn>.json` routing and
completion metadata alongside the raw provider response. See [model routing and
verification](docs/model-routing.md).

**Current boundary:** the runtime has a schematic robot arm with bounded box
pick-and-place support. Other operations are reported as unsupported. A generated
scene or animation does not establish successful assembly or real-world execution.

Follow the steps below in order. Commands assume **Linux or WSL2 with Bash**.

## 1. Install the prerequisites

Have these available before starting:

| Requirement | Used for |
| --- | --- |
| Python 3.10+ with `venv` and pip | Pipeline, local server and MuJoCo runtime |
| Node.js 22+ and npm | OI scene compilation and browser tooling |
| Git | Repository and pinned OI checkout |
| FFmpeg and ffprobe | Video conversion, duration checks and frame extraction |
| Chromium, or a compatible executable selected with `CHROMIUM_BIN` | Capturing scene images during the visual-review stage |
| Gemini API key with Managed Agents access | Generating a new run and optional live agent control |

An API key is not needed to inspect existing results or execute an existing task
plan with deterministic skill dispatch. New analysis and Gemini-controlled
execution make billable provider calls.

## 2. Clone and set up the project

```bash
git clone https://github.com/isayahc/video-to-workcell.git
cd video-to-workcell

python3 -m venv .venv-mujoco
.venv-mujoco/bin/python -m pip install -r requirements-mujoco.txt

npm ci
npm run setup
```

`npm run setup` downloads the selected IndustReal recording, reference labels and
geometry, checks out the pinned OpenIndustries version, and builds the renderer
and scene compilers. Downloads are saved in `data/`; generated dependencies and
build output are ignored by Git. Setup makes no Gemini calls.

Create your local configuration:

```bash
cp example.env .env
```

Edit `.env` and replace the placeholder with your API key:

```dotenv
GEMINI_API_KEY=your_key_here
```

The dashboard server reads `.env` automatically. Keep this file local; it is
ignored by Git. If Chromium has a different executable name or path, set it in
the shell before starting the server:

```bash
export CHROMIUM_BIN=/path/to/chromium
```

## 3. Start the dashboard

```bash
npm start
```

Open **http://127.0.0.1:5187**. Keep the server running while generating a workcell:
the visual-review stage uses it to capture actual OI renders.

For a different port, set the capture URL to match:

```bash
export APP_URL=http://127.0.0.1:5188
.venv-mujoco/bin/python ui/server.py --port 5188
```

## 4. Generate a workcell from the video

Click **Analyze video & build workcell**. The current input is IndustReal recording
`03_assy_0_1`; arbitrary video upload is not implemented.

The pipeline runs in this order:

| Stage | What happens | Main output |
| --- | --- | --- |
| 1. Sample | Extract 48 timestamped frames from the recording | `frames.json` and frame images |
| 2. Reconstruct | Gemini identifies observed steps, evidence, uncertainty and dependencies | `analysis.json` |
| 3. Design | Gemini proposes equipment and layout; the OI adapter compiles the scene | `scene-spec.json`, `workcell.oi.json`, `validation.json` |
| 4. Storyboard | Gemini authors visual reference segments for the observed steps | `segments.json`, `segmented-workcell.oi.json` |
| 5. Bind tasks | Gemini maps tasks to supported skills or explicitly unsupported operations; the contract is validated | `runtime-plan.json` |
| 6. Review | Capture video and OI endpoint images, then ask Gemini to compare them | `segment-evidence.json`, `segment-comparison.json` |

A full generation uses five managed-agent interactions. Progress appears in the
dashboard. If a stage fails, inspect its message and saved artifacts; the system
does not substitute a prebuilt scene or treat the failure as success.

## 5. Review the proposed workcell

Before execution:

1. Select a reconstructed step to inspect its timestamps, evidence and uncertainty.
2. Inspect the equipment linked to that step. Drag to orbit, scroll to zoom, and
   click scene objects for their details.
3. Choose **Authored storyboard** to review the proposed before/action/after sequence.
4. Read the endpoint comparison and its stated differences and unknowns.
5. Inspect `runtime-plan.json` for task dependencies, object bindings, targets,
   verification scopes and unsupported operations.

Original dataset meshes are component print sets. Other scene geometry is proposed
equipment or schematic workpieces. Dimensions and placements are engineering
assumptions unless separately evidenced. Endpoint reviews and nearest-timestamp
label comparisons are debugging evidence, not benchmark accuracy scores.

## 6. Execute the task plan

Choose **Live task graph · online planning**, then select a control mode:

| Control | Behavior |
| --- | --- |
| **Run task graph** | Dispatch ready tasks through supported skills without additional provider calls |
| **Run with Gemini decisions** | Use the billable observe/act/reobserve loop for each ready task |
| **Pause / Resume** | Pause or resume both scheduling and physics |
| **New execution / reconnect** | Explicitly cancel the current session and create a fresh world |

Tasks share one persistent physics world. Dependencies unlock only after verified
success; Gemini mode also waits for the current agent review to finish. Unsupported
or failed prerequisites block dependent tasks. Independent branches may continue.

Changing the selected video step or seeking the video does not reset execution.
Reloading the page reconnects to the same run's session while the server remains
running. The server owns the physics clock, so browser polling does not drive motion.

**Legacy guided parts · static arm** is a separate comparison mode that follows
storyboard targets through physics guides. It is not the live robot task controller.

### Using a run created before runtime plans were added

From the repository root, load your local configuration and generate a contract
for the existing compiled run. Replace `RUN_ID` with its folder name under
`artifacts/video-workcells/`:

```bash
set -a
source .env
set +a
.venv-mujoco/bin/python scripts/plan_runtime.py RUN_ID
```

This command makes a Gemini call. Review the resulting `runtime-plan.json`, then
reconnect in the dashboard. Old animations are never silently converted into
executable tasks.

For headless deterministic execution of a saved plan:

```bash
.venv-mujoco/bin/python scripts/run_robot_agent.py RUN_ID
```

Despite its historical filename, this command dispatches the saved task graph
without additional provider calls.

## 7. Inspect results and understand their limits

| Location | Contents |
| --- | --- |
| `data/industreal/` | Downloaded video, labels, geometry and source provenance |
| `artifacts/video-workcells/<run-id>/` | Frames, prompts, agent responses, analysis, scene files, runtime plan and visual reviews |
| `artifacts/robot-executions/<session-id>/` | Saved plan, physics model and initial state where applicable, trajectories, task outcomes and `state.json` |
| `artifacts/robot-executions/<session-id>/task-NNN/` | Per-task agent decisions and camera evidence when using Gemini control |

The dashboard links to execution state and results. Use its scene download controls
to export native OI manifests. These exports describe scenes/storyboards; execution
evidence is stored separately. Existing results can be reopened without another
analysis request.

Read outcomes at the level they actually establish:

- **Valid scene:** schema and geometry references passed their checks.
- **Successful pick-and-place:** simulated grasp, lift, release, position and
  settling met the implemented checks.
- **Completed task graph:** every bound task succeeded within its implemented
  verification scope. This does not independently prove equivalence to the entire
  human procedure.
- **Unsupported / blocked:** the required controller is missing or a prerequisite
  could not complete; this is not success.

The robot remains a fixed schematic six-joint arm. Its current skill accepts
unrotated, single-box proposed workpieces within documented size limits. Insertion,
fastening, arbitrary robot models, hardware execution and general recovery planning are
not implemented. The optional agent loop has bounded retries within the supported
skill. Saved snapshots are evidence, not crash-recovery checkpoints;
restarting the server does not resume an interrupted physics world.

See [the task contract and capability limits](docs/task-runtime.md) for details.

## 8. Run the checks

After setup, from the repository root:

```bash
npm test
npm run build
```

The tests cover task dependencies, contact execution, failure handling, server
controls and scene compilation without paid API calls. Three legacy physics tests
require saved IndustReal run artifacts and are skipped when those are absent.

To run the self-contained browser integration check, with Chromium installed:

```bash
npm run test:runtime:browser
```

It starts its own local server, compiles a test scene and checks task execution,
pause/resume, reference selection and reconnection. It makes no provider calls.
Environments that prevent Chromium from starting cannot run this check. A passing
offline suite does not establish that live Gemini generation works with your account.

## Troubleshooting

| Symptom | Next action |
| --- | --- |
| Missing dataset or geometry | Run `npm run prepare:data` |
| Missing renderer or compiler | Run `npm run setup:renderer`, then `npm run build` |
| MuJoCo unavailable | Install `requirements-mujoco.txt` into `.venv-mujoco` and start with `npm start` |
| Missing API key | Set `GEMINI_API_KEY` in `.env` for dashboard calls; load it into the shell for direct planning scripts |
| Chromium capture fails | Check `CHROMIUM_BIN`, confirm Chromium can start, and keep the dashboard running at `APP_URL` |
| No `runtime-plan.json` | Follow the existing-run migration in step 6 |
| Task reports unsupported or blocked | Inspect its reason and prerequisites; adding a controller and verifier is required for a new skill |
| Interrupted provider call | Inspect saved interaction IDs before retrying; stopping the local server does not cancel a remote interaction |

## Project background and code map

The research goal is to reduce the engineering effort needed to automate unfamiliar
physical procedures. Generalization, recovery and engineering-effort improvements
still require controlled benchmark evaluation.

The Gemini 4 NYC Hackathon primary track is **Element 119 — Multimodal AI**.
Managed Agents is also an optional bonus target; using the runtime does not establish
prize eligibility or an award. See the [submission requirements](docs/hackathon-element-119.md).

| Read next | Purpose |
| --- | --- |
| [Research overview](docs/research-overview.md) | Motivation, proposed architecture, benchmark foundations and references |
| [Benchmark comparison](docs/benchmark-comparison.md) | Planned measurements and comparisons |
| [Evaluation protocol](docs/evaluation.md) | Experiment records and evaluation discipline |
| [Task runtime](docs/task-runtime.md) | Contract, supported skills, lifecycle and evidence |
| [UI details](ui/README.md) | Additional dashboard and legacy-mode context |
| [IndustReal example](docs/industreal-example.md) | Dataset provenance and earlier example results |
| [Managed Agents smoke test](examples/README.md) | Isolate provider access before a full pipeline run |

| Directory | Responsibility |
| --- | --- |
| `ui/` | Dashboard, HTTP server, task graph and physics controllers |
| `scripts/` | Data preparation, generation pipeline, headless execution and checks |
| `integrations/` | Scene and storyboard compilation into native OI manifests |
| `docs/` | Runtime documentation, research and evaluation plans |
| `examples/` | Provider and symbolic-planning smoke tests |
