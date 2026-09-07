from __future__ import annotations

import argparse
import csv
import getpass
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import yaml


PROVIDER_META_LEAFS = {
    "dynamic_sort_subtable",
    "get_all_tables",
    "vdomparam",
    "update_if_exist",
}

FEATURE_RULES = [
    ("SD-WAN", lambda s: s.startswith("system.sdwan") or s.startswith("system.virtualwanlink")),
    ("ZTNA", lambda s: s.startswith("ztna.") or s.startswith("firewall.access-proxy")),
    ("VPN", lambda s: s.startswith("vpn.")),
    ("Routing", lambda s: s.startswith("router.") or s.startswith("routerbgp.")),
    ("Firewall / NAT", lambda s: s.startswith("firewall.")),
    ("HA", lambda s: s.startswith("system.ha")),
    ("Interfaces / Network", lambda s: (
        s.startswith("system.interface")
        or s.startswith("system.zone")
        or s.startswith("system.vxlan")
        or s.startswith("system.evpn")
        or s.startswith("system.dhcp")
        or s.startswith("system.dns")
        or s.startswith("system.ntp")
    )),
    ("Antivirus", lambda s: s.startswith("antivirus.")),
    ("IPS", lambda s: s.startswith("ips.")),
    ("Web Filter / DNS Filter", lambda s: s.startswith("webfilter.") or s.startswith("dnsfilter.")),
    ("Application Control", lambda s: s.startswith("application.")),
    ("DLP / CASB / WAF", lambda s: s.startswith("dlp.") or s.startswith("casb.") or s.startswith("waf.")),
    ("Identity / AAA", lambda s: s.startswith("user.") or s.startswith("authentication.")),
    ("Certificates", lambda s: s.startswith("certificate.") or s.startswith("vpn.certificate.")),
    ("Wireless", lambda s: s.startswith("wireless-controller.")),
    ("FortiSwitch", lambda s: s.startswith("switch-controller.")),
    ("Logging / Reporting", lambda s: s.startswith("log.") or s.startswith("report.")),
    ("Automation", lambda s: s.startswith("system.automation") or s.startswith("automation.")),
    ("System / Platform", lambda s: s.startswith("system.") or s.startswith("dpdk.")),
]

ERROR_PATTERNS = [
    re.compile(r"Command fail", re.I),
    re.compile(r"parse error", re.I),
    re.compile(r"Unknown action", re.I),
    re.compile(r"Return code -", re.I),
    re.compile(r"entry not found", re.I),
]


def classify_feature(section: str) -> str:
    for name, fn in FEATURE_RULES:
        if fn(section):
            return name
    return "Other"


def source_set(record: dict) -> set[str]:
    src = record.get("sources") or []
    if isinstance(src, str):
        return {src}
    return {str(x) for x in src}


def trust_tier(record: dict, attr_name: str) -> str:
    sources = source_set(record)
    leaf = attr_name.split(".")[-1]
    if sources == {"terraform"} and leaf in PROVIDER_META_LEAFS:
        return "provider_metadata"
    if "cli_reference" in sources:
        return "authoritative_cli"
    if {"ansible", "terraform"}.issubset(sources):
        return "secondary_consensus"
    if sources == {"terraform"}:
        return "secondary_terraform"
    if sources == {"ansible"}:
        return "secondary_ansible"
    return "unclassified"


def load_kb(version_root: Path):
    canonical_dir = version_root / "canonical"
    if not canonical_dir.exists():
        raise SystemExit(f"Canonical directory not found: {canonical_dir}")

    sections = {}
    for p in sorted(canonical_dir.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        sid = str(data.get("id") or p.stem)
        sections[sid] = data
    return sections


def has_enum(canon: dict) -> bool:
    return any(canon.get(k) not in (None, [], {}) for k in ("enum", "choices", "allowed_values", "values"))


def analyze(version_root: Path):
    sections = load_kb(version_root)

    feature_stats = defaultdict(Counter)
    section_rows = []
    attr_rows = []

    global_stats = Counter()
    blockers = []

    for section, data in sections.items():
        attrs = data.get("attributes_flat") or {}
        feature = classify_feature(section)

        sec = Counter()
        sec["sections"] = 1
        sec["attributes"] = len(attrs)

        if not attrs:
            sec["empty_sections"] += 1

        for attr, rec in attrs.items():
            rec = rec or {}
            canon = rec.get("canonical")
            evidence = rec.get("evidence")
            tier = trust_tier(rec, attr)

            sec[tier] += 1
            global_stats[tier] += 1
            global_stats["attributes"] += 1

            canonical_present = isinstance(canon, dict) and bool(canon)
            type_present = canonical_present and canon.get("type") not in (None, "")
            evidence_present = isinstance(evidence, dict) and bool(evidence)

            if canonical_present:
                sec["canonical_present"] += 1
            else:
                sec["missing_canonical"] += 1
                blockers.append(f"MISSING_CANONICAL: {section}::{attr}")

            if type_present:
                sec["type_present"] += 1
            else:
                sec["missing_type"] += 1
                blockers.append(f"MISSING_TYPE: {section}::{attr}")

            if evidence_present:
                sec["evidence_present"] += 1
            else:
                sec["missing_evidence"] += 1
                blockers.append(f"MISSING_EVIDENCE: {section}::{attr}")

            if canonical_present:
                if canon.get("description"):
                    sec["description"] += 1
                if canon.get("default") is not None:
                    sec["default"] += 1
                if canon.get("min") is not None or canon.get("max") is not None:
                    sec["range"] += 1
                if has_enum(canon):
                    sec["enum"] += 1
                if canon.get("version_ranges"):
                    sec["version_ranges"] += 1

            conflicts = data.get("conflicts") or []
            if conflicts:
                sec["section_has_conflicts"] = 1
                sec["conflict_objects"] = len(conflicts) if isinstance(conflicts, list) else 1

            attr_rows.append({
                "feature": feature,
                "section": section,
                "attribute": attr,
                "trust": tier,
                "sources": "+".join(sorted(source_set(rec))),
                "canonical": canonical_present,
                "type": canon.get("type") if canonical_present else None,
                "description": bool(canon.get("description")) if canonical_present else False,
                "default": canon.get("default") if canonical_present else None,
                "min": canon.get("min") if canonical_present else None,
                "max": canon.get("max") if canonical_present else None,
                "enum": has_enum(canon) if canonical_present else False,
                "versions": bool(canon.get("version_ranges")) if canonical_present else False,
                "evidence": evidence_present,
            })

        feature_stats[feature].update(sec)

        non_provider = len(attrs) - sec["provider_metadata"]
        authoritative_ratio = (sec["authoritative_cli"] / non_provider * 100.0) if non_provider else 0.0

        if sec["missing_canonical"] or sec["missing_type"] or sec["missing_evidence"] or sec["unclassified"]:
            status = "BLOCKED"
        elif non_provider == 0:
            status = "PROVIDER_ONLY"
        elif sec["authoritative_cli"] == non_provider:
            status = "ALL_CLI_BACKED"
        elif sec["authoritative_cli"] > 0:
            status = "MIXED_SOURCES"
        else:
            status = "SECONDARY_ONLY"

        section_rows.append({
            "feature": feature,
            "section": section,
            "attributes": len(attrs),
            "authoritative_cli": sec["authoritative_cli"],
            "secondary_consensus": sec["secondary_consensus"],
            "secondary_terraform": sec["secondary_terraform"],
            "secondary_ansible": sec["secondary_ansible"],
            "provider_metadata": sec["provider_metadata"],
            "unclassified": sec["unclassified"],
            "missing_canonical": sec["missing_canonical"],
            "missing_type": sec["missing_type"],
            "missing_evidence": sec["missing_evidence"],
            "authoritative_ratio_non_provider_pct": round(authoritative_ratio, 2),
            "status": status,
        })

    global_stats["sections"] = len(sections)
    global_stats["blockers"] = len(blockers)

    return sections, feature_stats, section_rows, attr_rows, global_stats, blockers


def feature_status(stats: Counter) -> str:
    attrs = stats["attributes"]
    non_provider = attrs - stats["provider_metadata"]
    if stats["missing_canonical"] or stats["missing_type"] or stats["missing_evidence"] or stats["unclassified"]:
        return "BLOCKED"
    if non_provider <= 0:
        return "PROVIDER_ONLY"
    if stats["authoritative_cli"] == non_provider:
        return "ALL_CLI_BACKED"
    if stats["authoritative_cli"] > 0:
        return "MIXED_SOURCES"
    return "SECONDARY_ONLY"


def write_reports(out_dir: Path, version: str, feature_stats, section_rows, attr_rows, global_stats, blockers):
    out_dir.mkdir(parents=True, exist_ok=True)

    feature_rows = []
    for feature in sorted(feature_stats):
        st = feature_stats[feature]
        non_provider = st["attributes"] - st["provider_metadata"]
        auth_pct = (st["authoritative_cli"] / non_provider * 100.0) if non_provider else 0.0
        feature_rows.append({
            "feature": feature,
            "sections": st["sections"],
            "attributes": st["attributes"],
            "authoritative_cli": st["authoritative_cli"],
            "secondary_consensus": st["secondary_consensus"],
            "secondary_terraform": st["secondary_terraform"],
            "secondary_ansible": st["secondary_ansible"],
            "provider_metadata": st["provider_metadata"],
            "unclassified": st["unclassified"],
            "missing_canonical": st["missing_canonical"],
            "missing_type": st["missing_type"],
            "missing_evidence": st["missing_evidence"],
            "description": st["description"],
            "default": st["default"],
            "range": st["range"],
            "enum": st["enum"],
            "version_ranges": st["version_ranges"],
            "authoritative_ratio_non_provider_pct": round(auth_pct, 2),
            "status": feature_status(st),
        })

    def write_csv(path, rows):
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    write_csv(out_dir / "feature_coverage.csv", feature_rows)
    write_csv(out_dir / "section_coverage.csv", section_rows)
    write_csv(out_dir / "attribute_inventory.csv", attr_rows)

    summary = {
        "version": version,
        "sections": global_stats["sections"],
        "attributes": global_stats["attributes"],
        "authoritative_cli": global_stats["authoritative_cli"],
        "secondary_consensus": global_stats["secondary_consensus"],
        "secondary_terraform": global_stats["secondary_terraform"],
        "secondary_ansible": global_stats["secondary_ansible"],
        "provider_metadata": global_stats["provider_metadata"],
        "unclassified": global_stats["unclassified"],
        "blocking_structural_issues": global_stats["blockers"],
        "features": feature_rows,
        "blockers_preview": blockers[:200],
    }
    (out_dir / "kb_full_validation_summary.yaml").write_text(
        yaml.safe_dump(summary, sort_keys=False, allow_unicode=True),
        encoding="utf-8"
    )

    return feature_rows


def _read_shell(shell, idle=0.25, max_wait=4.0):
    chunks = []
    start = time.time()
    last = time.time()
    while time.time() - start < max_wait:
        if shell.recv_ready():
            chunks.append(shell.recv(65535).decode("utf-8", errors="replace"))
            last = time.time()
        elif time.time() - last >= idle:
            break
        else:
            time.sleep(0.05)
    return "".join(chunks)


def live_probe(host: str, username: str, password: str, sections: dict, out_dir: Path, port=22):
    try:
        import paramiko
    except ImportError:
        raise SystemExit("Paramiko missing. Install it with: pip install paramiko")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        port=port,
        username=username,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
        auth_timeout=10,
        banner_timeout=10,
    )

    shell = client.invoke_shell(width=220, height=1000)
    time.sleep(0.5)
    _read_shell(shell)

    rows = []

    # Probe only sections that contain at least one CLI-backed attribute.
    candidates = []
    for section, data in sections.items():
        attrs = data.get("attributes_flat") or {}
        if any("cli_reference" in source_set(rec or {}) for rec in attrs.values()):
            candidates.append(section)

    for i, section in enumerate(candidates, 1):
        cli_path = section.replace(".", " ")
        shell.send(f"config {cli_path}\n")
        time.sleep(0.10)
        out1 = _read_shell(shell, max_wait=1.5)

        has_error = any(p.search(out1) for p in ERROR_PATTERNS)

        if not has_error:
            # Exit without setting/changing anything.
            shell.send("end\n")
            time.sleep(0.08)
            out2 = _read_shell(shell, max_wait=1.0)
            text = out1 + "\n" + out2
            status = "CLI_SECTION_ACCEPTED"
        else:
            shell.send("end\n")
            time.sleep(0.05)
            _read_shell(shell, max_wait=0.5)
            text = out1
            status = "CLI_SECTION_REJECTED_OR_CONTEXTUAL"

        rows.append({
            "section": section,
            "cli_path": cli_path,
            "status": status,
            "output": re.sub(r"\s+", " ", text).strip()[:1000],
        })

        if i % 25 == 0:
            print(f"[LIVE] {i}/{len(candidates)} sections probed")

    shell.close()
    client.close()

    path = out_dir / "live_cli_section_probe.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["section", "cli_path", "status", "output"])
        w.writeheader()
        w.writerows(rows)

    accepted = sum(1 for r in rows if r["status"] == "CLI_SECTION_ACCEPTED")
    rejected = len(rows) - accepted
    return {
        "probed": len(rows),
        "accepted": accepted,
        "rejected_or_contextual": rejected,
        "report": str(path),
    }


def print_table(feature_rows):
    print()
    print("=" * 118)
    print("FEATURE COVERAGE")
    print("=" * 118)
    print(f"{'FEATURE':30} {'SEC':>5} {'ATTR':>7} {'CLI':>7} {'CONS':>7} {'TF':>7} {'ANS':>7} {'META':>7} {'CLI%':>7}  STATUS")
    print("-" * 118)
    for r in feature_rows:
        print(
            f"{r['feature'][:30]:30} "
            f"{r['sections']:5} "
            f"{r['attributes']:7} "
            f"{r['authoritative_cli']:7} "
            f"{r['secondary_consensus']:7} "
            f"{r['secondary_terraform']:7} "
            f"{r['secondary_ansible']:7} "
            f"{r['provider_metadata']:7} "
            f"{r['authoritative_ratio_non_provider_pct']:6.1f}%  "
            f"{r['status']}"
        )


def main():
    ap = argparse.ArgumentParser(description="Full FortiOS KB validation")
    ap.add_argument("--version", default="7.6.7")
    ap.add_argument("--kb-root", default=None)
    ap.add_argument("--live", action="store_true", help="Read-only CLI section probe on a FortiGate")
    ap.add_argument("--host", default="192.168.52.131")
    ap.add_argument("--username", default="admin")
    ap.add_argument("--port", default=22, type=int)
    args = ap.parse_args()

    version_root = Path(args.kb_root or f"knowledge_base/fortios/{args.version}")
    out_dir = version_root / "audit" / "full_validation"

    print()
    print("=" * 80)
    print(f"FORTIOS {args.version} - FULL KB VALIDATION")
    print("=" * 80)
    print("KB root:", version_root)

    sections, feature_stats, section_rows, attr_rows, gs, blockers = analyze(version_root)
    feature_rows = write_reports(out_dir, args.version, feature_stats, section_rows, attr_rows, gs, blockers)

    print()
    print("Sections           :", gs["sections"])
    print("Attributes         :", gs["attributes"])
    print("AUTHORITATIVE CLI  :", gs["authoritative_cli"])
    print("SECONDARY CONSENSUS:", gs["secondary_consensus"])
    print("SECONDARY TERRAFORM:", gs["secondary_terraform"])
    print("SECONDARY ANSIBLE  :", gs["secondary_ansible"])
    print("PROVIDER METADATA  :", gs["provider_metadata"])
    print("UNCLASSIFIED       :", gs["unclassified"])
    print("Structural blockers:", gs["blockers"])

    print_table(feature_rows)

    if blockers:
        print()
        print("STRUCTURAL RESULT: FAIL")
        print("The KB has blocking structural issues.")
    else:
        print()
        print("STRUCTURAL RESULT: PASS")
        print("Every canonical attribute is classified and structurally usable.")

    print()
    print("Reports:")
    print(" -", out_dir / "feature_coverage.csv")
    print(" -", out_dir / "section_coverage.csv")
    print(" -", out_dir / "attribute_inventory.csv")
    print(" -", out_dir / "kb_full_validation_summary.yaml")

    if args.live:
        print()
        print("=" * 80)
        print("READ-ONLY LIVE CLI SECTION PROBE")
        print("=" * 80)
        print("This does not set values or save configuration.")
        password = getpass.getpass(f"Password for {args.username}@{args.host}: ")
        live = live_probe(args.host, args.username, password, sections, out_dir, args.port)
        print("Probed                :", live["probed"])
        print("Accepted              :", live["accepted"])
        print("Rejected/contextual   :", live["rejected_or_contextual"])
        print("Live report           :", live["report"])
        print()
        print("NOTE: a rejected section is not automatically a bad KB entry.")
        print("Some commands depend on VDOM/global context, license, model, or runtime state.")

    print()
    print("=" * 80)
    print("DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()

