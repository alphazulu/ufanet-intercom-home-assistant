from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

RESOURCE_NAMES: dict[str, tuple[str, ...]] = {
    "project_id": ("project_id",),
    "sender_id": ("gcm_defaultSenderId",),
    "app_id": ("google_app_id",),
    "api_key": ("google_api_key", "google_crash_reporting_api_key"),
    "database_url": ("firebase_database_url",),
    "storage_bucket": ("google_storage_bucket",),
}

REQUIRED_FIELDS = ("project_id", "sender_id", "app_id", "package_name", "api_key")
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")
APP_ID_RE = re.compile(r"^\d+:(\d+):android:[A-Za-z0-9_-]+$")
APPLICATION_ID_RE = re.compile(r'\bAPPLICATION_ID\s*=\s*"([^"]+)"')


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def safe_write_json(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise RuntimeError(f"Output already exists: {path}. Use --overwrite to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    try:
        os.chmod(tmp, stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass
    os.replace(tmp, path)
    try:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass


def add_candidate(candidates: dict[str, set[str]], field: str, value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        candidates.setdefault(field, set()).add(text)


def scan_xml(path: Path, candidates: dict[str, set[str]]) -> None:
    try:
        if path.stat().st_size > 8 * 1024 * 1024:
            return
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError, UnicodeError):
        return

    if root.tag.endswith("manifest"):
        add_candidate(candidates, "package_name", root.attrib.get("package"))

    name_to_field: dict[str, str] = {}
    for field, names in RESOURCE_NAMES.items():
        for name in names:
            name_to_field[name] = field

    for node in root.iter():
        if not node.tag.endswith("string"):
            continue
        name = node.attrib.get("name")
        field = name_to_field.get(name or "")
        if field and node.text:
            add_candidate(candidates, field, node.text)


def scan_build_config(path: Path, candidates: dict[str, set[str]]) -> None:
    try:
        if path.stat().st_size > 1024 * 1024:
            return
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for match in APPLICATION_ID_RE.finditer(text):
        add_candidate(candidates, "package_name", match.group(1))


def source_files(source: Path) -> tuple[list[Path], list[Path]]:
    if source.is_file():
        if source.suffix.lower() == ".xml":
            return [source], []
        if source.name == "BuildConfig.java":
            return [], [source]
        raise RuntimeError(
            "Direct APK parsing is intentionally not performed by this first extractor. "
            "Pass a decompiled/apktool directory, strings.xml/resources.xml, or BuildConfig.java."
        )
    if not source.is_dir():
        raise RuntimeError(f"Input path does not exist: {source}")

    xml_files = list(source.rglob("*.xml"))
    build_configs = list(source.rglob("BuildConfig.java"))
    return xml_files, build_configs


def choose_value(
    candidates: dict[str, set[str]],
    field: str,
    override: str | None,
    *,
    required: bool,
) -> str | None:
    if override is not None:
        value = override.strip()
        if not value and required:
            raise RuntimeError(f"Empty override for required field {field}")
        return value or None

    values = sorted(candidates.get(field, set()))
    if not values:
        if required:
            raise RuntimeError(
                f"Could not extract required field {field}. "
                f"Provide --{field.replace('_', '-')} explicitly."
            )
        return None
    if len(values) > 1:
        if field == "api_key":
            # google_api_key and google_crash_reporting_api_key are commonly identical.
            # Distinct values are ambiguous and must never be guessed.
            shown = ", ".join(f"sha256={fingerprint(value)}" for value in values)
        else:
            shown = ", ".join(repr(value) for value in values)
        raise RuntimeError(
            f"Multiple candidates found for {field}: {shown}. "
            f"Narrow the input directory or provide --{field.replace('_', '-')} explicitly."
        )
    return values[0]


def validate_config(config: dict[str, str]) -> None:
    package_name = config["package_name"]
    if not PACKAGE_RE.fullmatch(package_name):
        raise RuntimeError(f"Invalid Android package name: {package_name!r}")

    sender_id = config["sender_id"]
    if not sender_id.isdigit():
        raise RuntimeError("Firebase sender_id must be numeric")

    app_id = config["app_id"]
    match = APP_ID_RE.fullmatch(app_id)
    if not match:
        raise RuntimeError("Firebase app_id does not look like an Android Firebase app id")
    if match.group(1) != sender_id:
        raise RuntimeError("sender_id does not match the project number embedded in app_id")

    if not config["project_id"].strip():
        raise RuntimeError("project_id is empty")
    if not config["api_key"].strip():
        raise RuntimeError("api_key is empty")


def extract(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.source).expanduser().resolve()
    candidates: dict[str, set[str]] = {}
    xml_files, build_configs = source_files(source)

    for path in xml_files:
        scan_xml(path, candidates)
    for path in build_configs:
        scan_build_config(path, candidates)

    overrides = {
        "project_id": args.project_id,
        "sender_id": args.sender_id,
        "app_id": args.app_id,
        "package_name": args.package_name,
        "api_key": args.api_key,
    }

    config: dict[str, str] = {}
    for field in REQUIRED_FIELDS:
        value = choose_value(candidates, field, overrides[field], required=True)
        assert value is not None
        config[field] = value

    validate_config(config)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "firebase": config,
    }

    if args.include_unused:
        optional: dict[str, str] = {}
        for field in ("database_url", "storage_bucket"):
            value = choose_value(candidates, field, None, required=False)
            if value is not None:
                optional[field] = value
        if optional:
            payload["unused_metadata"] = optional

    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Firebase Android client configuration locally from a user's "
            "decompiled/apktool copy. No Ufanet Firebase values are built into this tool."
        )
    )
    parser.add_argument(
        "source",
        help="Decompiled/apktool directory, resources/strings XML, or BuildConfig.java",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(Path(__file__).with_name("firebase_config.json")),
        help="Output JSON path (default: firebase_config.json next to this script)",
    )
    parser.add_argument("--project-id")
    parser.add_argument("--sender-id")
    parser.add_argument("--app-id")
    parser.add_argument("--package-name")
    parser.add_argument("--api-key")
    parser.add_argument(
        "--include-unused",
        action="store_true",
        help="Also include database_url/storage_bucket if found; receiver does not need them",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacement of an existing output file",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = extract(args)
        output = Path(args.output).expanduser().resolve()
        safe_write_json(output, payload, overwrite=args.overwrite)
        firebase = payload["firebase"]
        print(f"[OK] Firebase config written to: {output}")
        print(f"[OK] package_name: {firebase['package_name']}")
        print(f"[OK] project_id: {firebase['project_id']}")
        print(f"[OK] sender_id: {firebase['sender_id']}")
        print(f"[OK] app_id present: yes (sha256={fingerprint(firebase['app_id'])})")
        print(f"[OK] api_key present: yes (sha256={fingerprint(firebase['api_key'])})")
        print("[INFO] The API key value is intentionally not printed.")
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
