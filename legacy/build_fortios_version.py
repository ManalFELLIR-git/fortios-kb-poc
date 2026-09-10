from pathlib import Path
import argparse
import subprocess
import sys
import time
import yaml


parser = argparse.ArgumentParser(
    description="FortiOS Knowledge Base pipeline orchestrator"
)

parser.add_argument(
    "--version",
    required=True,
    help="FortiOS version, example: 7.4.12",
)

parser.add_argument(
    "--skip-collection",
    action="store_true",
    help="Skip collection/extraction and run only final validation",
)

args = parser.parse_args()

VERSION = args.version

ROOT = Path("knowledge_base") / "fortios" / VERSION
CANONICAL = ROOT / "canonical"
AUDIT = ROOT / "audit"

AUDIT.mkdir(parents=True, exist_ok=True)


print()
print("=" * 80)
print(f"FORTIOS KB PIPELINE - {VERSION}")
print("=" * 80)


# ============================================================
# IMPORTANT
#
# Mets ici les scripts que TU UTILISES déjà pour construire
# la KB 7.6.7.
#
# Ne réécris pas leurs fonctions :
# cet orchestrateur les appelle simplement dans l'ordre.
# ============================================================

COLLECTION_STEPS = [

    # Exemple :
    #
    # (
    #     "CLI Reference collection",
    #     "collect_cli_reference.py",
    # ),
    #
    # (
    #     "CLI feature retry",
    #     "feature_source_retry.py",
    # ),
    #
    # (
    #     "Ansible extraction",
    #     "extract_ansible.py",
    # ),
    #
    # (
    #     "Terraform extraction",
    #     "extract_terraform.py",
    # ),
    #
    # (
    #     "Canonical merge",
    #     "build_canonical.py",
    # ),

]


VALIDATION_STEPS = [

    (
        "Final KB audit",
        "final_kb_audit.py",
    ),

    (
        "Final KB triage",
        "final_kb_triage.py",
    ),

    (
        "CLI gaps analysis",
        "analyze_cli_gaps.py",
    ),

    (
        "Final classification",
        "finalize_version.py",
    ),
]


def run_script(title, script):

    path = Path(script)

    print()
    print("-" * 80)
    print(f"[START] {title}")
    print(f"[SCRIPT] {script}")
    print("-" * 80)

    if not path.exists():

        print()
        print(f"[ERROR] Script not found: {script}")

        return False

    command = [
        sys.executable,
        str(path),
        "--version",
        VERSION,
    ]

    start = time.time()

    process = subprocess.run(
        command,
        check=False,
    )

    elapsed = time.time() - start

    if process.returncode != 0:

        print()
        print(
            f"[FAILED] {title} "
            f"(exit={process.returncode})"
        )

        return False

    print()
    print(
        f"[OK] {title} "
        f"({elapsed:.1f}s)"
    )

    return True


# ============================================================
# COLLECTION / EXTRACTION
# ============================================================

if not args.skip_collection:

    if COLLECTION_STEPS:

        print()
        print("=" * 80)
        print("PHASE 1 - COLLECTION / EXTRACTION")
        print("=" * 80)

        for title, script in COLLECTION_STEPS:

            if not run_script(
                title,
                script,
            ):

                print()
                print(
                    "PIPELINE STOPPED DURING COLLECTION"
                )

                sys.exit(1)

    else:

        print()
        print(
            "[INFO] No COLLECTION_STEPS configured."
        )

        print(
            "[INFO] Existing canonical data will be validated."
        )


# ============================================================
# PRE-VALIDATION
# ============================================================

print()
print("=" * 80)
print("PHASE 2 - PRE-VALIDATION")
print("=" * 80)


if not ROOT.exists():

    print(
        f"[FAIL] Version directory missing: {ROOT}"
    )

    sys.exit(1)


if not CANONICAL.exists():

    print(
        f"[FAIL] Canonical directory missing: {CANONICAL}"
    )

    sys.exit(1)


canonical_files = list(
    CANONICAL.glob("*.yaml")
)


if not canonical_files:

    print(
        "[FAIL] No canonical YAML files found."
    )

    sys.exit(1)


print(
    "Canonical files:",
    len(canonical_files),
)


# ============================================================
# VALIDATION
# ============================================================

print()
print("=" * 80)
print("PHASE 3 - QUALITY GATES")
print("=" * 80)


for title, script in VALIDATION_STEPS:

    if not run_script(
        title,
        script,
    ):

        print()
        print(
            "PIPELINE STOPPED DURING QUALITY GATE"
        )

        sys.exit(1)


# ============================================================
# FINAL MANIFEST CHECK
# ============================================================

print()
print("=" * 80)
print("PHASE 4 - FINAL STATUS")
print("=" * 80)


manifest_path = ROOT / "manifest.yaml"


if not manifest_path.exists():

    print()
    print(
        "[FAIL] manifest.yaml was not generated."
    )

    sys.exit(1)


with manifest_path.open(
    "r",
    encoding="utf-8",
) as f:

    manifest = yaml.safe_load(f) or {}


canonical = (
    manifest.get("canonical")
    or {}
)

confidence = (
    manifest.get("confidence_tiers")
    or {}
)

collection = (
    manifest.get("collection")
    or {}
)


sections = canonical.get(
    "sections",
    0,
)

attributes = canonical.get(
    "attributes",
    0,
)

without_type = canonical.get(
    "attributes_without_type",
    0,
)

without_evidence = canonical.get(
    "attributes_without_evidence",
    0,
)

remaining_errors = collection.get(
    "remaining_errors",
    0,
)

remaining_queue = collection.get(
    "remaining_queue",
    0,
)


authoritative = confidence.get(
    "authoritative_cli",
    0,
)

secondary_consensus = confidence.get(
    "secondary_consensus",
    0,
)

secondary_terraform = confidence.get(
    "secondary_terraform",
    0,
)

secondary_ansible = confidence.get(
    "secondary_ansible",
    0,
)

provider_metadata = confidence.get(
    "provider_metadata",
    0,
)


classified_total = (
    authoritative
    + secondary_consensus
    + secondary_terraform
    + secondary_ansible
    + provider_metadata
)


blockers = []


if sections <= 0:
    blockers.append(
        "No canonical sections"
    )


if attributes <= 0:
    blockers.append(
        "No canonical attributes"
    )


if without_type != 0:
    blockers.append(
        f"{without_type} attributes without type"
    )


if without_evidence != 0:
    blockers.append(
        f"{without_evidence} attributes without evidence"
    )


if remaining_errors != 0:
    blockers.append(
        f"{remaining_errors} collection errors"
    )


if remaining_queue != 0:
    blockers.append(
        f"{remaining_queue} items still queued"
    )


if classified_total != attributes:

    blockers.append(
        "Classification count mismatch: "
        f"{classified_total}/{attributes}"
    )


print()
print(
    "Version                   :",
    VERSION,
)

print(
    "Sections                  :",
    sections,
)

print(
    "Attributes                :",
    attributes,
)

print()
print(
    "AUTHORITATIVE CLI         :",
    authoritative,
)

print(
    "SECONDARY CONSENSUS       :",
    secondary_consensus,
)

print(
    "SECONDARY TERRAFORM       :",
    secondary_terraform,
)

print(
    "SECONDARY ANSIBLE         :",
    secondary_ansible,
)

print(
    "PROVIDER METADATA         :",
    provider_metadata,
)

print()
print(
    "Total classified          :",
    classified_total,
)


if blockers:

    print()
    print("=" * 80)
    print("STATUS: FAILED")
    print("=" * 80)

    for blocker in blockers:
        print(
            "[BLOCKER]",
            blocker,
        )

    sys.exit(1)


print()
print("=" * 80)
print(
    f"FORTIOS {VERSION}: READY_FOR_RUNTIME_POC"
)
print("=" * 80)

print()
print(
    "Manifest:",
    manifest_path,
)

print(
    "Next phase: hardware profile + runtime POC"
)

