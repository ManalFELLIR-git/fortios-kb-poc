from __future__ import annotations
from pathlib import Path
from .utils import load_yaml, dump_yaml


def count_yaml(folder: Path):
    return (
        len(list(folder.glob("*.yaml")))
        if folder.exists()
        else 0
    )


def audit(
    root: Path,
    version: str,
    extraction_errors=None,
    quality_gate_report=None,
):

    extraction_errors = extraction_errors or []
    if not quality_gate_report:
        raise ValueError(
            "audit requires the quality gate report; run run_quality_gate first"
        )

    quality_gate_version = quality_gate_report.get("version")
    if quality_gate_version != version:
        raise ValueError(
            "quality gate report version does not match audit target: "
            f"{quality_gate_version!r} != {version!r}"
        )

    canonical_dir = root / "canonical"

    canon_files = (
        list(canonical_dir.glob("*.yaml"))
        if canonical_dir.exists()
        else []
    )

    sections = []
    invalid = []

    for path in canon_files:

        try:
            sections.append(
                load_yaml(path)
            )

        except Exception as exc:
            invalid.append({
                "file": str(path),
                "error": repr(exc),
            })


    attrs = sum(
        len(section.get("attributes_flat") or {})
        for section in sections
    )


    raw_conflicts = sum(
        len(section.get("conflicts") or [])
        for section in sections
    )


    coverage = {
        src: sum(
            1
            for section in sections
            if section.get(
                "source_presence",
                {}
            ).get(src)
        )
        for src in (
            "ansible",
            "terraform",
            "cli_reference",
        )
    }


    # ========================================================
    # Semantic resolution
    # ========================================================

    semantic_path = (
        root
        / "audit"
        / "semantic_resolution_integrated.yaml"
    )

    semantic = {}

    if semantic_path.exists():
        semantic = load_yaml(
            semantic_path
        ) or {}


    type_report = (
        semantic.get("type_resolution")
        or {}
    )

    range_report = (
        semantic.get("range_resolution")
        or {}
    )


    type_total = int(
        type_report.get("total", 0)
        or 0
    )

    type_resolved = int(
        type_report.get("resolved", 0)
        or 0
    )

    type_unresolved = int(
        type_report.get("unresolved", 0)
        or 0
    )


    range_total = int(
        range_report.get("total", 0)
        or 0
    )

    range_resolved = int(
        range_report.get("resolved", 0)
        or 0
    )

    range_unresolved = int(
        range_report.get("unresolved", 0)
        or 0
    )


    semantic_unresolved = (
        type_unresolved
        + range_unresolved
    )


    quality_gate = {
        "safe_attributes": int(
            quality_gate_report.get("safe_attributes", 0)
            or 0
        ),
        "quarantined_attributes": int(
            quality_gate_report.get("quarantined_attributes", 0)
            or 0
        ),
        "needs_review_attributes": int(
            quality_gate_report.get("needs_review_attributes", 0)
            or 0
        ),
    }

    validated_attributes = sum(quality_gate.values())
    expected_attributes = int(
        quality_gate_report.get("total_attributes", 0)
        or 0
    )
    missing_validations = int(
        quality_gate_report.get("attributes_without_validation", 0)
        or 0
    )
    if missing_validations or validated_attributes != expected_attributes:
        raise ValueError(
            "quality gate report has incomplete or inconsistent attribute coverage"
        )


    # ========================================================
    # Feature layer
    # ========================================================

    features = 0
    feature_cli_refs = 0

    fp = (
        root
        / "raw"
        / "docs"
        / "features"
        / "admin_topics.yaml"
    )

    if fp.exists():

        data = load_yaml(fp) or {}

        topics = (
            data.get("topics")
            or []
        )

        features = len(topics)

        feature_cli_refs = sum(
            len(
                topic.get("cli_sections")
                or []
            )
            for topic in topics
        )


    # ========================================================
    # KB status
    # ========================================================

    if invalid or extraction_errors or type_unresolved > 0:

        kb_status = "BLOCKED"

    elif (
        quality_gate["quarantined_attributes"] > 0
        or quality_gate["needs_review_attributes"] > 0
    ):

        kb_status = "PARTIAL_VALIDATED"

    else:

        kb_status = "READY_FOR_GENERATION"


    report = {

        "target_version":
            version,

        "kb_status":
            kb_status,

        "status":
            kb_status,

        "sections":
            len(sections),

        "attributes_flat":
            attrs,

        "raw_conflicts":
            raw_conflicts,

        "type_resolution": {
            "total":
                type_total,

            "resolved":
                type_resolved,

            "unresolved":
                type_unresolved,
        },

        "range_resolution": {
            "total":
                range_total,

            "resolved":
                range_resolved,

            "unresolved":
                range_unresolved,
        },

        "semantic_unresolved_total":
            semantic_unresolved,

        "quality_gate":
            quality_gate,

        "coverage_sections":
            coverage,

        "invalid_yaml":
            invalid,

        "extraction_errors":
            extraction_errors,

        "feature_topics":
            features,

        "feature_cli_references":
            feature_cli_refs,

        "raw_counts": {

            "ansible":
                count_yaml(
                    root
                    / "raw"
                    / "ansible"
                ),

            "terraform":
                count_yaml(
                    root
                    / "raw"
                    / "terraform"
                ),

            "cli_reference":
                count_yaml(
                    root
                    / "raw"
                    / "docs"
                    / "cli_reference"
                ),
        },
    }


    dump_yaml(
        root
        / "audit"
        / "report.yaml",
        report,
    )


    md = [
        f"# FortiOS {version} KB audit",
        "",
        f"- KB status: **{kb_status}**",
        f"- Canonical sections: **{len(sections)}**",
        f"- Flattened attributes: **{attrs}**",
        f"- Raw differences/conflicts: **{raw_conflicts}**",
        "",
        "## Semantic validation",
        "",
        f"- Type differences: **{type_total}**",
        f"- Type resolved: **{type_resolved}**",
        f"- Type unresolved: **{type_unresolved}**",
        "",
        f"- Range differences: **{range_total}**",
        f"- Range resolved: **{range_resolved}**",
        f"- Range unresolved: **{range_unresolved}**",
        "",
        f"- Semantic unresolved total: **{semantic_unresolved}**",
        "",
        "## Quality gate",
        "",
        f"- Safe attributes: **{quality_gate['safe_attributes']}**",
        f"- Quarantined attributes: **{quality_gate['quarantined_attributes']}**",
        f"- Needs-review attributes: **{quality_gate['needs_review_attributes']}**",
        f"- Extraction errors: **{len(extraction_errors)}**",
        f"- Invalid YAML: **{len(invalid)}**",
        "",
        "## Coverage",
        "",
    ]


    for key, value in coverage.items():
        md.append(
            f"- {key}: {value} sections"
        )


    (
        root
        / "audit"
        / "report.md"
    ).write_text(
        "\n".join(md) + "\n",
        encoding="utf-8",
    )


    return report
