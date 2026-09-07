from __future__ import annotations

import argparse
import csv
import getpass
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import yaml

try:
    import paramiko
except ImportError:
    raise SystemExit("Paramiko missing. Install with: pip install paramiko")


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

PROMPT_RE = re.compile(r"(?m)^[^\r\n]*[#$>]\s*$")


def feature_of(section: str) -> str:
    for name, fn in FEATURE_RULES:
        if fn(section):
            return name
    return "Other"


def sources_of(record: dict) -> set[str]:
    src = record.get("sources") or []
    if isinstance(src, str):
        return {src}
    return {str(x) for x in src}


def trust_of(record: dict, attr: str) -> str:
    src = sources_of(record)
    leaf = attr.split(".")[-1]
    if src == {"terraform"} and leaf in PROVIDER_META_LEAFS:
        return "provider_metadata"
    if "cli_reference" in src:
        return "authoritative_cli"
    if {"ansible", "terraform"}.issubset(src):
        return "secondary_consensus"
    if src == {"terraform"}:
        return "secondary_terraform"
    if src == {"ansible"}:
        return "secondary_ansible"
    return "unclassified"


def norm(s: str) -> str:
    return str(s).strip().lower().replace("_", "-").replace(" ", "-")


def load_kb(root: Path):
    sections = {}
    for p in sorted((root / "canonical").glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        sid = str(data.get("id") or p.stem)
        sections[sid] = data
    return sections


def read_shell(shell, idle=0.30, max_wait=3.0):
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


def send(shell, command: str, wait=0.12, max_wait=2.0):
    shell.send(command + "\n")
    time.sleep(wait)
    return read_shell(shell, max_wait=max_wait)


def has_error(text: str) -> bool:
    return any(p.search(text) for p in ERROR_PATTERNS)


def parse_help_keys(text: str) -> set[str]:
    """
    FortiOS help usually emits lines such as:
      hostname    FortiGate hostname.
      status      Enable/disable ...
    This parser is intentionally permissive.
    """
    keys = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("FGT", "FortiGate")) and ("#" in line or ">" in line):
            continue
        if line.startswith(("set ?", "config ?", "?")):
            continue
        if line.startswith(("Command fail", "parse error", "Return code")):
            continue

        # Strip common prompt prefix if echoed.
        if "#" in line:
            maybe = line.split("#", 1)[-1].strip()
            if maybe.startswith(("set ?", "config ?")):
                continue

        token = re.split(r"\s{2,}|\t+", line, maxsplit=1)[0].strip()
        if not token or " " in token:
            continue

        # Conservative command-key shape.
        if re.fullmatch(r"[A-Za-z0-9_.:/-]+", token):
            keys.add(norm(token))
    return keys


def top_level_inventory(section_data: dict):
    """
    Compare only top-level canonical attributes safely.
    Nested fields like health_check.interval are represented by their parent
    'health-check' in the current section. They need deeper context and are
    reported separately instead of being falsely marked wrong.
    """
    attrs = section_data.get("attributes_flat") or {}

    top = {}
    nested = []
    for attr, rec in attrs.items():
        rec = rec or {}
        trust = trust_of(rec, attr)
        if trust == "provider_metadata":
            continue

        if "." in attr:
            nested.append((attr, rec, trust))
            continue

        top[attr] = (rec, trust)

    return top, nested


def probe_section(shell, section: str):
    cli_path = section.replace(".", " ")

    out_enter = send(shell, f"config {cli_path}", max_wait=1.7)
    if has_error(out_enter):
        # Make sure we are back at root-ish context.
        send(shell, "end", max_wait=0.7)
        return {
            "accepted": False,
            "cli_path": cli_path,
            "set_keys": set(),
            "config_keys": set(),
            "raw": out_enter,
        }

    out_set = send(shell, "set ?", max_wait=1.8)
    out_cfg = send(shell, "config ?", max_wait=1.8)

    # Exit only; no set/edit/next/delete/unset is ever issued.
    out_end = send(shell, "end", max_wait=1.0)

    return {
        "accepted": True,
        "cli_path": cli_path,
        "set_keys": parse_help_keys(out_set),
        "config_keys": parse_help_keys(out_cfg),
        "raw": out_enter + "\n" + out_set + "\n" + out_cfg + "\n" + out_end,
    }


def main():
    ap = argparse.ArgumentParser(description="Read-only FortiOS KB live attribute probe")
    ap.add_argument("--version", default="7.6.7")
    ap.add_argument("--kb-root", default=None)
    ap.add_argument("--host", default="192.168.52.131")
    ap.add_argument("--username", default="admin")
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument(
        "--feature",
        default=None,
        help='Optional feature filter, e.g. "SD-WAN", "VPN", "Routing", "ZTNA"',
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of sections to probe (0 = all matching sections)",
    )
    args = ap.parse_args()

    kb_root = Path(args.kb_root or f"knowledge_base/fortios/{args.version}")
    out_dir = kb_root / "audit" / "live_attribute_probe"
    out_dir.mkdir(parents=True, exist_ok=True)

    sections = load_kb(kb_root)
    if not sections:
        raise SystemExit(f"No canonical sections found under {kb_root / 'canonical'}")

    candidates = []
    for section, data in sections.items():
        feature = feature_of(section)
        if args.feature and feature.lower() != args.feature.lower():
            continue
        top, nested = top_level_inventory(data)
        if top or nested:
            candidates.append((section, feature, data, top, nested))

    if args.limit > 0:
        candidates = candidates[:args.limit]

    print()
    print("=" * 88)
    print(f"FORTIOS {args.version} - READ-ONLY LIVE KB ATTRIBUTE PROBE")
    print("=" * 88)
    print("Target   :", args.host)
    print("Sections :", len(candidates))
    if args.feature:
        print("Feature  :", args.feature)
    print()
    print("Safety: this script sends only:")
    print("  config <section>")
    print("  set ?")
    print("  config ?")
    print("  end")
    print("It does NOT send set/edit/next/delete/unset.")
    print()

    password = getpass.getpass(f"Password for {args.username}@{args.host}: ")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        args.host,
        port=args.port,
        username=args.username,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
        auth_timeout=10,
        banner_timeout=10,
    )

    shell = client.invoke_shell(width=240, height=1200)
    time.sleep(0.5)
    read_shell(shell)

    section_rows = []
    attr_rows = []
    feature_stats = defaultdict(Counter)

    for idx, (section, feature, data, top, nested) in enumerate(candidates, 1):
        probe = probe_section(shell, section)

        sec_counts = Counter()
        sec_counts["sections"] = 1
        sec_counts["top_level_kb"] = len(top)
        sec_counts["nested_kb"] = len(nested)

        if not probe["accepted"]:
            section_status = "SECTION_REJECTED_OR_CONTEXTUAL"
            sec_counts["section_rejected"] = 1

            for attr, (rec, trust) in top.items():
                attr_rows.append({
                    "feature": feature,
                    "section": section,
                    "attribute": attr,
                    "trust": trust,
                    "device_status": "NOT_TESTED_SECTION_REJECTED",
                    "device_key": "",
                    "note": "Section rejected or unavailable in this VM/context.",
                })

            for attr, rec, trust in nested:
                attr_rows.append({
                    "feature": feature,
                    "section": section,
                    "attribute": attr,
                    "trust": trust,
                    "device_status": "NESTED_NOT_PROBED",
                    "device_key": "",
                    "note": "Nested attribute requires deeper CLI context.",
                })

        else:
            section_status = "SECTION_ACCEPTED"
            sec_counts["section_accepted"] = 1

            exposed = probe["set_keys"] | probe["config_keys"]

            for attr, (rec, trust) in top.items():
                target = norm(attr)
                found = target in exposed

                if found:
                    status = "DEVICE_CONFIRMED"
                    sec_counts["device_confirmed"] += 1
                else:
                    status = "NOT_EXPOSED_TOPLEVEL"
                    sec_counts["not_exposed"] += 1

                attr_rows.append({
                    "feature": feature,
                    "section": section,
                    "attribute": attr,
                    "trust": trust,
                    "device_status": status,
                    "device_key": target if found else "",
                    "note": "",
                })

            for attr, rec, trust in nested:
                parent = norm(attr.split(".", 1)[0])
                parent_seen = parent in exposed

                if parent_seen:
                    status = "NESTED_PARENT_CONFIRMED"
                    sec_counts["nested_parent_confirmed"] += 1
                else:
                    status = "NESTED_NOT_PROBED"
                    sec_counts["nested_not_probed"] += 1

                attr_rows.append({
                    "feature": feature,
                    "section": section,
                    "attribute": attr,
                    "trust": trust,
                    "device_status": status,
                    "device_key": parent if parent_seen else "",
                    "note": "Nested leaf not directly probed; parent context only.",
                })

        feature_stats[feature].update(sec_counts)

        section_rows.append({
            "feature": feature,
            "section": section,
            "status": section_status,
            "kb_top_level_attributes": len(top),
            "kb_nested_attributes": len(nested),
            "device_set_keys": len(probe["set_keys"]),
            "device_config_keys": len(probe["config_keys"]),
            "device_confirmed_top_level": sec_counts["device_confirmed"],
            "not_exposed_top_level": sec_counts["not_exposed"],
            "nested_parent_confirmed": sec_counts["nested_parent_confirmed"],
        })

        if idx % 10 == 0 or idx == len(candidates):
            print(f"[PROBE] {idx}/{len(candidates)} sections")

    shell.close()
    client.close()

    # Write CSVs.
    section_csv = out_dir / "section_live_probe.csv"
    with section_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(section_rows[0].keys()) if section_rows else ["feature"])
        w.writeheader()
        w.writerows(section_rows)

    attr_csv = out_dir / "attribute_live_probe.csv"
    with attr_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(attr_rows[0].keys()) if attr_rows else ["feature"])
        w.writeheader()
        w.writerows(attr_rows)

    # Feature summary.
    feature_rows = []
    for feature in sorted(feature_stats):
        st = feature_stats[feature]
        tested_top = st["device_confirmed"] + st["not_exposed"]
        confirmed_pct = (st["device_confirmed"] / tested_top * 100.0) if tested_top else 0.0
        feature_rows.append({
            "feature": feature,
            "sections": st["sections"],
            "section_accepted": st["section_accepted"],
            "section_rejected_or_contextual": st["section_rejected"],
            "top_level_tested": tested_top,
            "device_confirmed": st["device_confirmed"],
            "not_exposed_top_level": st["not_exposed"],
            "nested_parent_confirmed": st["nested_parent_confirmed"],
            "nested_not_probed": st["nested_not_probed"],
            "confirmed_pct_top_level": round(confirmed_pct, 2),
        })

    feature_csv = out_dir / "feature_live_probe.csv"
    with feature_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(feature_rows[0].keys()) if feature_rows else ["feature"])
        w.writeheader()
        w.writerows(feature_rows)

    print()
    print("=" * 118)
    print("LIVE FEATURE RESULT")
    print("=" * 118)
    print(f"{'FEATURE':30} {'SEC':>5} {'OKSEC':>6} {'CTX':>6} {'TEST':>7} {'CONF':>7} {'MISS':>7} {'CONF%':>8}")
    print("-" * 118)

    for r in feature_rows:
        print(
            f"{r['feature'][:30]:30} "
            f"{r['sections']:5} "
            f"{r['section_accepted']:6} "
            f"{r['section_rejected_or_contextual']:6} "
            f"{r['top_level_tested']:7} "
            f"{r['device_confirmed']:7} "
            f"{r['not_exposed_top_level']:7} "
            f"{r['confirmed_pct_top_level']:7.1f}%"
        )

    print()
    print("Reports:")
    print(" -", feature_csv)
    print(" -", section_csv)
    print(" -", attr_csv)
    print()
    print("Interpretation:")
    print(" DEVICE_CONFIRMED        = KB top-level key exposed by this FortiOS CLI context")
    print(" NOT_EXPOSED_TOPLEVEL    = investigate; not automatically a bad KB entry")
    print(" NESTED_PARENT_CONFIRMED = parent context exists; deeper leaf still needs a scenario test")
    print(" SECTION_REJECTED...     = may be VM/model/license/VDOM/context specific")
    print()


if __name__ == "__main__":
    main()
