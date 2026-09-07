from __future__ import annotations
from pathlib import Path
from urllib.parse import urljoin, urlparse
import hashlib, json, re, time
import requests
from bs4 import BeautifulSoup
from .utils import dump_yaml, canonical_type

UA = "FortiOS-KB-POC/0.1 (documentation research; respectful crawler)"


def fetch(url: str, timeout=30):
    r = requests.get(url, timeout=timeout, headers={"User-Agent": UA})
    r.raise_for_status()
    return r.text


def clean_text(s):
    return re.sub(r"\s+", " ", s or "").strip()


def parse_size(size: str):
    out = {}
    if not size:
        return out
    m = re.search(r"Minimum value:\s*(-?\d+)", size, re.I)
    if m: out["min"] = int(m.group(1))
    m = re.search(r"Maximum value:\s*(-?\d+)", size, re.I)
    if m: out["max"] = int(m.group(1))
    m = re.search(r"Minimum length:\s*(\d+)", size, re.I)
    if m: out["min_length"] = int(m.group(1))
    m = re.search(r"Maximum length:\s*(\d+)", size, re.I)
    if m: out["max_length"] = int(m.group(1))
    return out


def parse_cli_page(html: str, url: str, version: str):
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.find(["h1", "h2"], string=re.compile(r"^\s*config\s+", re.I))
    if not title_node:
        # fallback to first h1
        h1 = soup.find("h1")
        if not h1 or not clean_text(h1.get_text()).lower().startswith("config "):
            return None
        title_node = h1
    title = clean_text(title_node.get_text())
    section_id = title.lower().removeprefix("config ").replace(" ", ".")
    attrs = {}
    children = {}
    current = attrs
    headings = soup.find_all(["h1", "h2", "h3", "h4"])
    for h in headings:
        htxt = clean_text(h.get_text())
        if h is title_node or htxt == title:
            current = attrs
        elif htxt.lower().startswith("config "):
            cname = htxt.lower().removeprefix("config ").strip().replace(" ", "-")
            children.setdefault(cname, {"attributes": {}})
            current = children[cname]["attributes"]
        else:
            continue
        table = h.find_next("table")
        if not table:
            continue
        # don't accidentally consume a table after another config heading
        between = []
        n = h.next_sibling
        while n is not None and n is not table:
            if getattr(n, "name", None) in {"h1","h2","h3","h4"} and clean_text(n.get_text()).lower().startswith("config "):
                table = None; break
            n = n.next_sibling
        if not table:
            continue
        rows = table.find_all("tr")
        headers = [clean_text(c.get_text()).lower() for c in rows[0].find_all(["th","td"])] if rows else []
        if not headers or "parameter" not in headers:
            continue
        for row in rows[1:]:
            cells = [clean_text(c.get_text(" ")) for c in row.find_all(["th","td"])]
            if len(cells) < 3:
                continue
            cells += [""] * (5-len(cells))
            param, desc, raw_type, size, default = cells[:5]
            name_m = re.match(r"([A-Za-z0-9_-]+)", param)
            if not name_m:
                continue
            name = name_m.group(1)
            spec = {
                "type": canonical_type(raw_type), "raw_type": raw_type,
                "description": desc, "default": default if default else None,
            }
            spec.update(parse_size(size))
            current[name] = {k:v for k,v in spec.items() if v not in (None, "")}
    return {
        "id": section_id,
        "version": version,
        "source": {"kind": "fortinet_cli_reference", "url": url},
        "attributes": attrs,
        "children": children,
    }


def extract_cli_snippets(text: str):
    # Extract config paths from documentation examples.
    paths = set()
    stack = []
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"config\s+([a-zA-Z0-9_-]+(?:\s+[a-zA-Z0-9_-]+)+)", line)
        if m:
            p = m.group(1).strip()
            # top-level config paths usually have at least 2 words; nested names are still useful
            paths.add(p.replace(" ", "."))
    return sorted(paths)


def parse_admin_page(html: str, url: str, version: str):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if not h1:
        return None
    title = clean_text(h1.get_text())
    text = soup.get_text("\n")
    cli = extract_cli_snippets(text)
    return {
        "title": title, "version": version, "source_url": url,
        "cli_sections": cli,
    }


def parse_release_page(html: str, url: str, version: str):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if not h1:
        return None
    title = clean_text(h1.get_text())
    text = clean_text(soup.get_text(" "))
    return {"title": title, "version": version, "source_url": url, "summary_text": text[:8000]}


def discover_links(html: str, base_url: str, allowed_prefixes: list[str]):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        u = urljoin(base_url, a["href"]).split("#",1)[0]
        if any(u.startswith(p) for p in allowed_prefixes):
            out.append(u)
    return sorted(set(out))




def discover_cli_config_links(
    html: str,
    base_url: str,
    version: str,
):
    """
    Découvre uniquement les vraies pages FortiOS:

        config ...

    depuis l'index CLI Reference.

    Aucun crawl récursif vers:
        diagnose
        execute
        get
        tree/category pages

    La logique est indépendante de la version.
    """

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    prefix = (
        f"https://docs.fortinet.com/"
        f"document/fortigate/{version}/"
        f"cli-reference/"
    )

    links = set()

    for a in soup.find_all(
        "a",
        href=True
    ):

        url = urljoin(
            base_url,
            a["href"]
        )

        url = (
            url
            .split("#", 1)[0]
            .split("?", 1)[0]
        )

        if not url.startswith(
            prefix
        ):
            continue

        anchor_text = clean_text(
            a.get_text(" ")
        ).lower()

        slug = (
            urlparse(url)
            .path
            .rstrip("/")
            .split("/")[-1]
            .lower()
        )

        if (
            anchor_text.startswith(
                "config "
            )
            or slug.startswith(
                "config-"
            )
        ):
            links.add(
                url
            )

    return sorted(
        links
    )


def build_cli_reference(
    version: str,
    seed: str,
    out_dir: Path,
    delay: float = 0.15,
):
    """
    Construit la couche CLI Reference complète
    avec collecte ciblée des pages config.

    Le dossier CLI est reconstruit proprement afin
    qu'aucune ancienne page ne survive à un nouveau run.
    """

    errors = []

    target_dir = (
        out_dir
        / "cli_reference"
    )

    target_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    # --------------------------------------------------------
    # Nettoyage atomique logique de l'ancien RAW CLI.
    # On ne mélange jamais un ancien crawl avec le nouveau.
    # --------------------------------------------------------

    for old in target_dir.glob(
        "*.yaml"
    ):
        old.unlink()


    try:

        seed_html = fetch(
            seed
        )

    except Exception as exc:

        errors.append({
            "url": seed,
            "error": repr(exc),
            "stage": "cli_index",
        })

        return {
            "cli_reference_discovered": 0,
            "cli_reference_sections": 0,
            "cli_reference_failed": 1,
        }, errors


    urls = discover_cli_config_links(
        seed_html,
        seed,
        version,
    )


    print(
        f"[CLI] config pages discovered: "
        f"{len(urls)}",
        flush=True
    )


    manifest = []

    seen_ids = {}

    parsed_count = 0


    for index, url in enumerate(
        urls,
        start=1
    ):

        print(
            f"[CLI] "
            f"{index}/{len(urls)} "
            f"{url}",
            flush=True
        )


        try:

            html = fetch(
                url
            )

            item = parse_cli_page(
                html,
                url,
                version,
            )


            if not item:

                error = {
                    "url": url,
                    "error":
                        "page_discovered_as_config_"
                        "but_parser_returned_none",
                    "stage": "cli_parse",
                }

                errors.append(
                    error
                )

                manifest.append({
                    "url": url,
                    "status": "parse_failed",
                })

                continue


            section_id = item[
                "id"
            ]


            # Ne jamais écraser silencieusement
            # deux URLs qui produisent le même ID.
            if section_id in seen_ids:

                error = {
                    "url": url,
                    "error":
                        "duplicate_section_id",
                    "section_id":
                        section_id,
                    "first_url":
                        seen_ids[
                            section_id
                        ],
                    "stage":
                        "cli_duplicate",
                }

                errors.append(
                    error
                )

                manifest.append({
                    "url":
                        url,
                    "status":
                        "duplicate",
                    "section_id":
                        section_id,
                })

                continue


            seen_ids[
                section_id
            ] = url


            dump_yaml(
                target_dir
                / f"{section_id}.yaml",
                item,
            )


            parsed_count += 1


            manifest.append({
                "url":
                    url,
                "status":
                    "parsed",
                "section_id":
                    section_id,
            })


        except Exception as exc:

            errors.append({
                "url":
                    url,
                "error":
                    repr(exc),
                "stage":
                    "cli_fetch_or_parse",
            })

            manifest.append({
                "url":
                    url,
                "status":
                    "error",
                "error":
                    repr(exc),
            })


        if delay:
            time.sleep(
                delay
            )


    # --------------------------------------------------------
    # Manifest de provenance
    # --------------------------------------------------------

    dump_yaml(
        out_dir
        / "manifests"
        / "cli_reference.yaml",
        {
            "version":
                version,

            "seed":
                seed,

            "discovered":
                len(urls),

            "parsed":
                parsed_count,

            "failed":
                len(errors),

            "pages":
                manifest,
        }
    )


    stats = {

        "cli_reference_discovered":
            len(urls),

        "cli_reference_sections":
            parsed_count,

        "cli_reference_failed":
            len(errors),
    }


    return (
        stats,
        errors
    )


def crawl(seed: str, allowed_prefixes: list[str], max_pages: int, delay: float=0.15):
    q = [seed]
    seen = set()
    pages = []

    while q and (
        max_pages <= 0
        or len(seen) < max_pages
    ):

        url = q.pop(0)

        if url in seen:
            continue

        seen.add(url)

        limit = (
            "ALL"
            if max_pages <= 0
            else str(max_pages)
        )

        print(
            f"[DOCS] "
            f"{len(seen)}/{limit} "
            f"{url}",
            flush=True
        )

        try:
            html = fetch(url)

        except Exception as exc:

            print(
                f"[DOCS][ERROR] "
                f"{url} : {exc}",
                flush=True
            )

            pages.append(
                (
                    url,
                    None,
                    repr(exc)
                )
            )

            continue

        pages.append(
            (
                url,
                html,
                None
            )
        )

        for link in discover_links(
            html,
            url,
            allowed_prefixes
        ):

            if (
                link not in seen
                and link not in q
            ):
                q.append(link)

        if delay:
            time.sleep(delay)

    return pages

def build_docs(version: str, seeds: dict, out_dir: Path, max_pages=100):
    stats = {}; errors = []
    # --------------------------------------------------
    # CLI Reference
    #
    # Collection ciblée:
    # uniquement les pages "config ..."
    # --------------------------------------------------

    cli_stats, cli_errors = (
        build_cli_reference(
            version,
            seeds["cli_reference"],
            out_dir,
        )
    )

    stats.update(
        cli_stats
    )

    errors.extend(
        cli_errors
    )

    # Admin Guide
    admin_prefix = f"https://docs.fortinet.com/document/fortigate/{version}/administration-guide/"
    pages = crawl(seeds["administration_guide"], [admin_prefix], max_pages)
    topics = []
    for url, html, err in pages:
        if err: errors.append({"url":url,"error":err}); continue
        item = parse_admin_page(html, url, version)
        if item: topics.append(item)
    dump_yaml(out_dir/"features"/"admin_topics.yaml", {"version":version,"topics":topics})
    stats["admin_topics"] = len(topics)

    # Release notes
    rn_prefix = f"https://docs.fortinet.com/document/fortigate/{version}/fortios-release-notes/"
    pages = crawl(seeds["release_notes"], [rn_prefix], max_pages)
    notes = []
    for url, html, err in pages:
        if err: errors.append({"url":url,"error":err}); continue
        item = parse_release_page(html, url, version)
        if item: notes.append(item)
    dump_yaml(out_dir/"version"/"release_notes.yaml", {"version":version,"topics":notes})
    stats["release_note_topics"] = len(notes)

    # New features single page
    try:
        html = fetch(seeds["new_features"])
        item = parse_release_page(html, seeds["new_features"], version)
        dump_yaml(out_dir/"version"/"new_features.yaml", item or {"version":version})
        stats["new_features_page"] = 1
    except Exception as exc:
        errors.append({"url":seeds["new_features"],"error":repr(exc)}); stats["new_features_page"] = 0
    return stats, errors
