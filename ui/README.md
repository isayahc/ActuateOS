# Video-first workbench

## Start

Requires Python 3.10+, Node.js 22+, Git, FFmpeg and ffprobe.

```bash
npm install
npm run setup
# Set GEMINI_API_KEY in .env (see example.env)
python3 ui/server.py
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

**Analyze video & build workcell** starts two real, potentially billable managed-agent
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
