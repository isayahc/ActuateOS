# Video-first workbench

## Start

Requires Python 3.10+, Node.js 22+, Git, FFmpeg and ffprobe.

```bash
npm install
npm run setup
# Set GEMINI_API_KEY in .env (see example.env)
python3 -m venv .venv-mujoco
.venv-mujoco/bin/python -m pip install -r requirements-mujoco.txt
.venv-mujoco/bin/python ui/server.py
```

Open **http://127.0.0.1:5187**. Use `--port 5188` to choose another port. Setup
downloads the selected real IndustReal recording, its labels and geometry, pins
the upstream OpenIndustries checkout, and builds the renderer. It does not make
Gemini API calls.

## What you see

1. **Video:** IndustReal v2 test recording `03_assy_0_1`, 275.4 seconds, with
   sampled-frame thumbnails. The source MPEG-4 Part 2 video is re-encoded to H.264
   for browser playback, without changing its timing.
2. **Analysis:** Gemini's timestamped reconstruction from 48 uniformly sampled
   frames. Click a step to seek the video. Uncertainty is shown per step. This is
   sampled-frame analysis, not full-rate video/audio understanding.
3. **Workcell:** the second Gemini managed agent's proposed equipment, primitive
   geometry and placements, rendered through OpenIndustries' actual `createWorld`.
   Drag to orbit, scroll to zoom, or click an object. Selecting an analysis step
   highlights all equipment the scene agent linked to it.

Blue-bordered object buttons identify original IndustReal 3MF print-set geometry.
Other objects are Gemini-authored proposals, not dataset equipment or validated
machines. The source geometry consists of multi-part print sets, not a reconstructed
assembled vehicle. Download the native `.oi.json` scene for the OpenIndustries workbench.

The reference section shows dataset completion labels alongside the nearest
predicted completion by time. Labels are withheld from both agents. Temporal
proximity is a debugging aid, **not** semantic accuracy or a benchmark score.

## Runs

**Analyze video & build workcell** starts five real, potentially billable managed-agent
interactions. The server loads credentials from its environment or `.env`; no key
is sent to the browser. Progress refreshes every 2.5 seconds. Existing results can
be viewed without credentials. No prebuilt scene replaces a failed model result.

Generated frames, prompts, agent responses, sandbox snapshots, analysis, comparison,
scene specification, portable scene, and validation report are stored under
`artifacts/video-workcells/<run-id>/`. The UI reads these artifacts. The old toy-test
dashboard remains at **/runs**, labeled separately.

The server is loopback-only and serves allowlisted assets. Stopping it does not
cancel an existing remote Gemini interaction. An interrupted run may require
checking its saved interaction IDs; it is not automatically retried.

## Verification

```bash
npm test
# With the app and a Chromium debugging endpoint on :9225 running:
npm run test:browser
```

The browser test makes no paid calls. It checks the already-generated result:
source-video decoding, native WebGL rendering, genuine source geometry, timestamp
seeking, equipment highlighting, nine reference labels, portable export, and mobile
layout. Evidence is saved under `artifacts/ui-evidence/`.

The real live run and its limitations are documented in
[the IndustReal example report](../docs/industreal-example.md).
# Linked subtask playback

## Live task graph (default)

The dashboard opens with live robot planning already selected. Click **Play segment**: it requests Gemini's decisions and starts the ready tasks in the run's `runtime-plan.json`, in dependency order. The same button becomes **Pause segment / Resume segment**, then **Run again** after completion (or **Retry segment** after failure). Planning and verification have explicit progress states, and repeated clicks cannot start duplicate decisions. Unsupported skills remain explicit and block dependent tasks. The human video has its own native controls and clock; selecting a reference step does not select or reset an independent robot execution.

**Advanced inspection** contains reference animation modes, execution reset, detailed logs, and an optional **Validated task dispatcher** policy that executes the saved plan without new provider calls. The default remains Gemini's billable observe/act/reobserve loop for each ready task; the next task waits for measured success and the current review. No advanced controls are required for default playback. Previous execution evidence remains on disk.

The world persists across task selection and page reloads. **Pause / Resume**
controls execution independently of video playback. **New execution / reconnect**
explicitly cancels the old session and creates a fresh world. Unsupported skills
remain visible and block dependent tasks rather than playing an animation as proof
of execution. Existing runs require an explicit runtime plan before using live mode.

See [the contract, capabilities, migration and evidence documentation](../docs/task-runtime.md).
The fixed schematic arm currently supports unrotated single-box pick-and-place;
it does not provide arbitrary robot models, insertion, fastening or assembly skills.

```bash
# Existing compiled run; this planning command uses the configured Gemini API key:
.venv-mujoco/bin/python scripts/plan_runtime.py RUN_ID
# Execute its saved plan without additional provider calls:
.venv-mujoco/bin/python scripts/run_robot_agent.py RUN_ID
npm test
npm run test:runtime:browser
```

## MuJoCo setup

```bash
python3 -m venv .venv-mujoco
.venv-mujoco/bin/python -m pip install -r requirements-mujoco.txt
npm run build
.venv-mujoco/bin/python ui/server.py
```

Open http://127.0.0.1:5187 and click **Play segment**. In the explicitly selected advanced reference modes, the button instead says **Play reference**. The OI renderer displays MuJoCo body states; browser keyframes are disabled in both physics modes. **Authored storyboard** explicitly selects the earlier animation.

For comparison, the **legacy** `Simulation` in `ui/mujoco_runtime.py` uses free workpiece bodies controlled by compliant welds to scripted mocap targets at 200 Hz, with a static arm. The new `RobotSimulation` uses articulated actuation at 500 Hz and contact-only grasping. The live adapter binds objects from the selected run; its robot mechanics remain a fixed supported profile.

In legacy mode, each selected segment initializes its authored starting state and rewinding reintegrates it. Live robot execution has an independent clock: video scrubbing does not rewind the robot. Saved OI animation exports remain the authored storyboard, not a robot execution program.

Verify physics with `.venv-mujoco/bin/python scripts/test_mujoco_runtime.py`. It exercises every real segment, contacts, deterministic rewind, pause, independent sessions, input bounds, and freefall with guide constraints disabled. `node scripts/test_video_ui.mjs` additionally verifies live physics reaches the native OI viewer, play/pause/rewind, segment switching and mobile layout.

On the video dashboard at http://127.0.0.1:5187, each reconstructed subtask has a matching native OI animation segment. Numbered chips select an interval; Play, scrub, previous/next and Loop control the video and scene together. The comparison below shows actual video and OI before/after images with a separate Gemini review of correspondences, differences and uncertainty. Download the selected animated segment independently.

Full generation uses five managed-agent interactions: video analysis, workcell design, segment authoring, runtime task binding and visual endpoint review. Keep the dashboard server running during generation: the review captures its actual WebGL renderer. Set `APP_URL` if using a port other than 5187; `CHROMIUM_BIN` can select the capture browser. Scene motion is a schematic workpiece replay; equipment and original print-set inventory remain stationary.
