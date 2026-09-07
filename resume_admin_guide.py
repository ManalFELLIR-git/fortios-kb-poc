from __future__ import annotations

from pathlib import Path
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import random
import time

from kb_builder.utils import load_yaml, dump_yaml
from kb_builder.feature_sources import (
    fetch,
    page_title,
    page_text,
    extract_cli_sections,
    discover_topic_links,
)


parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
parser.add_argument("--workers", type=int, default=6)
args = parser.parse_args()

version = args.version

ROOT = (
    Path("knowledge_base")
    / "fortios"
    / version
)

AUDIT = (
    ROOT
    / "audit"
    / "feature_source_collection.yaml"
)

ADMIN_FILE = (
    ROOT
    / "raw"
    / "docs"
    / "features"
    / "admin_topics_full.yaml"
)

RETRY_REPORT = (
    ROOT
    / "audit"
    / "feature_source_retry.yaml"
)

ADMIN_PREFIX = (
    f"https://docs.fortinet.com/"
    f"document/fortigate/{version}/"
    f"administration-guide"
)


# ============================================================
# Charger ce qu'on possède déjà
# ============================================================

audit = load_yaml(AUDIT) or {}

errors = audit.get(
    "error_records",
    []
)

failed_admin = {
    item["url"]
    for item in errors
    if (
        item.get("kind")
        == "administration_guide"
        and item.get("url")
    )
}


admin_data = (
    load_yaml(ADMIN_FILE)
    if ADMIN_FILE.exists()
    else {}
) or {}

topics = admin_data.get(
    "topics",
    []
)

known_topics = {
    item.get("source_url"): item
    for item in topics
    if item.get("source_url")
}


print()
print("=== ADMIN GUIDE RESUME ===")
print("Déjà récupérés :", len(known_topics))
print("URLs à retenter :", len(failed_admin))
print("Workers         :", args.workers)
print()


# ============================================================
# Fetch avec retry
# ============================================================

def fetch_retry(url):

    last_error = None

    for attempt in range(1, 5):

        try:
            html = fetch(
                url,
                timeout=30,
            )

            return {
                "url": url,
                "html": html,
                "error": None,
                "attempts": attempt,
            }

        except Exception as exc:

            last_error = repr(exc)

            if attempt < 4:

                wait = (
                    1.5 * (2 ** (attempt - 1))
                    + random.uniform(0, 0.5)
                )

                time.sleep(wait)

    return {
        "url": url,
        "html": None,
        "error": last_error,
        "attempts": 4,
    }


# ============================================================
# Queue = seulement les échecs précédents
# ============================================================

queue = deque(
    sorted(failed_admin)
)

queued = set(queue)

processed = set()

remaining_errors = []

new_topics = 0

batch_number = 0


def checkpoint():

    merged = list(
        known_topics.values()
    )

    dump_yaml(
        ADMIN_FILE,
        {
            "version":
                version,

            "count":
                len(merged),

            "topics":
                merged,
        }
    )

    dump_yaml(
        RETRY_REPORT,
        {
            "version":
                version,

            "existing_topics":
                len(merged),

            "processed":
                len(processed),

            "queue_remaining":
                len(queue),

            "errors_current_batch":
                remaining_errors,
        }
    )


# ============================================================
# Reprise en petits batches parallèles
# ============================================================

while queue:

    batch = []

    while (
        queue
        and len(batch) < args.workers * 4
    ):

        url = queue.popleft()

        if (
            url in processed
            or url in known_topics
        ):
            continue

        batch.append(url)

    if not batch:
        continue

    batch_number += 1

    batch_errors = []

    with ThreadPoolExecutor(
        max_workers=args.workers
    ) as executor:

        futures = {
            executor.submit(
                fetch_retry,
                url,
            ): url
            for url in batch
        }

        for future in as_completed(
            futures
        ):

            result = future.result()

            url = result["url"]

            processed.add(url)

            if result["error"]:

                batch_errors.append({
                    "kind":
                        "administration_guide",

                    "url":
                        url,

                    "error":
                        result["error"],

                    "attempts":
                        result["attempts"],
                })

                continue


            html = result["html"]

            item = {
                "version":
                    version,

                "kind":
                    "administration_guide",

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

            if url not in known_topics:
                known_topics[url] = item
                new_topics += 1


            # Important :
            # une page récupérée peut révéler de nouveaux topics
            links = discover_topic_links(
                html,
                url,
                ADMIN_PREFIX,
            )

            for link in links:

                if (
                    link not in known_topics
                    and link not in processed
                    and link not in queued
                ):

                    queue.append(link)
                    queued.add(link)


    remaining_errors.extend(
        batch_errors
    )

    checkpoint()

    print(
        f"[RESUME] "
        f"topics={len(known_topics)} "
        f"nouveaux={new_topics} "
        f"processed={len(processed)} "
        f"queue={len(queue)} "
        f"batch_errors={len(batch_errors)}",
        flush=True
    )


# ============================================================
# Audit final de reprise
# ============================================================

# Ne garder que les erreurs dont l'URL n'a finalement
# pas été récupérée.
final_errors = [
    item
    for item in remaining_errors
    if item.get("url")
    not in known_topics
]

dump_yaml(
    RETRY_REPORT,
    {
        "version":
            version,

        "admin_topics_final":
            len(known_topics),

        "new_topics_recovered":
            new_topics,

        "remaining_errors":
            len(final_errors),

        "error_records":
            final_errors,
    }
)

checkpoint()

print()
print("=== RESUME TERMINÉ ===")
print("Admin topics final :", len(known_topics))
print("Nouveaux récupérés :", new_topics)
print("Erreurs restantes  :", len(final_errors))
print()
print("[REPORT]", RETRY_REPORT)
