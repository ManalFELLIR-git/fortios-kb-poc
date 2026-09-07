from pathlib import Path
import yaml

ROOT = Path(
    "knowledge_base/fortios/7.6.7/canonical"
)

counts = {
    "ansible": 0,
    "terraform": 0,
    "cli": 0,
    "a_t": 0,
    "a_c": 0,
    "t_c": 0,
    "all3": 0,
    "only_a": 0,
    "only_t": 0,
    "only_c": 0,
}

for p in ROOT.glob("*.yaml"):

    data = yaml.safe_load(
        p.read_text(
            encoding="utf-8"
        )
    )

    presence = data.get(
        "source_presence",
        {}
    )

    a = bool(
        presence.get("ansible")
    )

    t = bool(
        presence.get("terraform")
    )

    c = bool(
        presence.get("cli_reference")
    )

    counts["ansible"] += a
    counts["terraform"] += t
    counts["cli"] += c

    counts["a_t"] += (
        a and t
    )

    counts["a_c"] += (
        a and c
    )

    counts["t_c"] += (
        t and c
    )

    counts["all3"] += (
        a and t and c
    )

    counts["only_a"] += (
        a and not t and not c
    )

    counts["only_t"] += (
        t and not a and not c
    )

    counts["only_c"] += (
        c and not a and not t
    )


print(
    "=== MAPPED OVERLAPS ==="
)

print(
    "Ansible             :",
    counts["ansible"]
)

print(
    "Terraform           :",
    counts["terraform"]
)

print(
    "CLI                 :",
    counts["cli"]
)

print()

print(
    "Ansible ∩ Terraform :",
    counts["a_t"]
)

print(
    "Ansible ∩ CLI       :",
    counts["a_c"]
)

print(
    "Terraform ∩ CLI     :",
    counts["t_c"]
)

print(
    "ALL 3               :",
    counts["all3"]
)

print()

print(
    "Only Ansible        :",
    counts["only_a"]
)

print(
    "Only Terraform      :",
    counts["only_t"]
)

print(
    "Only CLI            :",
    counts["only_c"]
)
