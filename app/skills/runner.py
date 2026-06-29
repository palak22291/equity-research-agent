"""Helper to invoke skill scripts as subprocesses (the canonical execution path).

Each skill script under app/skills/ reads a JSON object from stdin and prints a JSON
result to stdout. Routing the agent tools through this runner keeps the deterministic
financial math in the skill scripts rather than duplicated in the agent files, so the
agents demonstrably *use* the Agent Skills.
"""
import json
import subprocess
import sys
from pathlib import Path

# app/skills/runner.py -> project root is parents[2]
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_skill(script_relpath: str, input_data: dict, timeout: int = 60) -> str:
    """Invoke a skill script with input_data as stdin JSON; return its stdout JSON.

    Args:
        script_relpath: path relative to the project root, e.g.
            "app/skills/ratio-analysis/scripts/calculate_ratios.py".
        input_data: dict serialised to JSON and piped to the script's stdin.
        timeout: seconds before the subprocess is killed.

    Returns:
        The script's stdout (a JSON string). On an unexpected non-zero exit, returns a
        JSON error string. (Skill scripts print handled errors to stdout as JSON and
        exit 0, so those pass straight through.)
    """
    script = _PROJECT_ROOT / script_relpath
    # Surface skill invocations in the pipeline logs (stderr is captured alongside
    # stdout when the pipeline is run), so it's visible that the Agent Skills run.
    print(f"[skill] invoking {script_relpath}", file=sys.stderr, flush=True)
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            cwd=str(_PROJECT_ROOT),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Skill {script_relpath} timed out after {timeout}s"})

    out = proc.stdout.strip()
    if proc.returncode != 0:
        # Handled errors are printed to stdout as JSON; an unexpected crash lands in stderr.
        if out:
            return out
        return json.dumps({"error": (proc.stderr or "skill failed with no output").strip()})
    return out
