from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

from ms.core.hashing import sha256_file

from .models import UxWorkflow, UxWorkflowRun

_EXPECT_RE = re.compile(r"^\s*#\s*Expect:\s*(.+)$", re.IGNORECASE)
_CAPTURE_RE = re.compile(r"^\s*\d+\s+capture\s+(screen|controller)\s+([A-Za-z0-9_-]+)\s*$")
_SEMANTIC_EXPECT_RE = re.compile(r"^semantic:([A-Za-z0-9_-]+):([A-Za-z][A-Za-z0-9_]*)=(.+)$")
_LABEL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_OVERLAY_EXCLUSIVE_MAX_CHANGED_BYTE_RATIO = 0.02
_CAPTURE_CHANGED_MIN_BYTES = 16


def inspect_run(*, workflow: UxWorkflow, output_dir: Path, exit_code: int) -> UxWorkflowRun:
    trace_rows = _read_ndjson(output_dir / "trace.ndjson")
    binding_rows = _read_ndjson(output_dir / "binding-trace.ndjson")
    expectations = workflow_expectations(workflow.path)
    requires_semantics = any(item.startswith("semantic:") for item in expectations)
    semantic_rows, raw_semantic_schema_valid = _read_semantic_trace(
        output_dir / "semantic-trace.ndjson"
    )
    semantic_schema_valid = not requires_semantics or raw_semantic_schema_valid
    failed = _failed_expectations(
        expectations=expectations,
        trace_rows=trace_rows,
        semantic_rows=semantic_rows,
        semantic_schema_valid=semantic_schema_valid,
        output_dir=output_dir,
    )
    expected_semantic_labels = {
        parsed[0]
        for expectation in expectations
        if (parsed := _parse_semantic_expectation(expectation)) is not None
    }
    return UxWorkflowRun(
        workflow=workflow,
        output_dir=output_dir,
        exit_code=exit_code,
        capture_count=len(tuple(output_dir.glob("*.bmp"))),
        expected_capture_count=_expected_capture_count(workflow.path),
        run_ended=any(row.get("event") == "run_end" for row in trace_rows),
        has_dispatch=any(row.get("stage") == "dispatch" for row in binding_rows),
        semantic_capture_count=len(semantic_rows),
        expected_semantic_capture_count=len(expected_semantic_labels),
        semantic_schema_valid=semantic_schema_valid,
        expectations=expectations,
        failed_expectations=failed,
    )


def _failed_expectations(
    *,
    expectations: tuple[str, ...],
    trace_rows: tuple[dict[str, object], ...],
    semantic_rows: tuple[dict[str, object], ...],
    semantic_schema_valid: bool,
    output_dir: Path,
) -> tuple[str, ...]:
    failed: list[str] = []
    requires_semantics = any(item.startswith("semantic:") for item in expectations)
    if requires_semantics and not semantic_schema_valid:
        failed.append("semantic_trace_schema")
    for expectation in expectations:
        if expectation == "playhead_progress":
            if not _has_playhead_progress(trace_rows):
                failed.append(expectation)
            continue
        if expectation == "overlay_exclusive":
            if not _capture_mostly_match(
                output_dir, "selector_open_early", "selector_open_late",
                max_changed_byte_ratio=_OVERLAY_EXCLUSIVE_MAX_CHANGED_BYTE_RATIO,
            ):
                failed.append(expectation)
            continue
        if expectation.startswith("capture_match:"):
            labels = expectation.removeprefix("capture_match:").split("=", 1)
            if len(labels) != 2 or not labels[0] or not labels[1]:
                failed.append(expectation)
                continue
            if not _capture_match(output_dir, labels[0], labels[1]):
                failed.append(expectation)
            continue
        if expectation.startswith("capture_changed:"):
            labels = expectation.removeprefix("capture_changed:").split("=", 1)
            if len(labels) != 2 or not labels[0] or not labels[1]:
                failed.append(expectation)
                continue
            if not _capture_changed(output_dir, labels[0], labels[1]):
                failed.append(expectation)
            continue
        if expectation.startswith("semantic:"):
            if not semantic_schema_valid:
                continue
            parsed = _parse_semantic_expectation(expectation)
            if parsed is None or not _semantic_expectation_matches(semantic_rows, *parsed):
                failed.append(expectation)
            continue
        failed.append(expectation)
    return tuple(failed)


def workflow_expectations(path: Path) -> tuple[str, ...]:
    expectations: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _EXPECT_RE.match(line)
        if match is None:
            continue
        for item in match.group(1).split(","):
            if item.strip():
                keyword, separator, arguments = item.strip().partition(":")
                expectations.add(keyword.lower() + separator + arguments)
    return tuple(sorted(expectations))


def _expected_capture_count(path: Path) -> int:
    total = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].split("//", 1)[0]
        if _CAPTURE_RE.match(line):
            total += 1
    return total


def _read_ndjson(path: Path) -> tuple[dict[str, object], ...]:
    if not path.is_file():
        return ()
    rows: list[dict[str, object]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(cast(dict[str, object], value))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()
    return tuple(rows)


def _read_semantic_trace(path: Path) -> tuple[tuple[dict[str, object], ...], bool]:
    """Validate capture rows; input gesture rows remain extensible.

    Gate 9 capture rows require a unique label, source sequence, rendered
    snapshot and explicit surface context.
    """
    if not path.is_file():
        return (), False
    captures: list[dict[str, object]] = []
    labels: set[str] = set()
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            value = json.loads(raw_line)
            if not isinstance(value, dict):
                return (), False
            row = cast(dict[str, object], value)
            if row.get("kind") != "capture":
                continue
            if not _valid_semantic_capture_row(row):
                return (), False
            label = cast(str, row["label"])
            if label in labels:
                return (), False
            labels.add(label)
            captures.append(row)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return (), False
    return tuple(captures), True


def _valid_semantic_capture_row(row: dict[str, object]) -> bool:
    label = row.get("label")
    if not isinstance(label, str) or _LABEL_RE.fullmatch(label) is None:
        return False
    for field in ("seq", "ms", "source_seq", "playhead", "page", "shared_track", "shared_mask"):
        value = row.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            return False
    if cast(int, row["seq"]) <= 0 or cast(int, row["ms"]) < 0:
        return False
    if cast(int, row["source_seq"]) < 0:
        return False
    if not isinstance(row.get("surface_context"), bool):
        return False
    if not isinstance(row.get("playing"), bool):
        return False
    if not isinstance(row.get("view"), str) or not cast(str, row["view"]):
        return False
    if not isinstance(row.get("overlay"), str) or not cast(str, row["overlay"]):
        return False
    activation_origin = row.get("activation_origin")
    activation_generation = row.get("activation_generation")
    if (activation_origin is None) != (activation_generation is None):
        return False
    if activation_origin is not None:
        if not isinstance(activation_origin, str) or _LABEL_RE.fullmatch(activation_origin) is None:
            return False
        if (
            not isinstance(activation_generation, int)
            or isinstance(activation_generation, bool)
            or activation_generation <= 0
        ):
            return False
    surface_context = cast(bool, row["surface_context"])
    source_seq = cast(int, row["source_seq"])
    return (surface_context and source_seq >= 0) or (not surface_context and source_seq == 0)


def _parse_semantic_expectation(expectation: str) -> tuple[str, str, str] | None:
    match = _SEMANTIC_EXPECT_RE.fullmatch(expectation)
    if match is None:
        return None
    label, field, expected = match.groups()
    expected = expected.strip()
    return (label, field, expected) if expected else None


def _semantic_expectation_matches(
    rows: tuple[dict[str, object], ...], label: str, field: str, expected: str,
) -> bool:
    matches = tuple(row for row in rows if row.get("label") == label)
    if len(matches) != 1 or field not in matches[0]:
        return False
    return _semantic_value_matches(matches[0][field], expected)


def _semantic_value_matches(actual: object, expected: str) -> bool:
    if expected == "*":
        return actual is not None
    normalized = expected.casefold()
    if normalized == "true":
        return actual is True or (
            isinstance(actual, int) and not isinstance(actual, bool) and actual == 1
        )
    if normalized == "false":
        return actual is False or (
            isinstance(actual, int) and not isinstance(actual, bool) and actual == 0
        )
    if normalized == "null":
        return actual is None
    try:
        expected_int = int(expected, 10)
    except ValueError:
        expected_int = None
    if expected_int is not None:
        return isinstance(actual, int) and not isinstance(actual, bool) and actual == expected_int
    return isinstance(actual, str) and actual == expected


def _has_playhead_progress(rows: tuple[dict[str, object], ...]) -> bool:
    steps = {
        int(step)
        for row in rows
        if row.get("event") == "action"
        and row.get("playing") is True
        and (step := row.get("playhead_step")) is not None
        and isinstance(step, int | float)
        and step >= 0
    }
    return len(steps) > 1


def _capture_match(output_dir: Path, left_label: str, right_label: str) -> bool:
    left = _capture_for_label(output_dir, left_label)
    right = _capture_for_label(output_dir, right_label)
    if left is None or right is None:
        return False
    return sha256_file(left) == sha256_file(right)


def _capture_changed(output_dir: Path, left_label: str, right_label: str) -> bool:
    left = _capture_for_label(output_dir, left_label)
    right = _capture_for_label(output_dir, right_label)
    if left is None or right is None:
        return False
    return _changed_byte_count(left.read_bytes(), right.read_bytes()) >= _CAPTURE_CHANGED_MIN_BYTES


def _capture_mostly_match(
    output_dir: Path, left_label: str, right_label: str, *, max_changed_byte_ratio: float,
) -> bool:
    left = _capture_for_label(output_dir, left_label)
    right = _capture_for_label(output_dir, right_label)
    if left is None or right is None:
        return False
    left_data = left.read_bytes()
    right_data = right.read_bytes()
    total = max(len(left_data), len(right_data))
    if total == 0:
        return len(left_data) == len(right_data)
    return _changed_byte_count(left_data, right_data) / total <= max_changed_byte_ratio


def _changed_byte_count(left: bytes, right: bytes) -> int:
    return abs(len(left) - len(right)) + sum(a != b for a, b in zip(left, right, strict=False))


def _capture_for_label(output_dir: Path, label: str) -> Path | None:
    if _LABEL_RE.fullmatch(label) is None:
        return None
    matches = tuple(output_dir.glob(f"*_{label}_screen.bmp"))
    return matches[0] if len(matches) == 1 else None
