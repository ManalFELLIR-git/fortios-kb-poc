from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .utils import dump_yaml, load_yaml


PROVIDER_ONLY = "provider_only_candidate"
PROVIDER_REQUIRED_ONLY = "provider_required_only"
ENUM_CHOICES_MISSING = "enum_choices_missing"
DEFAULT_OUTSIDE_RANGE = "default_outside_range"
NOT_EXACTLY_CONFIRMED = "not_confirmed_by_exact_fortios_sources"


def _numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _source_evidence(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Return deterministic provenance without manufacturing unavailable fields."""
    raw_evidence = entry.get("evidence") or {}
    source_names = set(entry.get("sources") or [])
    if isinstance(raw_evidence, dict):
        source_names.update(raw_evidence)

    evidence = []
    for source in sorted(source_names):
        item: dict[str, Any] = {"source": source}
        spec = raw_evidence.get(source) if isinstance(raw_evidence, dict) else None
        if isinstance(spec, dict) and spec.get("choices"):
            item["observed_choices"] = spec["choices"]
        evidence.append(item)
    return evidence


def _has_source(entry: dict[str, Any], source: str) -> bool:
    if source in set(entry.get("sources") or []):
        return True
    evidence = entry.get("evidence") or {}
    return isinstance(evidence, dict) and source in evidence


def _sources(entry: dict[str, Any]) -> set[str]:
    sources = set(entry.get("sources") or [])
    evidence = entry.get("evidence") or {}
    if isinstance(evidence, dict):
        sources.update(evidence)
    return sources


def _sentinel_is_resolved(entry: dict[str, Any], default: float) -> bool:
    special_values = entry.get("special_values") or []
    special_numeric = {
        value
        for raw in special_values
        if (value := _numeric(raw)) is not None
    }
    if default in special_numeric:
        return True

    resolution = entry.get("resolution") or {}
    range_resolution = resolution.get("range") or {}
    return isinstance(range_resolution, dict) and any(
        isinstance(value, dict)
        and value.get("resolution") == "sentinel_value_plus_normal_range"
        for value in range_resolution.values()
    )


def _validate_attribute(
    entry: dict[str, Any], *, exact_cli_reference: bool
) -> dict[str, Any]:
    canonical = entry.get("canonical") or {}
    field_sources = entry.get("field_sources") or {}
    sources = _sources(entry)
    reasons: list[str] = []

    provider_only = sources == {"terraform"}
    if provider_only:
        reasons.append(PROVIDER_ONLY)

    if (
        canonical.get("required") is True
        and field_sources.get("required") == "terraform"
    ):
        reasons.append(PROVIDER_REQUIRED_ONLY)

    if canonical.get("type") == "enum" and not canonical.get("choices"):
        reasons.append(ENUM_CHOICES_MISSING)

    default = _numeric(canonical.get("default"))
    minimum = _numeric(canonical.get("min"))
    maximum = _numeric(canonical.get("max"))
    if (
        default is not None
        and minimum is not None
        and maximum is not None
        and (default < minimum or default > maximum)
        and not _sentinel_is_resolved(entry, default)
    ):
        reasons.append(DEFAULT_OUTSIDE_RANGE)

    if not exact_cli_reference or not _has_source(entry, "cli_reference"):
        reasons.append(NOT_EXACTLY_CONFIRMED)

    reasons = list(dict.fromkeys(reasons))
    if provider_only:
        status = "quarantined"
    elif reasons:
        status = "needs_review"
    else:
        status = "confirmed"

    return {
        "safe_for_cli_generation": status == "confirmed",
        "status": status,
        "reasons": reasons,
        "evidence": _source_evidence(entry),
    }


def run_quality_gate(kb_dir: Path, version: str) -> dict:
    """
    Execute the quality gate and annotate every eligible canonical attribute.

    ``kb_dir`` is the version directory containing ``canonical/``. Existing
    validation blocks are replaced, making repeated runs deterministic and
    preventing duplicated reasons or evidence.
    """
    kb_dir = Path(kb_dir)
    canonical_dir = kb_dir / "canonical"
    reason_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    total_attributes = 0
    attributes_with_validation = 0
    not_applicable_files = 0

    for path in sorted(canonical_dir.glob("*.yaml")):
        section = load_yaml(path) or {}
        attributes = section.get("attributes_flat")
        if not isinstance(attributes, dict) or not attributes:
            not_applicable_files += 1
            continue

        changed = False
        for entry in attributes.values():
            if not isinstance(entry, dict):
                continue
            total_attributes += 1
            validation = _validate_attribute(
                entry,
                exact_cli_reference=section.get("version") == version,
            )
            entry["validation"] = validation
            attributes_with_validation += 1
            status_counts[validation["status"]] += 1
            reason_counts.update(validation["reasons"])
            changed = True

        if changed:
            dump_yaml(path, section)

    attributes_without_validation = total_attributes - attributes_with_validation
    if attributes_without_validation:
        raise RuntimeError(
            f"quality gate left {attributes_without_validation} eligible attributes without validation"
        )

    return {
        "version": version,
        "total_attributes": total_attributes,
        "attributes_with_validation": attributes_with_validation,
        "attributes_without_validation": attributes_without_validation,
        "safe_attributes": status_counts["confirmed"],
        "quarantined_attributes": status_counts["quarantined"],
        "needs_review_attributes": status_counts["needs_review"],
        "not_applicable_files": not_applicable_files,
        "reason_counts": dict(sorted(reason_counts.items())),
    }
