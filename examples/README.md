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

Live E2E verification is pending API credentials. Local syntax and missing-key
behavior can be checked without making paid calls; neither establishes API access.
