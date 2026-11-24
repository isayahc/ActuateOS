# Scene-bound task execution

The default live mode executes a validated task graph against one persistent MuJoCo
world. Selecting a video subtask only changes the reference being reviewed. Browser
polling reads state; a server worker owns the physics clock. Reopening the same run
reconnects to its execution while that server remains running.

## Data flow

1. Video analysis produces evidence-linked steps and dependencies.
2. Scene design proposes equipment and geometry appropriate to those steps.
3. Storyboard generation produces visual reference segments, explicitly separate
   from execution.
4. A managed-agent interaction writes `runtime-plan.json`, binding task IDs to
   scene objects, supported skills, targets and verification scopes. Validation
   rejects missing references, cycles, invalid geometry and dropped observed
   dependencies. Every observed step must be represented, even if unsupported.
5. The runtime dispatches ready tasks serially through one shared arm. A task can
   unlock its dependents only after the skill's measured verifier passes.
6. OpenIndustries renders the actual body and joint states. It never supplies
   the live controller with animation keyframes.

The default video input remains the IndustReal benchmark recording. This change
removes demo-specific execution bindings and prescriptive equipment requirements;
it does not add arbitrary video upload or make all physical tasks executable.

## Contract

An illustrative contract for an observed step `prepare` followed by `assemble`:

```json
{
  "version": 1,
  "robot_id": "handling_arm",
  "robot_profile": "parallel_gripper_v1",
  "initial_positions": {"component_a": [0.0, 0.8, -0.1]},
  "tasks": [
    {
      "id": "stage_component",
      "step_id": "prepare",
      "title": "Stage component for assembly",
      "skill": "pick_place",
      "object_id": "component_a",
      "target": {"id": "staging_position", "position": [0.12, 0.8, -0.1]},
      "position_tolerance_m": 0.025,
      "speed_tolerance": 0.05,
      "scope": "Component released and settled at the proposed staging position",
      "depends_on": []
    },
    {
      "id": "join_component",
      "step_id": "assemble",
      "title": "Join the staged component",
      "skill": "insert",
      "scope": "Insertion and assembled fit would need independent verification",
      "reason": "No insertion controller or fit verifier is implemented",
      "depends_on": ["stage_component"]
    }
  ]
}
```

All step and object IDs must exist in the run. Task IDs, equipment names and target
IDs are data, not recognized magic strings. Coordinates are SI meters, Y-up;
targets and initial positions are workpiece body origins (bottom-center), not
end-effector positions. Initial overrides can only affect bound movable workpieces.
Other bodies use their compiled scene poses. Starting poses are proposals, not
measurements inferred from animation. Repeated tasks on a workpiece use its current
physical pose, never its initial position again.

The validator preserves observed dependencies: each task must transitively depend
on every task assigned to each prerequisite observed step. A staging task cannot
silently stand in for a later unsupported assembly operation.

## Supported adapter and verification

`parallel_gripper_v1` is the existing **schematic six-joint arm**, placed at the bound
robot instance. Its dimensions and gains are fixed adapter assumptions; it is not
an automatic conversion of an arbitrary proposed robot into a validated robot model.
Only unrotated proposed robot instances are accepted.

The current `pick_place` skill accepts unrotated, single-box proposed workpieces:
width 8–70 mm, height 15–35 mm, depth 20–150 mm. It computes IK and collision-checked
paths from current joints and object poses, then uses actuators and friction contact.
It checks bilateral finger contact, lift, release, final position and settling.
The position threshold is at most 25 mm; the combined generalized-velocity norm
threshold is at most 0.05 (the existing adapter criterion, not a physical metrology
standard). Each task has a 120 simulated-second execution budget.

No grasp welds, mocap guides or object-pose assignments drive live manipulation.
All supported movable workpieces coexist in the same physics world. Original
catalog print sets remain visual-only; proposed static equipment uses the existing
collision approximation. Reachability is checked during planning and can fail.

Insertion, fastening, tool changes, inspection and assembly verification have no
implemented skills. Unknown skill names remain `unsupported`, with a required
reason. Their dependent tasks become `blocked`. Independent branches may continue.
Failure is not retried automatically. A fresh execution is an explicit operator
action and preserves the old evidence.

Execution is `completed` only when every task succeeds; an unsupported or failed
branch prevents full completion. A task result establishes only the implemented pick/place checks, never hardware
or full-assembly success. Agent-authored task scopes remain proposals; the runtime
reports its fixed verification scope separately from that proposed scope. The
contract does not independently prove semantic equivalence to the human procedure.

## Controls, lifecycle and evidence

- **Run task graph:** start the saved contract; no provider request or API key is
  needed during deterministic dispatch. The plan-generation interaction is billable.
- **Run with Gemini decisions:** retain the observe/act/reobserve agent loop for
  each ready task (billable, requires a Gemini key). The scheduler waits for both
  measured placement and the agent thread to finish before unlocking dependencies
  or rebinding the shared world. Provider failure blocks that task. Agent turns
  and camera evidence are saved under `task-NNN/` within the execution directory.
- **Pause / Resume:** suspend or resume scheduling and physics together.
- **New execution / reconnect:** explicitly cancel the current execution and create
  a fresh world. Merely reloading the page reconnects without resetting it.
- Switching reference subtasks, seeking the video, changing view mode or closing
  the browser does not advance or reset a live execution.
- Idle sessions expire after five minutes without client activity. Running work
  continues to a terminal task-graph state. Server shutdown cancels workers.

`artifacts/robot-executions/<session>/` contains `runtime-plan.json`, `model.xml`,
`initial-state.json`, sampled `trajectory.jsonl`, and atomic `state.json` snapshots
with task outcomes and events. Unsupported-only plans do not create a physics model.
Snapshots are evidence, **not crash recovery checkpoints**: a server restart does
not resume an interrupted physical world. The old evidence remains available.

The legacy guided-parts mode still follows animation via mocap guides and is
explicitly labeled as a separate comparison baseline.

## Existing runs and verification

Old runs do not silently fall back to the step-1 demo. Generate a contract for an
existing compiled run (requires a Gemini key in the environment):

```bash
.venv-mujoco/bin/python scripts/plan_runtime.py RUN_ID
```

Review `runtime-plan.json`, then use the dashboard or the historical headless entry
point (now dispatches the graph without making provider calls):

```bash
.venv-mujoco/bin/python scripts/run_robot_agent.py RUN_ID
npm test
npm run test:runtime:browser
```

The browser test starts its own local server and Chromium (`CHROMIUM_BIN` can
override its path), compiles a native OI test scene, executes two tasks, checks
pause/resume, reference selection, navigation/reconnection and final results.
It uses arbitrary non-demo IDs and no downloaded dataset or provider calls.
The default button uses deterministic skill dispatch; the optional Gemini button
retains online model decisions. Both paths share the same task graph and physics.
Unit tests cover failed grasps, unreachable/blocked targets, replanning, DAG
validation and unsupported-task propagation. Three legacy guided-physics tests
require saved IndustReal artifacts and are skipped when those artifacts are absent.

### Geometry origins and grasp targets

Targets remain world-space **body origin** positions. The gripper aims at the
center of the compiled box vertices, including the part-local offset; it does
not assume that the body origin sits beneath the box center. Pickup uses the
measured body transform, while placement converts the requested unrotated body
origin to the corresponding box center. Transfer and retreat retain that offset.
Changing an asset origin without changing its world geometry must not break a
previously feasible contact grasp. This does not add rotated-workpiece support.
