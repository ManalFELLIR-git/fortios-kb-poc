from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin, urlparse
import re
import time

from bs4 import BeautifulSoup

from .fortinet_docs import fetch, clean_text
from .utils import dump_yaml


def normalize_url(url: str):
    return (
        url
        .split("#", 1)[0]
        .split("?", 1)[0]
        .rstrip("/")
    )


def page_text(html: str):
    soup = BeautifulSoup(html, "html.parser")

    # Enlever le bruit de navigation autant que possible.
    for tag in soup.find_all(
        ["script", "style", "nav", "footer", "noscript"]
    ):
        tag.decompose()

    return clean_text(
        soup.get_text("\n")
    )


def page_title(html: str):
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")

    if h1:
        return clean_text(
            h1.get_text(" ")
        )

    title = soup.find("title")

    if title:
        return clean_text(
            title.get_text(" ")
        )

    return ""


def extract_cli_sections(html: str):
    """
    Cherche les commandes 'config ...' présentes
    dans les exemples CLI d'une page Admin Guide.
    """

    soup = BeautifulSoup(html, "html.parser")

    texts = []

    for node in soup.find_all(
        ["pre", "code"]
    ):
        texts.append(
            node.get_text("\n")
        )

    # fallback : certains exemples ne sont pas dans <pre>
    texts.append(
        soup.get_text("\n")
    )

    sections = set()

    pattern = re.compile(
        r"(?im)^\s*config\s+"
        r"([a-z0-9_-]+(?:\s+[a-z0-9_-]+)+)"
        r"\s*$"
    )

    for text in texts:

        for match in pattern.finditer(
            text
        ):

            value = (
                match.group(1)
                .strip()
                .lower()
                .replace(" ", ".")
            )

            sections.add(
                value
            )

    return sorted(
        sections
    )


def discover_topic_links(
    html: str,
    base_url: str,
    prefix: str,
):
    """
    Ne conserve que les vraies pages de contenu Fortinet :

      /administration-guide/<NUMERIC-ID>/...
      /fortios-release-notes/<NUMERIC-ID>/...
      /new-features/<NUMERIC-ID>/...

    Les pages /search et autres index ne sont pas
    considérées comme des topics finaux.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    links = set()

    prefix = normalize_url(
        prefix
    )

    for a in soup.find_all(
        "a",
        href=True
    ):

        url = normalize_url(
            urljoin(
                base_url,
                a["href"]
            )
        )

        if not url.startswith(
            prefix + "/"
        ):
            continue

        tail = url[
            len(prefix) + 1:
        ]

        first = (
            tail.split("/", 1)[0]
        )

        if first.isdigit():
            links.add(
                url
            )

    return sorted(
        links
    )


def crawl_topics(
    seed: str,
    prefix: str,
    version: str,
    kind: str,
    delay: float = 0.10,
):
    """
    Crawl ciblé des pages de contenu uniquement.

    Il découvre les liens de topics au fur et à mesure,
    mais ne traverse pas les autres familles documentaires.
    """

    seed = normalize_url(
        seed
    )

    prefix = normalize_url(
        prefix
    )

    queue = [seed]
    seen = set()
    discovered_topics = set()

    pages = []
    errors = []


    while queue:

        url = queue.pop(0)

        if url in seen:
            continue

        seen.add(
            url
        )

        try:

            html = fetch(
                url
            )

        except Exception as exc:

            errors.append({
                "kind": kind,
                "url": url,
                "error": repr(exc),
            })

            continue


        links = discover_topic_links(
            html,
            url,
            prefix,
        )


        for link in links:

            discovered_topics.add(
                link
            )

            if (
                link not in seen
                and link not in queue
            ):
                queue.append(
                    link
                )


        # Le seed peut être /search :
        # on ne le stocke pas comme topic.
        if url != seed:

            item = {
                "version":
                    version,

                "kind":
                    kind,

                "title":
                    page_title(html),

                "source_url":
                    url,

                "content":
                    page_text(html),

                "cli_sections":
                    extract_cli_sections(
                        html
                    ),
            }

            pages.append(
                item
            )


        if (
            len(seen) % 50
            == 0
        ):

            print(
                f"[{kind.upper()}] "
                f"visited={len(seen)} "
                f"topics={len(pages)} "
                f"queue={len(queue)}",
                flush=True
            )


        if delay:
            time.sleep(
                delay
            )


    return pages, errors


def build_feature_sources(
    version: str,
    seeds: dict,
    root: Path,
):
    """
    Collecte les sources nécessaires à la Feature KB.

    NE TOUCHE PAS:
      raw/ansible
      raw/terraform
      raw/docs/cli_reference
      canonical/
    """

    out = (
        root
        / "raw"
        / "docs"
    )

    all_errors = []

    # ========================================================
    # ADMIN GUIDE
    # ========================================================

    admin_prefix = (
        f"https://docs.fortinet.com/"
        f"document/fortigate/{version}/"
        f"administration-guide"
    )

    admin, errors = crawl_topics(
        seeds["administration_guide"],
        admin_prefix,
        version,
        "administration_guide",
    )

    all_errors.extend(
        errors
    )

    dump_yaml(
        out
        / "features"
        / "admin_topics_full.yaml",
        {
            "version":
                version,

            "count":
                len(admin),

            "topics":
                admin,
        },
    )


    # ========================================================
    # RELEASE NOTES
    # ========================================================

    rn_prefix = (
        f"https://docs.fortinet.com/"
        f"document/fortigate/{version}/"
        f"fortios-release-notes"
    )

    rn, errors = crawl_topics(
        seeds["release_notes"],
        rn_prefix,
        version,
        "release_notes",
    )

    all_errors.extend(
        errors
    )

    dump_yaml(
        out
        / "version"
        / "release_notes_full.yaml",
        {
            "version":
                version,

            "count":
                len(rn),

            "topics":
                rn,
        },
    )


    # ========================================================
    # NEW FEATURES
    # ========================================================

    # Pour New Features on utilise le prefix du seed,
    # car Fortinet publie parfois 7.6.7 sous l'arbre 7.6.0.
    nf_seed = normalize_url(
        seeds["new_features"]
    )

    parsed = urlparse(
        nf_seed
    )

    parts = (
        parsed.path
        .rstrip("/")
        .split("/")
    )

    # Retirer le dernier élément "7-6-7"
    nf_prefix_path = "/".join(
        parts[:-1]
    )

    nf_prefix = (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"{nf_prefix_path}"
    )

    nf, errors = crawl_topics(
        nf_seed,
        nf_prefix,
        version,
        "new_features",
    )

    all_errors.extend(
        errors
    )


    # Le seed lui-même contient aussi de l'information.
    try:

        html = fetch(
            nf_seed
        )

        nf.insert(
            0,
            {
                "version":
                    version,

                "kind":
                    "new_features",

                "title":
                    page_title(html),

                "source_url":
                    nf_seed,

                "content":
                    page_text(html),

                "cli_sections":
                    extract_cli_sections(
                        html
                    ),
            }
        )

    except Exception as exc:

        all_errors.append({
            "kind":
                "new_features",

            "url":
                nf_seed,

            "error":
                repr(exc),
        })


    dump_yaml(
        out
        / "version"
        / "new_features_full.yaml",
        {
            "version":
                version,

            "count":
                len(nf),

            "topics":
                nf,
        },
    )


    report = {
        "version":
            version,

        "admin_topics":
            len(admin),

        "release_note_topics":
            len(rn),

        "new_feature_topics":
            len(nf),

        "errors":
            len(all_errors),
    }


    dump_yaml(
        root
        / "audit"
        / "feature_source_collection.yaml",
        {
            **report,
            "error_records":
                all_errors,
        },
    )


    return report
