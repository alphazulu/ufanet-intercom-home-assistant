#!/usr/bin/env python3
"""Static release gate for the Ufanet Intercom custom integration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import py_compile
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "ufanet_intercom"
MANIFEST = COMP / "manifest.json"
CONST = COMP / "const.py"
INIT = COMP / "__init__.py"
JS = COMP / "frontend" / "ufanet-archive-card.js"
SERVICES = COMP / "services.yaml"
HACS = ROOT / "hacs.json"
README = ROOT / "README.md"
README_RU = ROOT / "README_RU.md"

ERRORS: list[str] = []
WARNINGS: list[str] = []


def error(message: str) -> None:
    ERRORS.append(message)


def warning(message: str) -> None:
    WARNINGS.append(message)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        error(f"invalid JSON {path.relative_to(ROOT)}: {exc}")
        return {}


def extract(pattern: str, text: str, label: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        error(f"unable to find {label}")
        return None
    return match.group(1)


def check_versions() -> None:
    manifest = load_json(MANIFEST)
    manifest_version = str(manifest.get("version") or "")
    const_text = CONST.read_text(encoding="utf-8")
    init_text = INIT.read_text(encoding="utf-8")
    js_text = JS.read_text(encoding="utf-8")
    readme_text = README.read_text(encoding="utf-8")
    readme_ru_text = README_RU.read_text(encoding="utf-8")

    python_version = extract(r'^INTEGRATION_VERSION\s*=\s*["\']([^"\']+)', const_text, "INTEGRATION_VERSION")
    card_version = extract(r'^const CARD_VERSION\s*=\s*["\']([^"\']+)', js_text, "CARD_VERSION")
    cache_version = extract(r'_ARCHIVE_CARD_MODULE_URL\s*=.*?\?v=([0-9A-Za-z._-]+)', init_text, "frontend cache-bust version")
    resource_pattern = r'/ufanet_intercom/ufanet-archive-card\.js\?v=([0-9A-Za-z._-]+)'
    readme_version = extract(resource_pattern, readme_text, "README Lovelace resource version")
    readme_ru_version = extract(resource_pattern, readme_ru_text, "README_RU Lovelace resource version")

    versions = {
        "manifest": manifest_version,
        "python": python_version,
        "card": card_version,
        "cache": cache_version,
        "readme": readme_version,
        "readme_ru": readme_ru_version,
    }
    present = {value for value in versions.values() if value}
    if len(present) != 1:
        error(f"version mismatch: {versions}")


def check_python() -> None:
    with tempfile.TemporaryDirectory(prefix="ufanet-release-check-") as tmp:
        for path in sorted(COMP.glob("*.py")):
            try:
                py_compile.compile(str(path), cfile=str(Path(tmp) / (path.stem + ".pyc")), doraise=True)
            except Exception as exc:
                error(f"Python compile failed for {path.name}: {exc}")


def check_json() -> None:
    for path in [MANIFEST, HACS, COMP / "strings.json", *sorted((COMP / "translations").glob("*.json"))]:
        if path.exists():
            load_json(path)


def check_js() -> None:
    node = shutil.which("node")
    if node:
        result = subprocess.run([node, "--check", str(JS)], capture_output=True, text=True)
        if result.returncode:
            error("node --check failed: " + (result.stderr.strip() or result.stdout.strip()))
    else:
        warning("Node.js not installed; skipped JavaScript parser check")

    text = JS.read_text(encoding="utf-8")
    calls = set(re.findall(r'this\.(_[A-Za-z][A-Za-z0-9_]*)\s*\(', text))
    definitions = set(re.findall(r'^\s{2}(?:async\s+)?(_[A-Za-z][A-Za-z0-9_]*)\s*\(', text, re.MULTILINE))
    missing = sorted(calls - definitions)
    if missing:
        error("custom-card method calls without declarations: " + ", ".join(missing))

    service_calls = set(re.findall(r'_callResponseService\(\s*["\']([a-z0-9_]+)["\']', text))
    service_keys = set(re.findall(r'^([a-z0-9_]+):\s*$', SERVICES.read_text(encoding="utf-8"), re.MULTILINE))
    missing_services = sorted(service_calls - service_keys)
    if missing_services:
        error("card response services missing from services.yaml: " + ", ".join(missing_services))


def check_package_hygiene() -> None:
    bad = []
    for path in ROOT.rglob("*"):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            bad.append(str(path.relative_to(ROOT)))
    if bad:
        error("compiled cache files packaged: " + ", ".join(bad[:10]))

    component_dirs = [p for p in (ROOT / "custom_components").iterdir() if p.is_dir()]
    if len(component_dirs) != 1 or component_dirs[0].name != "ufanet_intercom":
        error("HACS integration repository must contain exactly custom_components/ufanet_intercom")


def check_secrets() -> None:
    candidates = [p for p in ROOT.rglob("*") if p.is_file() and p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".zip"}]
    jwt = re.compile(r'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}')
    live_guest = re.compile(r'https://domovoy\.city/[^\s"\']+\?token=[A-Za-z0-9_-]{6,}')
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if jwt.search(text):
            error(f"possible live JWT in {path.relative_to(ROOT)}")
        if live_guest.search(text):
            error(f"possible live guest link in {path.relative_to(ROOT)}")


def check_hacs(strict: bool) -> None:
    manifest = load_json(MANIFEST)
    hacs = load_json(HACS)
    for key in ("domain", "name", "version"):
        if not manifest.get(key):
            error(f"manifest missing {key}")
    if not hacs.get("name"):
        error("hacs.json missing name")

    requirements = {
        "documentation": manifest.get("documentation"),
        "issue_tracker": manifest.get("issue_tracker"),
        "codeowners": manifest.get("codeowners"),
        "brand/icon.png": (ROOT / "brand" / "icon.png").exists(),
    }
    missing = [key for key, value in requirements.items() if not value]
    if missing:
        message = "HACS publication metadata not finalized: " + ", ".join(missing)
        if strict:
            error(message)
        else:
            warning(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-hacs", action="store_true")
    args = parser.parse_args()

    check_versions()
    check_python()
    check_json()
    check_js()
    check_package_hygiene()
    check_secrets()
    check_hacs(args.strict_hacs)

    for item in WARNINGS:
        print("WARNING:", item)
    for item in ERRORS:
        print("ERROR:", item)

    if ERRORS:
        print(f"FAILED: {len(ERRORS)} error(s), {len(WARNINGS)} warning(s)")
        return 1
    print(f"OK: release checks passed with {len(WARNINGS)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
