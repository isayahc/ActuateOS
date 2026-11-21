"""Build a native OI scene and run artifacts for the offline browser integration test."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from test_task_runtime import fixture


def prepare(folder: Path) -> None:
    """Compile a synthetic test scene without borrowing the IndustReal demo."""
    folder.mkdir(parents=True)
    values = fixture(folder)
    analysis = values["analysis.json"]
    analysis.update(title="Runtime integration fixture", summary="Two sequential transfers", uncertainties=["Synthetic test geometry"])
    for index, step in enumerate(analysis["steps"]):
        step.update(title=f"Transfer {index+1}", start_s=index*10, end_s=(index+1)*10,
                    evidence="Synthetic test fixture", uncertainty="Not observed video", objects=["Test component"])
    spec = values["segmented-scene-spec.json"]
    spec.update(title="Independent task runtime fixture", room=[4, 4, 3], rationale="Offline integration test", assumptions=["Schematic arm and box"])
    for obj in spec["objects"]:
        obj.update(name=obj["id"], rationale="Test geometry", step_ids=[s["id"] for s in analysis["steps"]])
        part = obj["parts"][0]
        part.update(position=[0, part["size"][1]/2, 0], color=[.5, .65, .75])
    for name, value in (("analysis.json", analysis), ("segmented-scene-spec.json", spec), ("geometry.json", {"assets": []})):
        (folder / name).write_text(json.dumps(value))
    result = subprocess.run(["node", "ui/dist/compile-scene.mjs", str(folder / "segmented-scene-spec.json"),
                             str(folder / "geometry.json"), str(folder / "segmented-workcell.oi.json")],
                            capture_output=True, text=True, check=True)
    manifest = json.loads((folder / "segmented-workcell.oi.json").read_text())
    segments: list[dict[str, Any]] = []
    for step in analysis["steps"]:
        segments.append({"step_id": step["id"], "title": step["title"], "start_s": step["start_s"], "end_s": step["end_s"],
                         "duration_s": 10, "active_object_ids": ["part_42"], "instances": manifest["instances"],
                         "animation": {"duration": 10, "loop": False, "tracks": []},
                         "before": "Reference layout", "action": "Review only", "after": "Reference layout",
                         "differences": ["Test scene, no recorded human"], "object_mapping": [],
                         "structural_checks": {"moving_objects": 0}})
    (folder / "segments.json").write_text(json.dumps({"segments": segments, "assumptions": []}))
    (folder / "validation.json").write_text(result.stdout)
    (folder / "status.json").write_text(json.dumps({"id": folder.name, "phase": "ready", "message": "Offline runtime test"}))


if __name__ == "__main__":
    prepare(Path(sys.argv[1]).resolve())
