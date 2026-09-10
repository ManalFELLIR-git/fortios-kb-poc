from pathlib import Path
import shutil

path = Path("kb_builder/build.py")
backup = Path("kb_builder/build.py.before_version_arg.bak")

if not backup.exists():
    shutil.copy2(path, backup)

new_content = r'''from __future__ import annotations

from pathlib import Path
import argparse
import json
import re

from .utils import load_yaml, dump_yaml
from .bootstrap import clone_pinned
from .ansible_extractor import extract_all as extract_ansible
from .terraform_extractor import extract_all as extract_terraform
from .fortinet_docs import build_docs
from .reconcile import reconcile_all
from .audit import audit


VERSION_RE = re.compile(
    r"^\d+\.\d+\.\d+$"
)


def validate_version(version: str) -> str:
    version = str(version).strip()

    if not VERSION_RE.fullmatch(version):
        raise ValueError(
            f"Version FortiOS invalide: {version!r}. "
            "Format attendu: X.Y.Z"
        )

    return version


def validate_expected_commit(
    source_name: str,
    actual_commit: str,
    source_cfg: dict,
):
    """
    Vérifie le commit uniquement lorsque expected_commit
    est fourni dans sources.yaml.
    """

    expected = source_cfg.get(
        "expected_commit"
    )

    if not expected:
        return

    if actual_commit.lower() != str(expected).lower():
        raise RuntimeError(
            f"{source_name}: commit inattendu.\n"
            f"Expected: {expected}\n"
            f"Actual  : {actual_commit}"
        )


def docs_are_pinned_to_other_version(
    docs_cfg: dict,
    config_version: str,
    target_version: str,
) -> bool:
    """
    Protection anti-contamination.

    Si l'utilisateur demande une autre version mais que
    les URLs docs contiennent encore explicitement la
    version du YAML, on refuse de scraper ces docs.

    La résolution dynamique des URLs sera ajoutée dans
    l'étape suivante.
    """

    if target_version == config_version:
        return False

    for key, value in docs_cfg.items():

        if key == "base_host":
            continue

        if (
            isinstance(value, str)
            and config_version in value
        ):
            return True

    return False


def main(argv=None):

    ap = argparse.ArgumentParser(
        description=(
            "FortiOS canonical KB builder"
        )
    )

    ap.add_argument(
        "--config",
        default="config/sources.yaml",
    )

    ap.add_argument(
        "--version",
        default=None,
        help=(
            "FortiOS target version, e.g. 7.6.7. "
            "Defaults to target.version in sources.yaml."
        ),
    )

    ap.add_argument(
        "--work",
        default=".work",
    )

    ap.add_argument(
        "--output",
        default=None,
        help=(
            "Output directory. Default: "
            "knowledge_base/fortios/<version>"
        ),
    )

    ap.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Use already-present source repos",
    )

    ap.add_argument(
        "--skip-docs",
        action="store_true",
    )

    ap.add_argument(
        "--docs-max-pages",
        type=int,
        default=100,
        help=(
            "Per document family; "
            "0 = unlimited"
        ),
    )

    args = ap.parse_args(argv)


    # --------------------------------------------------
    # Configuration
    # --------------------------------------------------

    cfg = load_yaml(
        Path(args.config)
    )

    config_version = validate_version(
        cfg["target"]["version"]
    )

    version = validate_version(
        args.version
        if args.version
        else config_version
    )


    # --------------------------------------------------
    # Output dynamique
    # --------------------------------------------------

    if args.output:

        out = Path(
            args.output
        )

    else:

        out = (
            Path("knowledge_base")
            / "fortios"
            / version
        )


    work = Path(
        args.work
    )

    out.mkdir(
        parents=True,
        exist_ok=True
    )


    src = cfg["sources"]

    ans_dir = (
        work
        / "ansible"
    )

    tf_dir = (
        work
        / "terraform"
    )


    # --------------------------------------------------
    # Protection docs
    # --------------------------------------------------

    docs_cfg = src.get(
        "fortinet_docs",
        {}
    )

    if (
        not args.skip_docs
        and docs_are_pinned_to_other_version(
            docs_cfg,
            config_version,
            version,
        )
    ):

        raise RuntimeError(
            "\n"
            "Fortinet documentation URLs are still "
            f"pinned to {config_version}, while the "
            f"requested target is {version}.\n"
            "\n"
            "The builder refuses to mix documentation "
            "from different FortiOS versions.\n"
            "\n"
            "Use --skip-docs only for a controlled "
            "structured-source test, or configure "
            "version-aware Fortinet document discovery."
        )


    metadata = {

        "version":
            version,

        "config_target_version":
            config_version,

        "sources":
            {},
    }


    # --------------------------------------------------
    # Bootstrap
    # --------------------------------------------------

    if not args.no_bootstrap:

        asha = clone_pinned(
            src["ansible"]["repository"],
            src["ansible"]["tag"],
            ans_dir,
        )

        validate_expected_commit(
            "ansible",
            asha,
            src["ansible"],
        )


        tsha = clone_pinned(
            src["terraform"]["repository"],
            src["terraform"]["tag"],
            tf_dir,
        )

        validate_expected_commit(
            "terraform",
            tsha,
            src["terraform"],
        )


        metadata[
            "sources"
        ][
            "ansible"
        ] = {
            "tag":
                src["ansible"]["tag"],

            "commit":
                asha,
        }


        metadata[
            "sources"
        ][
            "terraform"
        ] = {
            "tag":
                src["terraform"]["tag"],

            "commit":
                tsha,
        }


    # --------------------------------------------------
    # Structured extraction
    # --------------------------------------------------

    errors = []


    a, e = extract_ansible(
        ans_dir
        / src["ansible"]["modules_dir"],

        version,

        out
        / "raw"
        / "ansible",
    )

    errors += e


    t, e = extract_terraform(
        tf_dir
        / src["terraform"]["resources_dir"],

        version,

        out
        / "raw"
        / "terraform",

        tf_dir
        / src["terraform"]["docs_dir"],
    )

    errors += e


    metadata[
        "extraction"
    ] = {

        "ansible_sections":
            len(a),

        "terraform_sections":
            len(t),
    }


    # --------------------------------------------------
    # Official Fortinet documentation
    # --------------------------------------------------

    if not args.skip_docs:

        ds, de = build_docs(
            version,
            docs_cfg,
            out / "raw" / "docs",
            args.docs_max_pages,
        )

        metadata[
            "docs"
        ] = ds

        errors += de


    # --------------------------------------------------
    # Metadata
    # --------------------------------------------------

    dump_yaml(
        out / "metadata.yaml",
        metadata,
    )


    # --------------------------------------------------
    # Reconciliation
    # --------------------------------------------------

    reconcile_all(
        out,
        version,
    )


    # --------------------------------------------------
    # Audit
    # --------------------------------------------------

    report = audit(
        out,
        version,
        errors,
    )

    print(
        json.dumps(
            report,
            indent=2,
            default=str,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
'''

path.write_text(
    new_content,
    encoding="utf-8"
)

print()
print("[OK] build.py patché")
print("[OK] --version ajouté")
print("[OK] output dynamique")
print("[OK] validation format X.Y.Z")
print("[OK] protection anti-mélange des docs")
print("[OK] vérification expected_commit ajoutée")
print("[BACKUP]", backup)
