"""Collect reproducible Ruff evidence without importing application dependencies."""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


def run_ruff(command, root):
    return subprocess.run(command, cwd=root, capture_output=True, check=False)


def relative_path(value, root):
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve().relative_to(root.resolve()).as_posix()


def normalize_diagnostics(raw, root):
    diagnostics = json.loads(raw)
    if not isinstance(diagnostics, list):
        raise ValueError("Ruff diagnostics must be an array")
    for item in diagnostics:
        item["filename"] = relative_path(item["filename"], root)
    return sorted(diagnostics, key=lambda item: (
        item["filename"], item.get("code") or "", item["location"]["row"],
        item["location"]["column"], json.dumps(item, sort_keys=True),
    ))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect(root, output, ruff_command=None):
    root = root.resolve()
    output.mkdir(parents=True, exist_ok=False)
    command = ruff_command or ["uvx", "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple", "--from", "ruff==0.17.1", "ruff"]
    common = ["check", ".", "--config", str(root / "pyproject.toml"), "--no-cache", "--no-fix"]
    manifest = {
        "schema_version": 1, "generated_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(), "python": sys.version, "commands": {},
        "status": "collecting", "ruff_exit_code": None, "diagnostic_count": None,
        "dirty": None, "execution_mode": "direct-tool" if ruff_command else "pinned-tool",
    }
    def collect_environment(name, invocation):
        manifest["commands"][name] = invocation
        manifest[name + "_exit_code"] = None
        try:
            result = run_ruff(invocation, root)
        except OSError as error:
            (output / f"{name}.raw.txt").write_bytes(b"")
            (output / f"{name}.stderr.txt").write_text(str(error), encoding="utf-8")
            raise OSError(f"Environment collection {name} could not start: {error}") from error
        (output / f"{name}.raw.txt").write_bytes(result.stdout)
        (output / f"{name}.stderr.txt").write_bytes(result.stderr)
        manifest[name + "_exit_code"] = result.returncode
        if result.returncode:
            raise ValueError(f"Environment collection {name} failed with exit {result.returncode}")
        return result

    try:
        for name in ("pyproject.toml", "uv.lock"):
            manifest[name + "_sha256"] = hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name, args in (("source_commit", ["rev-parse", "HEAD"]),
                           ("working_tree", ["status", "--porcelain=v1", "--untracked-files=all"]),
                           ("diff", ["diff", "--binary", "HEAD"])):
            result = collect_environment(name, ["git", *args])
            value = result.stdout.decode("utf-8", errors="replace").strip()
            if name == "diff":
                manifest["diff_sha256"] = hashlib.sha256(result.stdout).hexdigest()
                (output / "working-tree.diff").write_bytes(result.stdout)
            else:
                manifest[name] = value
        manifest["dirty"] = bool(manifest["working_tree"])
        # git diff does not include untracked files; fingerprint those separately.
        untracked = collect_environment("untracked", ["git", "ls-files", "--others", "--exclude-standard", "-z"])
        manifest["untracked_sha256"] = {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in untracked.stdout.decode("utf-8").split("\0") if name and (root / name).is_file()
        }
        uv = collect_environment("uv_version", ["uv", "--version"])
        manifest["uv_version"] = uv.stdout.decode("utf-8", errors="replace").strip()
        for name, args in (("version", ["--version"]), ("settings", [*common, "--show-settings"]),
                           ("files", [*common, "--show-files"]),
                           ("diagnostics", [*common, "--output-format", "json"])):
            invocation = [*command, *args]
            manifest["commands"][name] = invocation
            result = run_ruff(invocation, root)
            suffix = "raw.json" if name == "diagnostics" else "raw.txt"
            (output / f"{name}.{suffix}").write_bytes(result.stdout)
            (output / f"{name}.stderr.txt").write_bytes(result.stderr)
            manifest[name + "_exit_code"] = result.returncode
            if name == "diagnostics":
                manifest["ruff_exit_code"] = result.returncode
                if result.returncode not in (0, 1):
                    raise ValueError(f"Ruff execution failed with exit {result.returncode}")
                diagnostics = normalize_diagnostics(result.stdout, root)
                if bool(diagnostics) != (result.returncode == 1):
                    raise ValueError("Ruff exit code contradicts diagnostics")
                write_json(output / "diagnostics.json", diagnostics)
                write_json(output / "stats.json", {
                    "by_rule": dict(sorted(Counter(item.get("code") or "syntax-error" for item in diagnostics).items())),
                    "by_path": dict(sorted(Counter(item["filename"] for item in diagnostics).items())),
                })
                manifest["diagnostic_count"] = len(diagnostics)
            elif result.returncode:
                raise ValueError(f"Ruff {name} failed with exit {result.returncode}")
            elif name == "version":
                manifest["ruff_version"] = result.stdout.decode("utf-8").strip()
                if manifest["ruff_version"] != "ruff 0.17.1":
                    raise ValueError("Expected Ruff 0.17.1")
            elif name == "files":
                files = sorted(relative_path(line, root) for line in result.stdout.decode("utf-8").splitlines() if line)
                write_json(output / "files.json", files)
                manifest["scanned_file_count"] = len(files)
        manifest["status"] = "diagnostics" if manifest["ruff_exit_code"] == 1 else "clean"
    except (OSError, ValueError, KeyError, TypeError) as error:
        manifest["status"] = "error"
        manifest["error"] = str(error)
    write_json(output / "manifest.json", manifest)
    return 2 if manifest["status"] == "error" else manifest["ruff_exit_code"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New evidence directory; existing paths are rejected")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output or root / "artifacts" / "ruff" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    try:
        result = collect(root, output)
    except (OSError, ValueError) as error:
        print(f"Evidence could not be saved: {error}", file=sys.stderr)
        return 2
    print(f"Ruff evidence: {output.resolve()} (exit {result})")
    return result


if __name__ == "__main__":
    sys.exit(main())
