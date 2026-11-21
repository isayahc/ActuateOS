# First real IndustReal video-to-workcell example

## Source and selection

- Dataset: **IndustReal v2**, DOI [10.4121/b008dd74-020d-4ea4-a8ba-7bb60769d224.v2](https://doi.org/10.4121/b008dd74-020d-4ea4-a8ba-7bb60769d224.v2).
- Recording: **03_assy_0_1**, original **test split**, 275.4 seconds, 1280×720, 10 FPS.
- Task: human assembly of a STEMFIE construction-toy car.
- Dataset authors: Tim J. Schoonbeek, Tim Houben, Hans Onvlee, Peter H. N. de With,
  and Fons van der Sommen. Dataset license: **Apache-2.0**.
- [Source repository and recording documentation](https://github.com/TimSchoonbeek/IndustReal).
- Selected because it is publicly documented as a successful assembly demonstration,
  and its actual video, annotations, and geometry are downloadable. This is an
  exploratory example, not a blinded evaluation across the test split.

`scripts/prepare_industreal.py` retrieves only the selected ZIP members using HTTP
byte ranges, instead of downloading the full multi-GB archives. ZIP CRC checks and
local SHA-256 hashes are retained. The original video remains unchanged. A separate
H.264 derivative enables browser playback at the original timing.

| Source file | SHA-256 |
| --- | --- |
| `03_assy_0_1.mp4` | `ce7d03f9144c4235ab3e6608bd4c8056d447d0dc1727239970a764392b13763a` |
| `AR_labels.csv` | `ccc59a16520720a3db2002245fb0fe4537b67b8da19e24936814171f5a049939` |
| `PSR_labels.csv` | `75f5ecc65ebe85281d02f0ca33f637f81058149e2f44cc283d0ba113b80e8e9e` |
| Beams Braces 3MF | `f67b91157f9241170243de1b7e818534f85ddf712115506244fb8bc33fddcb98` |
| Screws Pins 3MF | `b6ef115ce5384fc86bcb62cbc2227612d4d5c5281b5758c8dae13833fca9403c` |
| Sign Nuts Washers Pulley 3MF | `462a1a31040f4d4455653e1ea6b0a5650ff70a588fa3c749265670eb04cdb92d` |
| Wheels 3MF | `7f037ed2be58183ee4ced379199f3273f9ceac7d5314bce468c552db43de3b41` |

Full archive URLs, member paths and hashes are generated in
`data/industreal/provenance.json`.

## Pipeline actually executed

1. Extract **48 uniformly sampled frames**, approximately 5.86 seconds apart,
   from the source recording. Save frame timestamps and hashes.
2. Send images and timestamps to a **Gemini Managed Agent**
   (`antigravity-preview-09-2026`). Download its `analysis.json` sandbox artifact.
   The agent does not receive the dataset labels, filename, or annotations.
3. Validate analysis structure, timestamp bounds, references, and graph acyclicity.
   Compare completion times with the reference PSR labels for manual inspection.
4. Send the analysis and source-geometry catalog to a **second managed-agent
   interaction with a fresh sandbox**. It chooses equipment, dimensions, primitive
   geometry, placement, and links from observed steps to proposed equipment.
5. Compile its `scene-spec.json` using pinned **OpenIndustries** APIs:
   `finalizeAsset`, `makeManifest`, `readManifest`, and `hydrateManifest`.
6. Render the exported native `astra.scene` v1 manifest using OpenIndustries'
   **`createWorld`**, with orbit controls and equipment selection in the local UI.

No reference PSR/AR labels enter either agent's prompt. AR labels are downloaded
for future evaluation; the current comparison UI uses PSR completion labels only.
The first agent uses images because the managed-agent input API supports text and
images; this run does not use a native continuous-video model call or audio.

### Geometry and renderer provenance

OpenIndustries source is fetched at revision
`838ea330296148621f7a23f7cb647b11e73b5184`, with the source checkout kept under
ignored `.deps/`. This directly uses upstream renderer and scene validation code;
it is not a screenshot, generic replacement renderer, or a full embedded workbench.
OpenForma is not called by this example.

The four original 3MF mesh sets retain their topology. The adapter converts
millimeters to meters, applies the dataset's documented 200% print scale, rotates
Z-up into Y-up, and normalizes each asset's origin. The sets contain multiple
components in a print layout. They are shown as inventory on the proposed bench;
they are not semantically separated into individual parts or assembled into a car.
Equipment and fixtures are agent-designed conceptual primitives.

## Observed result

Live run: **`7ab1900b51ad4600ba9305d9d345a111`**.

- Both managed-agent interactions completed and their actual files were retrieved.
- Reconstruction: **7 coarse steps**, from joining beams through axle/wheel
  subassemblies and final chassis fastening.
- Reference: **9 PSR completion labels**. These have different granularity; the
  reconstruction is not an exact reproduction of the reference procedure.
- Scene: **10 instances** — 4 original dataset geometry sets and 6 proposed
  equipment objects.
- Native OI schema/geometry hydration: accepted, with no room-bound warnings.
- All seven analysis steps link to scene objects.
- Browser checks passed for video decoding/seeking, 3D rendering, linked selection,
  reference comparison, portable scene download, and a 390px mobile layout.

### What the comparison says (and does not say)

Nearest predicted completion-time offsets were −18.42 seconds for the two labels
at 47.7 seconds, +3.06 seconds at 67.2 seconds, +2.71 seconds for the two labels at
114.4 seconds, +4.30 seconds at 165.5 seconds, and +6.30 seconds for the three labels
at 268.9 seconds. These are **temporal diagnostics only**. Nearest-time association
can pair semantically different actions. No precision, recall, or benchmark score
is claimed from this mapping.

The output explicitly notes occluded pin insertions, unknown fastening torque,
motion blur, and missed intermediate motions. Model interpretations such as a
"pink cap" are unverified semantic labels, not established component identities.

The workcell is a proposal. Schema validity is not proof of feasible grasping,
collision clearance, reach, fixtures, contact, fastener tooling, or task execution.

## Local evidence

`artifacts/video-workcells/7ab1900b51ad4600ba9305d9d345a111/` includes the frame
manifest, agent prompts/responses, snapshots, analysis, reference comparison,
scene specification, native `.oi.json` scene, and validation report.
`artifacts/ui-evidence/` contains browser screenshots and checks. Raw media,
credentials, geometry, and runtime artifacts are ignored by Git.
# Per-subtask animated scenes and visual comparisons

The saved real run `7ab1900b51ad4600ba9305d9d345a111` now includes seven native OpenIndustries animation segments, one for each reconstructed video subtask. Select a numbered segment to play or scrub its video interval and scene together. Playback stops at the interval boundary unless Loop is enabled. Each segment has before/action/after descriptions and an animated OI manifest download.

A third Gemini managed-agent interaction authored schematic moving workpiece proxies. The four original IndustReal print sets remain stationary reference inventory. The compiler validates segment coverage, native timelines, object mappings and cross-segment pose continuity. These checks do not establish physical execution.

A fourth, separate Gemini interaction reviewed 28 images: video-before/after and actual native OI-before/after for all seven segments. Results: three `consistent_at_coarse_level`, two `partial`, one `uncertain`, and one `not_represented`. In particular, step 2's fastening change is not visible in the rendered endpoint views. The UI presents these mismatches rather than treating timestamp alignment as success. Endpoint review cannot establish intermediate motion, contact, torque or robot feasibility.

Artifacts include `segments-spec.json`, `segments.json`, `segmented-workcell.oi.json`, `segment-comparison.json`, and hashed images in `segment-evidence/`. New full pipeline runs automatically perform all four interactions. Regenerate only the comparison with `python3 scripts/compare_segments.py RUN_ID` while the app is running and the API key is loaded.

Verification: `node scripts/test_segments.mjs` checks valid native compilation and rejection of missing segments, discontinuities, invalid mappings and nonchanging tracks. `node scripts/test_video_ui.mjs` checks every segment's changing poses/export, synchronized scrubbing, stop/loop, review images and mobile layout against the live app and Chromium debugging port 9225.
