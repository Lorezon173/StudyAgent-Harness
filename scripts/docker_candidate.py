"""Bind CI evidence to one saved Docker image; fail closed before publication."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

TECHNICAL = ("structure", "migration", "api-auth")
PHASES = (*TECHNICAL, "api-teaching", "all")
# Publication protocol: keep the minimum checks aligned with verify_docker_image.REQUIRED.
REQUIRED = {
    "structure": {"runtime_resources"},
    "migration": {"pg_empty_and_repeat", "pg_historical_preservation", "pg_reject_missing_mastery",
                  "pg_reject_nonnumeric_user", "pg_reject_orphan_user", "sqlite_upgrade"},
    "api-auth": {"effective_jwt_valid", "health_frontend_auth"},
    "api-teaching": {"effective_jwt_valid", "health_frontend_auth", "real_teaching_restart_ownership"},
    "all": {"structure", "migration", "api-auth", "api-teaching", "candidate_identity"},
}


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("missing or malformed manifest") from exc
    if not isinstance(value, dict):
        raise ValueError("manifest must be an object")
    return value


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def verify(directory, source_sha):
    directory = Path(directory)
    data = read_json(directory / "candidate.json")
    if type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("unsupported candidate version")
    for field, pattern in (("source_sha", r"[0-9a-f]{40}"),
                           ("image_id", r"sha256:[0-9a-f]{64}"),
                           ("archive_sha256", r"[0-9a-f]{64}")):
        if not isinstance(data.get(field), str) or not re.fullmatch(pattern, data[field]):
            raise ValueError("invalid candidate identity")
    if data["source_sha"] != source_sha or data.get("dirty") is not False:
        raise ValueError("candidate source mismatch or dirty")
    if not isinstance(data.get("image_ref"), str) or not data["image_ref"] or data["image_ref"].startswith("-"):
        raise ValueError("invalid image reference")
    archive = directory / "image.tar"
    if data.get("archive") != "image.tar" or archive.is_symlink() or not archive.is_file():
        raise ValueError("invalid archive path")
    if digest(archive) != data["archive_sha256"]:
        raise ValueError("archive checksum mismatch")
    return data


def check_phase(root, phase, candidate):
    data = read_json(Path(root) / phase / "manifest.json")
    if (data.get("phase") != phase or data.get("status") != "passed"
            or type(data.get("exit_code")) is not int or data["exit_code"] != 0
            or data.get("dirty") is not False
            or any(data.get(key) != candidate[key] for key in ("source_sha", "image_id"))):
        raise ValueError("phase failed, missing, dirty, or identity mismatch: " + phase)
    required, checks = data.get("required_checks"), data.get("checks")
    if (not isinstance(required, list) or not required
            or any(not isinstance(name, str) or not name for name in required)
            or len(set(required)) != len(required) or not isinstance(checks, list)):
        raise ValueError("invalid required checks: " + phase)
    if any(not isinstance(check, dict) or not isinstance(check.get("name"), str)
           or not check["name"] or check.get("status") != "passed" for check in checks):
        raise ValueError("nonpassing checks: " + phase)
    names = [check.get("name") for check in checks]
    if (len(set(names)) != len(names) or not REQUIRED[phase] <= set(required)
            or any(names.count(name) != 1 for name in required)):
        raise ValueError("missing or duplicate checks: " + phase)
    if phase == "all" and data.get("archive_sha256") != candidate["archive_sha256"]:
        raise ValueError("aggregate archive checksum mismatch")
    return data


def gate(directory, source_sha, evidence_root):
    data = verify(directory, source_sha)
    for phase in PHASES:
        check_phase(evidence_root, phase, data)
    return data


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def inspect(image):
    return json.loads(run("docker", "image", "inspect", image))[0]


def check_image(data):
    actual = inspect(data["image_id"])
    if (actual.get("Id") != data["image_id"]
            or (actual.get("Config", {}).get("Labels") or {}).get(
                "org.opencontainers.image.revision") != data["source_sha"]):
        raise ValueError("loaded image identity or revision label mismatch")


def pack(directory, source_sha, image, evidence_root):
    if run("git", "rev-parse", "HEAD") != source_sha or run("git", "status", "--porcelain"):
        raise ValueError("packing requires clean matching checkout")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "image_ref": image, "image_id": inspect(image)["Id"],
            "source_sha": source_sha, "dirty": False, "archive": "image.tar"}
    check_image(data)
    for phase in TECHNICAL:
        check_phase(evidence_root, phase, data)
    subprocess.run(["docker", "save", "--output", str(directory / "image.tar"), image], check=True)
    data["archive_sha256"] = digest(directory / "image.tar")
    (directory / "candidate.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return verify(directory, source_sha)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("pack", "load", "verify", "gate"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--image")
    args = parser.parse_args()
    try:
        if args.command == "pack":
            if not args.image or not args.evidence_root:
                raise ValueError("pack requires image and evidence root")
            data = pack(args.directory, args.source_sha, args.image, args.evidence_root)
        elif args.command == "gate":
            if not args.evidence_root:
                raise ValueError("gate requires evidence root")
            data = gate(args.directory, args.source_sha, args.evidence_root)
        else:
            data = verify(args.directory, args.source_sha)
            if args.command == "load":
                subprocess.run(["docker", "load", "--input", str(args.directory / "image.tar")], check=True)
                check_image(data)
        print(json.dumps(data, sort_keys=True))
    except (ValueError, OSError, subprocess.SubprocessError):
        parser.exit(1, "candidate validation failed; publication blocked\n")


if __name__ == "__main__":
    main()
