from pathlib import Path
import re
import shutil

path = Path("kb_builder/reconcile.py")

backup = Path(
    "kb_builder/reconcile.py.before_terraform_deprecation_fix.bak"
)

if not backup.exists():
    shutil.copy2(path, backup)

text = path.read_text(
    encoding="utf-8"
)

helper = r'''
def terraform_resource_name(section_id: str) -> str:
    """
    Convertit l'ID RAW Terraform vers le nom du resource provider.

    Exemples:
      firewall.security_policy
        -> fortios_firewall_security_policy

      vpnipsec.phase1interface
        -> fortios_vpnipsec_phase1interface
    """

    return (
        "fortios_"
        + str(section_id).replace(".", "_")
    )


def discover_terraform_deprecations(
    terraform_map,
    repo_root=Path(".work/terraform")
):
    """
    Détecte automatiquement les resources Terraform legacy
    à partir de la documentation du provider.

    Aucune règle FortiOS/version n'est hardcodée.
    """

    docs_root = (
        repo_root
        / "website"
        / "docs"
        / "r"
    )

    result = {}

    if not docs_root.exists():
        return result

    resource_to_section = {
        terraform_resource_name(sid): sid
        for sid in terraform_map
    }

    pattern = re.compile(
        r"replaced\s+by\s+new\s+resource"
        r"\s+[`'\"]"
        r"(fortios_[A-Za-z0-9_]+)"
        r"[`'\"]",
        re.IGNORECASE
    )

    for sid in terraform_map:

        resource = terraform_resource_name(
            sid
        )

        doc = (
            docs_root
            / f"{resource}.html.markdown"
        )

        if not doc.exists():
            continue

        try:
            content = doc.read_text(
                encoding="utf-8",
                errors="ignore"
            )
        except Exception:
            continue

        match = pattern.search(
            content
        )

        if not match:
            continue

        replacement_resource = (
            match.group(1)
        )

        replacement_sid = (
            resource_to_section.get(
                replacement_resource
            )
        )

        # On ne retire le legacy que si
        # le remplacement existe réellement
        # dans cette release du provider.
        if replacement_sid:

            result[sid] = {
                "legacy_resource":
                    resource,

                "legacy_section_id":
                    sid,

                "replacement_resource":
                    replacement_resource,

                "replacement_section_id":
                    replacement_sid,

                "documentation":
                    str(doc),
            }

    return result
'''

marker = "def reconcile_all("

if "def discover_terraform_deprecations(" not in text:

    if marker not in text:
        raise RuntimeError(
            "reconcile_all introuvable"
        )

    text = text.replace(
        marker,
        helper.rstrip()
        + "\n\n\n"
        + marker,
        1
    )


old_block = '''    # -----------------------------------------------------
    # 5. TERRAFORM -> CLI / ANSIBLE
    # -----------------------------------------------------

    t, terraform_aliases, terraform_collisions = (
        remap_source_sections(
            t_raw,
            authority_index,
            "terraform"
        )
    )
'''

new_block = '''    # -----------------------------------------------------
    # 5. Détecter les anciens resources Terraform
    #
    # Ils restent dans RAW pour la provenance,
    # mais ne participent pas à la vérité canonique
    # lorsqu'un remplacement officiel existe.
    # -----------------------------------------------------

    terraform_deprecations = (
        discover_terraform_deprecations(
            t_raw
        )
    )

    deprecated_terraform_ids = set(
        terraform_deprecations
    )

    t_primary_raw = {
        sid: item
        for sid, item in t_raw.items()
        if sid not in deprecated_terraform_ids
    }

    dump_yaml(
        root
        / "audit"
        / "terraform_deprecations.yaml",
        {
            "version": version,
            "deprecated_count":
                len(terraform_deprecations),
            "resources":
                terraform_deprecations,
        }
    )


    # -----------------------------------------------------
    # 6. TERRAFORM ACTIF -> CLI / ANSIBLE
    # -----------------------------------------------------

    t, terraform_aliases, terraform_collisions = (
        remap_source_sections(
            t_primary_raw,
            authority_index,
            "terraform"
        )
    )
'''

if old_block not in text:

    raise RuntimeError(
        "Bloc Terraform attendu introuvable. "
        "Aucune modification écrite."
    )

text = text.replace(
    old_block,
    new_block,
    1
)

path.write_text(
    text,
    encoding="utf-8"
)

print()
print(
    "[OK] Détection générique des resources Terraform deprecated installée"
)

print(
    "[OK] RAW reste intact"
)

print(
    "[OK] Les resources legacy sont exclus du canonical"
)

print(
    "[OK] Rapport: audit/terraform_deprecations.yaml"
)

print(
    "[BACKUP]",
    backup
)
