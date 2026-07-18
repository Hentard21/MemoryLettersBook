#!/usr/bin/env python3
"""Build the project Graphify graph locally, without an LLM semantic pass.

Graphify's deterministic extractors cover source code, Markdown, and JSON.
This adapter adds file/reference nodes for project CSV, HTML, CSS, and text
files so the book manifests and prototype sources remain discoverable while
heavy media stay excluded by .graphifyignore.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.detect import _is_ignored, _load_graphifyignore, detect, save_manifest
from graphify.export import to_json
from graphify.extract import collect_files, extract
from graphify.report import generate


TEXT_EXTENSIONS = {
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".txt",
}
INCLUDE_ROOTS = ("assets", "config", "content", "design", "docs", "scripts")
ROOT_FILES = {"README.md"}
MAX_TEXT_BYTES = 2_000_000

HERO_RE = re.compile(r"\bhero-\d{3}\b", re.IGNORECASE)
PATH_RE = re.compile(
    r"(?:(?:assets|config|content|design|docs|scripts|source|workspace)[/\\])"
    r"[\w.()@+\- /\\*]+(?:\.[A-Za-z0-9_-]+)?"
)
TOPIC_PATTERNS = {
    "full_manifest": re.compile(r"полный\s+манифест|full\s+manifest", re.IGNORECASE),
    "family_order": re.compile(r"порядок\s+семей|последовательност[ьи]\s+семей", re.IGNORECASE),
    "maps": re.compile(r"\bmap\b|карт[аы]|region_code|map_feature_id", re.IGNORECASE),
    "emblems": re.compile(r"\bemblem\b|герб[а-я]*", re.IGNORECASE),
    "flagship_portrait": re.compile(r"flagship|флагманск[а-я]+\s+(?:фото|портрет)", re.IGNORECASE),
    "reference_pdf": re.compile(r"reference\.pdf|исходн[а-я]+\s+pdf|контрольн[а-я]+\s+pdf", re.IGNORECASE),
    "manifest": re.compile(r"manifest|манифест", re.IGNORECASE),
}


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:14]
    return f"{prefix}_{digest}"


def relative_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def iter_project_text_files(root: Path) -> list[Path]:
    patterns = _load_graphifyignore(root)
    ignore_cache: dict[Path, bool] = {}
    candidates: list[Path] = []

    for name in INCLUDE_ROOTS:
        base = root / name
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            if path.stat().st_size > MAX_TEXT_BYTES:
                continue
            if _is_ignored(path, root, patterns, _cache=ignore_cache):
                continue
            candidates.append(path)

    for name in ROOT_FILES:
        path = root / name
        if path.is_file() and path.stat().st_size <= MAX_TEXT_BYTES:
            candidates.append(path)

    return sorted(set(candidates))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def add_unique_node(nodes: list[dict], node_ids: set[str], node: dict) -> None:
    if node["id"] in node_ids:
        return
    nodes.append(node)
    node_ids.add(node["id"])


def add_unique_edge(edges: list[dict], edge_keys: set[tuple], edge: dict) -> None:
    edge.setdefault("source_file", "")
    edge.setdefault("source_location", "")
    key = (edge["source"], edge["target"], edge["relation"], edge.get("context", ""))
    if key in edge_keys:
        return
    edges.append(edge)
    edge_keys.add(key)


def custom_file_layer(root: Path, files: list[Path], base: dict) -> dict:
    nodes = list(base.get("nodes", []))
    edges = list(base.get("edges", []))
    node_ids = {node["id"] for node in nodes}
    edge_keys = {
        (edge.get("source"), edge.get("target"), edge.get("relation"), edge.get("context", ""))
        for edge in edges
    }

    file_ids: dict[str, str] = {}
    texts: dict[str, str] = {}
    for path in files:
        rel = relative_posix(path, root)
        file_id = stable_id("project_file", rel.lower())
        file_ids[rel.lower()] = file_id
        text = read_text(path)
        texts[rel] = text
        add_unique_node(
            nodes,
            node_ids,
            {
                "id": file_id,
                "label": rel,
                "type": "project_file",
                "source_file": rel,
                "source_location": rel,
                "confidence": "EXTRACTED",
            },
        )

    for rel, text in texts.items():
        source_id = file_ids[rel.lower()]

        for hero in sorted({match.lower() for match in HERO_RE.findall(text)}):
            hero_id = f"entity_{hero.replace('-', '_')}"
            add_unique_node(
                nodes,
                node_ids,
                {
                    "id": hero_id,
                    "label": hero,
                    "type": "hero_id",
                    "source_file": "",
                    "source_location": "",
                    "confidence": "EXTRACTED",
                },
            )
            add_unique_edge(
                edges,
                edge_keys,
                {
                    "source": source_id,
                    "target": hero_id,
                    "relation": "references",
                    "confidence": "EXTRACTED",
                    "context": "hero_id",
                },
            )

        for topic, pattern in TOPIC_PATTERNS.items():
            if not pattern.search(text):
                continue
            topic_id = f"topic_{topic}"
            add_unique_node(
                nodes,
                node_ids,
                {
                    "id": topic_id,
                    "label": topic.replace("_", " "),
                    "type": "project_topic",
                    "source_file": "",
                    "source_location": "",
                    "confidence": "EXTRACTED",
                },
            )
            add_unique_edge(
                edges,
                edge_keys,
                {
                    "source": source_id,
                    "target": topic_id,
                    "relation": "documents",
                    "confidence": "EXTRACTED",
                    "context": topic,
                },
            )

        for raw_match in PATH_RE.findall(text):
            normalized = raw_match.strip("`'\".,;:()[]{} ").replace("\\", "/")
            normalized = re.sub(r"\s+", " ", normalized)
            target_id = file_ids.get(normalized.lower())
            if not target_id or target_id == source_id:
                continue
            add_unique_edge(
                edges,
                edge_keys,
                {
                    "source": source_id,
                    "target": target_id,
                    "relation": "references_file",
                    "confidence": "EXTRACTED",
                    "context": normalized,
                },
            )

        if rel.lower().endswith(".csv"):
            try:
                rows = list(csv.DictReader(text.splitlines()))
            except csv.Error:
                rows = []
            # Large page-level CSVs are already connected through their hero IDs.
            # Row nodes are useful only for compact operational manifests.
            if len(rows) > 100:
                continue
            for index, row in enumerate(rows, start=1):
                row_key = next(
                    (row.get(key) for key in ("hero_id", "asset_id", "family_id", "page_id", "id") if row.get(key)),
                    f"row-{index}",
                )
                row_id = stable_id("csv_row", f"{rel}:{row_key}:{index}")
                add_unique_node(
                    nodes,
                    node_ids,
                    {
                        "id": row_id,
                        "label": str(row_key),
                        "type": "manifest_row",
                        "source_file": rel,
                        "source_location": f"{rel}:{index + 1}",
                        "confidence": "EXTRACTED",
                    },
                )
                add_unique_edge(
                    edges,
                    edge_keys,
                    {
                        "source": source_id,
                        "target": row_id,
                        "relation": "contains",
                        "confidence": "EXTRACTED",
                        "context": "csv_row",
                    },
                )

    return {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": base.get("hyperedges", []),
        "input_tokens": 0,
        "output_tokens": 0,
    }


def build(root: Path) -> None:
    root = root.resolve()
    out = root / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)

    detection = detect(root, cache_root=root)
    supported_files = collect_files(root, root=root)
    structural = extract(supported_files, cache_root=root)
    project_files = iter_project_text_files(root)
    extraction = custom_file_layer(root, project_files, structural)

    graph = build_from_json(extraction, root=str(root), directed=False)
    if graph.number_of_nodes() == 0:
        raise RuntimeError("Graphify extraction produced an empty graph")

    communities = cluster(graph)
    cohesion = score_all(graph, communities)
    labels = {community_id: f"Community {community_id}" for community_id in communities}
    gods = god_nodes(graph)
    surprises = surprising_connections(graph, communities)
    questions = suggest_questions(graph, communities, labels)

    wrote = to_json(graph, communities, out / "graph.json")
    if not wrote:
        raise RuntimeError("Graphify refused to replace graph.json with a smaller graph")

    report = generate(
        graph,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection,
        {"input": 0, "output": 0},
        str(root),
        suggested_questions=questions,
    )
    (out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    (out / ".graphify_labels.json").write_text(
        json.dumps({str(key): value for key, value in labels.items()}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out / ".graphify_root").write_text(str(root), encoding="utf-8")
    (out / ".graphify_python").write_text(sys.executable, encoding="utf-8")
    save_manifest(detection.get("all_files") or detection.get("files", {}), root=root)

    print(
        json.dumps(
            {
                "root": str(root),
                "text_files": len(project_files),
                "structural_files": len(supported_files),
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                "communities": len(communities),
                "semantic_backend": None,
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=".", type=Path)
    args = parser.parse_args()
    build(args.path)


if __name__ == "__main__":
    main()
