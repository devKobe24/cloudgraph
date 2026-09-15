"""CLI dispatch. Subcommands land here as their phases are implemented."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from . import __version__, report
from .analyze import analyze
from .build import build
from .estimate import estimate
from .export import to_html, to_json_payload
from .load import DesignError, load_design, load_graph
from .paths import resolve_out_dir, write_json_atomic, write_text_atomic
from .pricing import CatalogError, load_catalog
from .query import (
    format_money,
    render_explain,
    render_path,
    render_search,
    render_stats,
    resolve,
)
from .schema import Architecture, ArchitectureMetadata
from .validate import validate_design

# name -> help text, in the order they appear in --help.
SUBCOMMANDS = {
    "init": "create a new .awsgraph.json design file",
    "design": "open the standalone designer in a browser",
    "validate": "validate a design file",
    "build": "build graph.json, graph.html and AWS_REPORT.md",
    "estimate": "print the monthly cost estimate",
    "stats": "print graph statistics",
    "query": "search the graph",
    "path": "show the path between two resources",
    "explain": "show one resource in detail",
    "affected": "show resources affected by a change",
    "export": "export the graph in another format",
}


def _graph_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", default=None, help="output directory (default: ./awsgraph-out)")


def _init_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="path of the design file to create")
    parser.add_argument("--name", default="My AWS Architecture", help="architecture name")
    parser.add_argument(
        "--force", action="store_true", help="overwrite the file if it already exists"
    )


def _validate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="path of the design file to validate")


def _build_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="path of the design file to build")
    parser.add_argument("--out", default=None, help="output directory (default: ./awsgraph-out)")
    parser.add_argument("--open", action="store_true", help="open graph.html when done")


def _estimate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", default=None, help="output directory (default: ./awsgraph-out)")
    parser.add_argument("--json", action="store_true", help="print machine-readable output")


def _query_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("text", help="search text")
    _graph_args(parser)
    parser.add_argument("--limit", type=int, default=10, help="maximum matches")


def _explain_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("resource", help="resource id, name or type")
    _graph_args(parser)


def _path_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="start resource")
    parser.add_argument("target", help="end resource")
    _graph_args(parser)


ARG_ADDERS: dict[str, Callable[[argparse.ArgumentParser], None]] = {
    "init": _init_args,
    "validate": _validate_args,
    "build": _build_args,
    "estimate": _estimate_args,
    "stats": _graph_args,
    "query": _query_args,
    "explain": _explain_args,
    "path": _path_args,
}


def _print_errors(source: str, messages: list[str]) -> int:
    print(f"Error: {source} is invalid", file=sys.stderr)
    for message in messages:
        print(f"  {message}", file=sys.stderr)
    return 1


def _open_graph(args: argparse.Namespace):
    """Load awsgraph-out/graph.json, or print why it could not be read."""
    try:
        return load_graph(resolve_out_dir(args.out, create=False) / "graph.json")
    except DesignError as exc:
        for message in exc.messages:
            print(f"Error: {message}", file=sys.stderr)
        return None


def _resolve_one(graph, term: str) -> str | None:
    """Resolve a user term to exactly one node, or explain why it could not."""
    resolution = resolve(graph, term)
    if not resolution.ids:
        print(f'Error: no resource matches "{term}".', file=sys.stderr)
        return None
    if not resolution.is_unique:
        print(f'Error: "{term}" matches more than one resource:', file=sys.stderr)
        for node_id in resolution.ids:
            attrs = graph.nodes[node_id]
            print(
                f"  - {attrs['label']} [{attrs['resource_type']}] ({node_id})",
                file=sys.stderr,
            )
        print("Use the resource id to pick one.", file=sys.stderr)
        return None
    node_id = resolution.ids[0]
    if resolution.how.startswith("fuzzy"):
        print(
            f'Matched "{term}" to {graph.nodes[node_id]["label"]} by {resolution.how}.',
            file=sys.stderr,
        )
    return node_id


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if path.exists() and not args.force:
        print(f"Error: {path} already exists. Use --force to overwrite.", file=sys.stderr)
        return 1
    architecture = Architecture(metadata=ArchitectureMetadata(name=args.name))
    path.write_text(architecture.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Created {path}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        architecture = load_design(args.file)
    except DesignError as exc:
        return _print_errors(args.file, exc.messages)

    errors = validate_design(architecture)
    if errors:
        return _print_errors(args.file, errors)

    print(
        f"{args.file}: OK "
        f"({len(architecture.resources)} resources, "
        f"{len(architecture.relationships)} relationships)"
    )
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    try:
        architecture = load_design(args.file)
    except DesignError as exc:
        return _print_errors(args.file, exc.messages)

    errors = validate_design(architecture)
    if errors:
        return _print_errors(args.file, errors)

    try:
        catalog = load_catalog(
            architecture.pricing_context.region, architecture.pricing_context.catalog_id
        )
    except CatalogError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    graph = build(architecture)
    summary = estimate(graph, catalog)
    analysis = analyze(graph)

    # Render everything before touching disk so a failure leaves the previous
    # build intact (guide section 24.1).
    payload = to_json_payload(graph)
    html_text = to_html(graph)
    report_text = report.generate(graph, analysis, source=args.file)

    out_dir = resolve_out_dir(args.out)
    write_json_atomic(out_dir / "graph.json", payload)
    write_text_atomic(out_dir / "graph.html", html_text)
    write_text_atomic(out_dir / "AWS_REPORT.md", report_text)

    for node_id in summary["unpriced_resource_ids"]:
        attrs = graph.nodes[node_id]
        print(f"Warning: {attrs['label']} could not be priced.", file=sys.stderr)
        for missing in attrs.get("cost_missing", []):
            print(f"  {missing}", file=sys.stderr)

    print(f"Wrote {out_dir}/graph.json")
    print(f"Wrote {out_dir}/graph.html")
    print(f"Wrote {out_dir}/AWS_REPORT.md")
    print(
        f"Estimated monthly cost: "
        f"{format_money(summary['monthly_cost'], summary['currency'])} ({summary['status']})"
    )

    if args.open:
        import webbrowser

        webbrowser.open((out_dir / "graph.html").as_uri())
    return 0


def cmd_estimate(args: argparse.Namespace) -> int:
    graph_path = resolve_out_dir(args.out, create=False) / "graph.json"
    try:
        graph = load_graph(graph_path)
    except DesignError as exc:
        for message in exc.messages:
            print(f"Error: {message}", file=sys.stderr)
        return 1

    analysis = analyze(graph)
    if args.json:
        print(json.dumps(analysis, ensure_ascii=False, indent=2))
        return 0

    summary = analysis["summary"]
    currency = summary["currency"]
    print("Estimated Monthly Cost")
    print(format_money(summary["monthly_cost"], currency))
    print()
    width = max((len(s) for s in analysis["cost_by_service"]), default=0)
    for service, amount in analysis["cost_by_service"].items():
        print(f"{service:<{width}}  {format_money(amount, currency)}")
    if summary["unpriced_count"]:
        print()
        print(f"{summary['unpriced_count']} resource(s) could not be priced.", file=sys.stderr)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    graph = _open_graph(args)
    if graph is None:
        return 1
    print(render_stats(graph))
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    graph = _open_graph(args)
    if graph is None:
        return 1
    rendered = render_search(graph, args.text, args.limit)
    print(rendered)
    return 0 if rendered.startswith("Matches:") else 1


def cmd_explain(args: argparse.Namespace) -> int:
    graph = _open_graph(args)
    if graph is None:
        return 1
    node_id = _resolve_one(graph, args.resource)
    if node_id is None:
        return 1
    print(render_explain(graph, node_id))
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    graph = _open_graph(args)
    if graph is None:
        return 1
    source = _resolve_one(graph, args.source)
    target = _resolve_one(graph, args.target)
    if source is None or target is None:
        return 1
    rendered = render_path(graph, source, target)
    if rendered is None:
        print(
            f"No path from {graph.nodes[source]['label']} to {graph.nodes[target]['label']}.",
            file=sys.stderr,
        )
        return 1
    print(rendered)
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "init": cmd_init,
    "validate": cmd_validate,
    "build": cmd_build,
    "estimate": cmd_estimate,
    "stats": cmd_stats,
    "query": cmd_query,
    "explain": cmd_explain,
    "path": cmd_path,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="awsgraph",
        description="Local-first AWS architecture graph and cost estimator.",
    )
    parser.add_argument("--version", action="version", version=f"awsgraph {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, help_text in SUBCOMMANDS.items():
        command_parser = sub.add_parser(name, help=help_text)
        add_args = ARG_ADDERS.get(name)
        if add_args is not None:
            add_args(command_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    handler = COMMANDS.get(args.command)
    if handler is None:
        print(f"awsgraph {args.command}: not implemented yet", file=sys.stderr)
        return 2
    return handler(args)
