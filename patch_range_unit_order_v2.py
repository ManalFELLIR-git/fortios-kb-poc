from pathlib import Path
import shutil
import re

path = Path("resolve_range_conflicts.py")
backup = Path("resolve_range_conflicts.py.before_unit_order_fix_v2.bak")

if not backup.exists():
    shutil.copy2(path, backup)

text = path.read_text(encoding="utf-8")


def find_rule(number, phrase):
    pattern = re.compile(
        rf"(?m)^    # RULE {number} — {re.escape(phrase)}.*$"
    )

    match = pattern.search(text)

    if not match:
        raise RuntimeError(
            f"RULE {number} introuvable : {phrase}"
        )

    # Revenir au début du séparateur =====
    start = text.rfind(
        "    # ========================================================",
        0,
        match.start()
    )

    if start == -1:
        start = match.start()

    return start


p3 = find_rule(
    3,
    "Ansible confirme exactement la CLI"
)

# Formulation volontairement plus courte :
# fonctionne avec "au lieu deCLI" ou "au lieu de CLI"
p4_match = re.search(
    r"(?m)^    # RULE 4 — Ansible confirme Terraform.*$",
    text
)

if not p4_match:
    raise RuntimeError("RULE 4 introuvable")

p4 = text.rfind(
    "    # ========================================================",
    0,
    p4_match.start()
)

p5 = find_rule(
    5,
    "unités différentes"
)

p6_match = re.search(
    r"(?m)^    # RULE 6 — Ansible possède un troisième range.*$",
    text
)

if not p6_match:
    raise RuntimeError("RULE 6 introuvable")

p6 = text.rfind(
    "    # ========================================================",
    0,
    p6_match.start()
)


if not (
    p3 < p4 < p5 < p6
):
    raise RuntimeError(
        "Ordre actuel inattendu. Aucun changement effectué."
    )


block3 = text[p3:p4]
block4 = text[p4:p5]
block5 = text[p5:p6]


# Renumérotation des commentaires uniquement
block5 = block5.replace(
    "# RULE 5 —",
    "# RULE 3 —",
    1
)

block3 = block3.replace(
    "# RULE 3 —",
    "# RULE 4 —",
    1
)

block4 = block4.replace(
    "# RULE 4 —",
    "# RULE 5 —",
    1
)


new_text = (
    text[:p3]
    + block5
    + block3
    + block4
    + text[p6:]
)


path.write_text(
    new_text,
    encoding="utf-8"
)

print("[OK] Ordre corrigé")
print("[OK] RULE 3 = unités différentes")
print("[OK] RULE 4 = Ansible confirme CLI")
print("[OK] RULE 5 = Ansible confirme Terraform")
print("[BACKUP]", backup)
