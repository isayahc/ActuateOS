# Saved IndustReal demo runtime migration

The saved run `7ab1900b51ad4600ba9305d9d345a111` predates the explicit
task-graph runtime. Its `runtime-plan.json` is intentionally tracked as a small
compatibility artifact; the recording, generated scenes and execution evidence
remain local artifacts.

The plan requires that run's original `analysis.json`,
`segmented-scene-spec.json` and `segmented-workcell.oi.json`. It binds the existing
`robot_arm` and single-box `proxy_cross_block` to a contact-verified staging task.
The initial position and staging target are explicit engineering assumptions.
This plan was authored locally; it is not attributed to Carbon or to observed
human motion. It contains no motion tracks. Runtime IK and contact physics
determine execution from the current state.

Frame joining, fastening, axle insertion and final assembly are explicitly
unsupported, preserving the observed dependency graph. After staging succeeds,
the graph reports blocked rather than claiming full assembly success.

## Run

Restart the server after updating Python runtime code:

```bash
npm start
```

Open http://127.0.0.1:5187/?run=7ab1900b51ad4600ba9305d9d345a111 and press
**Play segment**. The default uses Hydrogen's managed-agent decisions. Advanced
inspection also offers the validated task dispatcher without provider calls.

## Verification

On 2026-11-21 the task was executed headlessly through `TaskExecution` with the
real saved scene and MuJoCo physics. Staging succeeded with a position error of
`0.001310321991702673` meters. This check used the task dispatcher, not a live
Gemini decision loop. The running HTTP server's `/api/runtime/connect` and
`/api/runtime/state` endpoints also returned a ready task-graph session.
