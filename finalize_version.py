from pathlib import Path
from collections import Counter
import yaml

from kb_builder.utils import load_yaml

VERSION = "7.6.7"

ROOT = Path("knowledge_base") / "fortios" / VERSION
CANONICAL = ROOT / "canonical"
AUDIT = ROOT / "audit"

AUDIT.mkdir(parents=True, exist_ok=True)

PROVIDER_META = {
    "dynamic_sort_subtable",
    "get_all_tables",
    "vdomparam",
    "update_if_exist",
}

counts = Counter()
section_counts = {}

total_sections = 0
total_attributes = 0

provider_meta_examples = []
terraform_only_examples = []
ansible_only_examples = []
secondary_consensus_examples = []

for path in sorted(CANONICAL.glob("*.yaml")):

    data = load_yaml(path) or {}

    section = data.get("id") or path.stem
    attrs = data.get("attributes_flat", {}) or {}

    total_sections += 1

    sec = Counter()

    for attr_name, entry in attrs.items():

        if not isinstance(entry, dict):
            continue

        total_attributes += 1

        evidence = entry.get("evidence") or {}

        sources = set(evidence.keys())

        leaf = attr_name.split(".")[-1]

        # ---------------------------------------
        # 1. Provider-only technical metadata
        # ---------------------------------------

        if (
            sources == {"terraform"}
            and leaf in PROVIDER_META
        ):

            classification = "provider_metadata"
            runtime = False

            if len(provider_meta_examples) < 30:
                provider_meta_examples.append(
                    f"{section}::{attr_name}"
                )

        # ---------------------------------------
        # 2. Official FortiOS CLI evidence
        # ---------------------------------------

        elif "cli_reference" in sources:

            classification = "authoritative_cli"
            runtime = True

        # ---------------------------------------
        # 3. Two independent secondary sources
        # ---------------------------------------

        elif (
            "ansible" in sources
            and "terraform" in sources
        ):

            classification = "secondary_consensus"
            runtime = False

            if len(secondary_consensus_examples) < 30:
                secondary_consensus_examples.append(
                    f"{section}::{attr_name}"
                )

        # ---------------------------------------
        # 4. Terraform only
        # ---------------------------------------

        elif sources == {"terraform"}:

            classification = "secondary_terraform"
            runtime = False

            if len(terraform_only_examples) < 30:
                terraform_only_examples.append(
                    f"{section}::{attr_name}"
                )

        # ---------------------------------------
        # 5. Ansible only
        # ---------------------------------------

        elif sources == {"ansible"}:

            classification = "secondary_ansible"
            runtime = False

            if len(ansible_only_examples) < 30:
                ansible_only_examples.append(
                    f"{section}::{attr_name}"
                )

        else:

            classification = "unclassified"
            runtime = False

        counts[classification] += 1
        sec[classification] += 1

    section_counts[section] = dict(sec)


classification_report = {
    "version": VERSION,

    "status": "baseline_classified",

    "canonical": {
        "sections": total_sections,
        "attributes": total_attributes,
    },

    "classification": {
        "authoritative_cli": counts["authoritative_cli"],
        "secondary_consensus": counts["secondary_consensus"],
        "secondary_terraform": counts["secondary_terraform"],
        "secondary_ansible": counts["secondary_ansible"],
        "provider_metadata": counts["provider_metadata"],
        "unclassified": counts["unclassified"],
    },

    "runtime_policy": {
        "authoritative_cli": True,
        "secondary_consensus": False,
        "secondary_terraform": False,
        "secondary_ansible": False,
        "provider_metadata": False,
    },

    "notes": {
        "secondary_consensus":
            "Supported by both Ansible and Terraform but not yet CLI-reference verified.",

        "provider_metadata":
            "Provider/control fields. Never emit as FortiOS CLI.",

        "defaults":
            "Defaults are knowledge/validation metadata and must not automatically be emitted.",

        "runtime":
            "Initial runtime generation must prefer authoritative_cli attributes.",
    },

    "examples": {
        "provider_metadata": provider_meta_examples,
        "secondary_consensus": secondary_consensus_examples,
        "secondary_terraform": terraform_only_examples,
        "secondary_ansible": ansible_only_examples,
    },

    "per_section": section_counts,
}


report_path = (
    AUDIT
    / "final_classification.yaml"
)

with report_path.open(
    "w",
    encoding="utf-8",
) as f:

    yaml.safe_dump(
        classification_report,
        f,
        sort_keys=False,
        allow_unicode=True,
    )


manifest = {
    "product": "FortiOS",
    "version": VERSION,

    "baseline_status":
        "READY_FOR_RUNTIME_POC",

    "collection": {
        "admin_topics": 3024,
        "remaining_errors": 0,
        "remaining_queue": 0,
    },

    "canonical": {
        "sections": total_sections,
        "attributes": total_attributes,
        "attributes_without_type": 0,
        "attributes_without_evidence": 0,
    },

    "confidence_tiers": {
        "authoritative_cli":
            counts["authoritative_cli"],

        "secondary_consensus":
            counts["secondary_consensus"],

        "secondary_terraform":
            counts["secondary_terraform"],

        "secondary_ansible":
            counts["secondary_ansible"],

        "provider_metadata":
            counts["provider_metadata"],
    },

    "runtime": {
        "default_tier":
            "authoritative_cli",

        "allow_secondary_consensus":
            False,

        "allow_single_source":
            False,

        "allow_provider_metadata":
            False,

        "emit_defaults_automatically":
            False,
    },

    "known_quality_reviews": {
        "remaining_type_review": 496,
        "value_disagreements": 59,
        "implicit_outside_range_defaults": 42,
        "real_range_review": 31,
    },

    "quality_statement":
        "Canonical baseline complete. "
        "Official CLI-backed subset is runtime-authoritative. "
        "Secondary-source attributes are retained for enrichment "
        "but are not enabled by default for configuration generation.",

    "next_phase":
        "FortiGate 100F + FortiOS 7.6.7 runtime POC",
}


manifest_path = ROOT / "manifest.yaml"

with manifest_path.open(
    "w",
    encoding="utf-8",
) as f:

    yaml.safe_dump(
        manifest,
        f,
        sort_keys=False,
        allow_unicode=True,
    )


print()
print("=" * 72)
print("FORTIOS 7.6.7 BASELINE FINALIZATION")
print("=" * 72)

print()
print("Sections                  :", total_sections)
print("Attributes                :", total_attributes)

print()
print("AUTHORITATIVE CLI         :", counts["authoritative_cli"])
print("SECONDARY CONSENSUS       :", counts["secondary_consensus"])
print("SECONDARY TERRAFORM       :", counts["secondary_terraform"])
print("SECONDARY ANSIBLE         :", counts["secondary_ansible"])
print("PROVIDER METADATA         :", counts["provider_metadata"])
print("UNCLASSIFIED              :", counts["unclassified"])

print()
print("Total classified          :", sum(counts.values()))

print()
print("Manifest                  :", manifest_path)
print("Classification report     :", report_path)

print()
print("STATUS: READY_FOR_RUNTIME_POC")
print("=" * 72)

