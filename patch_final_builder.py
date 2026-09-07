from pathlib import Path
import shutil
import re

# ============================================================
# BUILD.PY
# ============================================================

build = Path("kb_builder/build.py")
build_backup = Path("kb_builder/build.py.before_semantic_integration.bak")

if not build_backup.exists():
    shutil.copy2(build, build_backup)

text = build.read_text(encoding="utf-8")

# Ajouter import
if "from .semantic_resolution import resolve_semantics" not in text:

    # Ajouter après les imports relatifs
    lines = text.splitlines()

    insert_at = 0

    for i, line in enumerate(lines):
        if line.startswith("from .") or line.startswith("import "):
            insert_at = i + 1

    lines.insert(
        insert_at,
        "from .semantic_resolution import resolve_semantics"
    )

    text = "\n".join(lines) + "\n"


# Ajouter résolution après reconcile_all(root, version)
if "resolve_semantics(root, version, apply=True)" not in text:

    pattern = re.compile(
        r"(?m)^(\s*)reconcile_all\(root,\s*version\)\s*$"
    )

    m = pattern.search(text)

    if not m:
        raise RuntimeError(
            "Appel reconcile_all(root, version) introuvable dans build.py"
        )

    indent = m.group(1)

    replacement = (
        m.group(0)
        + "\n"
        + indent
        + "semantic_summary = resolve_semantics("
        + "root, version, apply=True)"
    )

    text = (
        text[:m.start()]
        + replacement
        + text[m.end():]
    )

build.write_text(
    text,
    encoding="utf-8"
)

print("[OK] build.py : semantic resolver intégré")


# ============================================================
# AUDIT.PY
# ============================================================

audit = Path("kb_builder/audit.py")
audit_backup = Path("kb_builder/audit.py.before_semantic_audit.bak")

if not audit_backup.exists():
    shutil.copy2(audit, audit_backup)


audit_code = r'''from __future__ import annotations
from pathlib import Path
from .utils import load_yaml, dump_yaml


def count_yaml(folder: Path):
    return (
        len(list(folder.glob("*.yaml")))
        if folder.exists()
        else 0
    )


def audit(root: Path, version: str, extraction_errors=None):

    extraction_errors = extraction_errors or []

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


    raw_conflicts = sum(
        len(section.get("conflicts") or [])
        for section in sections
    )

    attrs = sum(
        len(section.get("attributes_flat") or {})
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
    # Semantic resolution report
    # ========================================================

    semantic_path = (
        root
        / "audit"
        / "semantic_resolution_integrated.yaml"
    )

    semantic = {}

    if semantic_path.exists():
        semantic = (
            load_yaml(
                semantic_path
            )
            or {}
        )


    type_report = (
        semantic.get(
            "type_resolution"
        )
        or {}
    )

    range_report = (
        semantic.get(
            "range_resolution"
        )
        or {}
    )


    type_total = int(
        type_report.get(
            "total",
            0
        )
        or 0
    )

    type_resolved = int(
        type_report.get(
            "resolved",
            0
        )
        or 0
    )

    type_unresolved = int(
        type_report.get(
            "unresolved",
            0
        )
        or 0
    )


    range_total = int(
        range_report.get(
            "total",
            0
        )
        or 0
    )

    range_resolved = int(
        range_report.get(
            "resolved",
            0
        )
        or 0
    )

    range_unresolved = int(
        range_report.get(
            "unresolved",
            0
        )
        or 0
    )


    semantic_unresolved = (
        type_unresolved
        + range_unresolved
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

        f = load_yaml(fp) or {}

        topics = (
            f.get("topics")
            or []
        )

        features = len(topics)

        feature_cli_refs = sum(
            len(
                topic.get(
                    "cli_sections"
                )
                or []
            )
            for topic in topics
        )


    # ========================================================
    # KB Status
    # ========================================================

    if (
        invalid
        or extraction_errors
    ):

        kb_status = "PARTIAL"

    elif semantic_unresolved > 0:

        kb_status = (
            "PARTIAL_VALIDATED"
        )

    elif semantic_path.exists():

        kb_status = (
            "STATIC_VALIDATED"
        )

    else:

        kb_status = (
            "RECONCILED"
        )


    report = {

        "target_version":
            version,

        "kb_status":
            kb_status,

        "sections":
            len(sections),

        "attributes_flat":
            attrs,

        # Ancien compteur conservé pour traçabilité.
        # Ce sont des différences détectées,
        # pas forcément des conflits non résolus.
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
        f"- Extraction errors: **{len(extraction_errors)}**",
        f"- Invalid YAML: **{len(invalid)}**",
        "",

        "## Coverage",
        "",
    ]


    for key, value in (
        coverage.items()
    ):

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
'''


audit.write_text(
    audit_code,
    encoding="utf-8"
)

print("[OK] audit.py : audit sémantique intégré")

print()
print("[BACKUP]", build_backup)
print("[BACKUP]", audit_backup)
