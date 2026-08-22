"""The ``tokenmill`` command line.

Four commands:

* ``tokenmill convert`` — convert a source and report the token change.
* ``tokenmill repo`` — pack a repository into one file, with the repository
  options the plan's Phase 4 names: include and exclude globs, a token budget
  that genuinely truncates, and a per-directory breakdown.
* ``tokenmill backends`` — list backends with availability and licence.
* ``tokenmill tokens`` — count the tokens in a file or a string.

``repo`` exists as its own command rather than as flags on ``convert`` because a
Git URL means two different things depending on which the user typed:
``https://github.com/owner/project`` is a web page to ``convert`` and a
repository to clone to ``repo``. Both go through the same pipeline.

Two conventions run through all of them.

**Converted text goes to stdout; everything else goes to stderr.** So
``tokenmill convert page.html > page.md`` writes exactly the Markdown, and the
report is still visible in the terminal.

**No traceback ever reaches the user.** Every
:class:`~tokenmill.core.errors.TokenmillError` is caught and printed as a
message plus its hint. Anything else is a bug in tokenmill, and it says so and
tells the user where to report it.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from tokenmill import __version__
from tokenmill.cli.format import format_result_report, format_table
from tokenmill.core.config import load_config
from tokenmill.core.errors import TokenmillError
from tokenmill.core.models import (
    ConversionResult,
    Domain,
    ImageHandling,
    LinkHandling,
    OutputFormat,
    Source,
    SourceKind,
)
from tokenmill.core.pipeline import Pipeline
from tokenmill.core.registry import default_registry
from tokenmill.tokens.registry import default_tokenizer_registry

__all__ = ["app", "main"]

app = typer.Typer(
    name="tokenmill",
    help=(
        "Convert documents, web pages and repositories to token-efficient text, "
        "and measure exactly what that saved."
    ),
    # Not `no_args_is_help`: that exits 2, and a bare `tokenmill` asking what it
    # can do is not a usage error. The root callback prints help and exits 0.
    add_completion=False,
)

#: Exit code for a failure tokenmill anticipated and can explain.
EXIT_ERROR = 1

#: Exit code for a bug: an exception outside the error taxonomy.
EXIT_BUG = 70


def _fail(message: str, hint: str | None = None) -> NoReturn:
    """Print an error to stderr and exit.

    Args:
        message: What went wrong.
        hint: An actionable next step, printed on its own line.

    Raises:
        SystemExit: Always, with :data:`EXIT_ERROR`.
    """
    print(f"error: {message}", file=sys.stderr)
    if hint:
        print(f"hint:  {hint}", file=sys.stderr)
    raise typer.Exit(EXIT_ERROR)


def _configure_logging(verbose: bool) -> None:
    """Send library logging to stderr at the requested level.

    Args:
        verbose: Enable debug logging.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _make_source(target: str) -> Source:
    """Turn a command-line argument into a source.

    Args:
        target: A URL, or a path to a file or directory.

    Returns:
        The source.
    """
    if target.startswith(("http://", "https://")):
        return Source.from_url(target)
    try:
        return Source.from_path(target)
    except FileNotFoundError as exc:
        _fail(str(exc), hint="pass a path that exists, or an http(s) URL")


def _result_to_json(result: ConversionResult, *, include_text: bool) -> dict[str, Any]:
    """Render a conversion result as JSON-serialisable data.

    Token counts are ``null`` rather than absent when nothing could be measured,
    so a consumer can tell "not measured" from "measured as zero". A binary
    document reports ``tokens_before: null`` and a ``source_bytes`` figure: it
    has no comparable before-count, only a file size.

    Args:
        result: The conversion to render.
        include_text: Embed the converted text in the payload.

    Returns:
        The JSON-ready mapping.
    """
    payload: dict[str, Any] = {
        "source": result.source_name,
        "backend": result.backend_id,
        "format": result.output_format.value,
        "duration_s": round(result.duration_s, 6),
        "tokenizer": (result.tokens_after.tokenizer_id if result.tokens_after else None),
        "source_bytes": result.source_bytes,
        "tokens_before": result.tokens_before.value if result.tokens_before else None,
        "tokens_after": result.tokens_after.value if result.tokens_after else None,
        "token_delta": result.token_delta,
        "reduction_ratio": result.reduction_ratio,
        "post_processors": list(result.post_processors),
        "web": _web_summary(result),
        "attempts": [
            {"backend": attempt.backend_id, "ok": attempt.ok, "error": attempt.error}
            for attempt in result.attempts
        ],
        "warnings": list(result.warnings),
        "metadata": dict(result.metadata),
        "stages": [
            {
                "stage": stage.stage,
                "characters": stage.characters,
                "tokens": stage.tokens.value if stage.tokens else None,
            }
            for stage in result.stages
        ],
    }
    if include_text:
        payload["text"] = result.text
    return payload


#: Metadata keys a web backend records, surfaced as their own object in
#: ``--json`` so a consumer does not have to know they live in ``metadata``.
_WEB_KEYS = (
    "strips_boilerplate",
    "html_characters",
    "visible_text_characters",
    "output_characters",
    "boilerplate_reduction",
)


def _web_summary(result: ConversionResult) -> dict[str, Any] | None:
    """Render the web-specific measurements, or ``None`` for a non-web result.

    Args:
        result: The conversion to describe.

    Returns:
        The web metrics, or ``None`` when the backend recorded none — which is
        every document and repository conversion.
    """
    if "strips_boilerplate" not in result.metadata:
        return None
    return {key: result.metadata.get(key) for key in _WEB_KEYS}


@app.command()
def convert(
    target: Annotated[str, typer.Argument(help="File, directory or http(s) URL to convert.")],
    backend: Annotated[
        str | None, typer.Option("--backend", "-b", help="Force a specific backend id.")
    ] = None,
    tokenizer: Annotated[
        str | None,
        typer.Option("--tokenizer", "-t", help="Tokenizer to measure with, e.g. o200k_base."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write the converted text here instead of stdout."),
    ] = None,
    output_format: Annotated[
        OutputFormat | None, typer.Option("--format", "-f", help="Output format.")
    ] = None,
    post: Annotated[
        str | None,
        typer.Option(
            "--post",
            help="Comma-separated post-processor chain, run in the order given. "
            "Defaults to the non-destructive chain.",
        ),
    ] = None,
    images: Annotated[
        ImageHandling | None,
        typer.Option("--images", help="Keep images, reduce them to alt text, or strip them."),
    ] = None,
    links: Annotated[
        LinkHandling | None, typer.Option("--links", help="Keep or strip Markdown links.")
    ] = None,
    fallback: Annotated[
        bool | None,
        typer.Option(
            "--fallback/--no-fallback",
            help="On auto-selection, try the next backend when the preferred one fails. "
            "Never applies to an explicit --backend.",
        ),
    ] = None,
    offline: Annotated[
        bool,
        typer.Option(
            "--offline",
            help="Refuse to retrieve a URL. Converting a local file never reaches "
            "the network with or without this.",
        ),
    ] = False,
    ignore_robots: Annotated[
        bool,
        typer.Option(
            "--ignore-robots",
            help="Fetch a URL even when the site's robots.txt disallows it. "
            "Yours to decide for a site you control.",
        ),
    ] = False,
    allow_network: Annotated[
        bool,
        typer.Option(
            "--allow-network",
            help="Permit backends to make network calls of their own, such as "
            "downloading a model or driving a browser.",
        ),
    ] = False,
    user_agent: Annotated[
        str | None,
        typer.Option("--user-agent", help="Identify as this instead of tokenmill's default."),
    ] = None,
    max_redirects: Annotated[
        int | None, typer.Option("--max-redirects", help="Redirects a URL fetch may follow.")
    ] = None,
    show_stages: Annotated[
        bool, typer.Option("--show-stages", help="Show the per-stage token breakdown.")
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit the result as JSON on stdout.")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Suppress the report on stderr.")
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")] = False,
) -> None:
    """Convert a source to token-efficient text and report what that saved."""
    _configure_logging(verbose)
    source = _make_source(target)

    try:
        config = load_config()
    except TokenmillError as exc:
        _fail(exc.message, exc.hint)

    chain = tuple(part.strip() for part in post.split(",") if part.strip()) if post else None
    options = config.to_options(
        backend=backend,
        tokenizer=tokenizer,
        output_format=output_format,
        post_processors=chain,
        image_handling=images,
        link_handling=links,
        fallback=fallback,
        user_agent=user_agent,
        max_redirects=max_redirects,
        # These three are flags rather than tri-state options, so `False` means
        # "not passed" and must not clobber a configured value — the same rule
        # `to_options` applies to everything else it is handed.
        fetch=False if offline else None,
        respect_robots=False if ignore_robots else None,
        allow_network=True if allow_network else None,
    )
    # Asking for image or link handling without naming a chain implies wanting
    # the `links` post-processor; it is destructive, so it is not in the default
    # chain, and silently ignoring the flag would be worse than either option.
    if chain is None and (
        options.image_handling is not ImageHandling.KEEP
        or options.link_handling is not LinkHandling.KEEP
    ):
        registry = Pipeline().post_processors
        implied = (*[p.id for p in registry.default_chain()], "links")
        options = options.with_(post_processors=implied)

    try:
        result = Pipeline().run(source, options)
    except TokenmillError as exc:
        _fail(exc.message, exc.hint)
    except KeyError as exc:
        _fail(str(exc).strip("\"'"))

    if as_json:
        print(json.dumps(_result_to_json(result, include_text=output is None), indent=2))
    elif output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.text, encoding="utf-8")
        print(f"wrote {output}", file=sys.stderr)
    else:
        print(result.text, end="" if result.text.endswith("\n") else "\n")

    if not quiet and not as_json:
        print(format_result_report(result, show_stages=show_stages), file=sys.stderr)


@app.command()
def repo(
    target: Annotated[
        str, typer.Argument(help="Repository directory, or a Git URL to clone shallowly.")
    ],
    backend: Annotated[
        str | None, typer.Option("--backend", "-b", help="Force a specific backend id.")
    ] = None,
    tokenizer: Annotated[
        str | None, typer.Option("--tokenizer", "-t", help="Tokenizer to measure with.")
    ] = None,
    include: Annotated[
        str | None,
        typer.Option("--include", help="Comma-separated globs; only matching files are packed."),
    ] = None,
    exclude: Annotated[
        str | None, typer.Option("--exclude", help="Comma-separated globs to leave out.")
    ] = None,
    token_budget: Annotated[
        int | None,
        typer.Option(
            "--token-budget",
            help="Cap the pack at this many tokens, counted in the run's tokenizer. "
            "Whole files are dropped from the end and every one is reported.",
        ),
    ] = None,
    tree_tokens: Annotated[
        bool,
        typer.Option("--tree-tokens", help="Append a per-directory token breakdown."),
    ] = False,
    max_file_size: Annotated[
        int | None, typer.Option("--max-file-size", help="Skip files larger than this many bytes.")
    ] = None,
    gitignore: Annotated[
        bool,
        typer.Option("--gitignore/--no-gitignore", help="Respect .gitignore rules."),
    ] = True,
    branch: Annotated[
        str | None, typer.Option("--branch", help="Branch, tag or commit to clone.")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write the pack here instead of stdout.")
    ] = None,
    allow_network: Annotated[
        bool,
        typer.Option(
            "--allow-network",
            help="Permit a backend to fetch its own runtime, such as npx downloading repomix.",
        ),
    ] = False,
    show_stages: Annotated[
        bool, typer.Option("--show-stages", help="Show the per-stage token breakdown.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit the result as JSON on stdout.")] = (
        False
    ),
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Suppress the report.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")] = False,
) -> None:
    """Pack a repository into one prompt-ready file, with token accounting."""
    _configure_logging(verbose)

    try:
        config = load_config()
    except TokenmillError as exc:
        _fail(exc.message, exc.hint)

    source = _repo_source(target)
    extra: dict[str, Any] = {
        "include": include,
        "exclude": exclude,
        "token_budget": token_budget,
        "tree_tokens": tree_tokens,
        "max_file_bytes": max_file_size,
        "respect_gitignore": gitignore,
        "branch": branch,
    }
    options = config.to_options(
        backend=backend,
        tokenizer=tokenizer,
        allow_network=True if allow_network else None,
    ).with_(extra={k: v for k, v in extra.items() if v is not None})

    try:
        result = Pipeline().run(source, options)
    except TokenmillError as exc:
        _fail(exc.message, exc.hint)

    if as_json:
        print(json.dumps(_result_to_json(result, include_text=output is None), indent=2))
    elif output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.text, encoding="utf-8")
        print(f"wrote {output}", file=sys.stderr)
    else:
        print(result.text, end="" if result.text.endswith("\n") else "\n")

    if not quiet and not as_json:
        print(format_result_report(result, show_stages=show_stages), file=sys.stderr)


def _repo_source(target: str) -> Source:
    """Turn a ``tokenmill repo`` argument into a repository source.

    A Git URL is *not* fetched as a web page here, which is the whole reason
    this command builds its own source rather than reusing
    :func:`_make_source`: ``https://github.com/owner/project`` is an HTML page
    to ``convert`` and a repository to clone to ``repo``, and only the command
    the user typed can tell those apart.

    Args:
        target: A directory path, or a Git URL.

    Returns:
        The source.
    """
    if target.startswith(("http://", "https://", "git://", "ssh://")):
        try:
            return Source.from_git(target)
        except ValueError as exc:
            _fail(str(exc))
    try:
        source = Source.from_path(target)
    except FileNotFoundError as exc:
        _fail(str(exc), hint="pass a directory that exists, or a Git URL")
    if source.kind is not SourceKind.REPO:
        _fail(
            f"{target} is a file, not a repository",
            hint="pass the directory that contains it, or use `tokenmill convert` for one file",
        )
    return source


@app.command()
def backends(
    show_all: Annotated[
        bool,
        typer.Option("--all", "-a", help="Include backends that cannot currently run."),
    ] = False,
    domain: Annotated[
        Domain | None, typer.Option("--domain", "-d", help="Only backends serving this domain.")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON on stdout.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")] = False,
) -> None:
    """List the installed backends with their licence and availability."""
    _configure_logging(verbose)
    registry = default_registry()

    rows: list[list[str]] = []
    payload: list[dict[str, Any]] = []
    for converter in registry:
        info = converter.info
        if domain is not None and domain not in info.domains:
            continue
        availability = converter.is_available()
        if not availability and not show_all:
            continue
        rows.append(
            [
                info.id,
                ",".join(d.value for d in info.domains),
                info.license,
                info.license_tier.value,
                info.isolation.value,
                availability.describe(),
            ]
        )
        payload.append(
            {
                "id": info.id,
                "name": info.name,
                "description": info.description,
                "domains": [d.value for d in info.domains],
                "input_formats": list(info.input_formats),
                "output_formats": [f.value for f in info.output_formats],
                "license": info.license,
                "license_tier": info.license_tier.value,
                "isolation": info.isolation.value,
                "install_extra": info.install_extra,
                "requires_gpu": info.requires_gpu,
                "requires_network": info.requires_network,
                "requires_binary": info.requires_binary,
                "upstream_url": info.upstream_url,
                "available": availability.is_available,
                "availability": availability.describe(),
                "hint": availability.hint,
            }
        )

    # A plugin that failed to load is shown as a backend that cannot run, not
    # hidden. Hiding it would leave the user unable to work out why the backend
    # they installed never appeared.
    for broken in registry.broken:
        if not show_all:
            continue
        rows.append([broken.id, "?", "?", "?", "?", f"failed to load: {broken.error}"])
        payload.append(
            {
                "id": broken.id,
                "available": False,
                "availability": f"failed to load: {broken.error}",
                "hint": broken.availability.hint,
                "entry_point": broken.source,
            }
        )

    if as_json:
        print(json.dumps(payload, indent=2))
        return

    if not rows:
        print("no backends matched", file=sys.stderr)
        if not show_all:
            print("hint:  pass --all to include unavailable backends", file=sys.stderr)
        return

    print(format_table(["id", "domains", "license", "tier", "isolation", "availability"], rows))


@app.command()
def tokens(
    target: Annotated[
        str | None,
        typer.Argument(help="File or http(s) URL to count. Omit when using --text."),
    ] = None,
    text: Annotated[
        str | None, typer.Option("--text", help="Count this literal string instead of a file.")
    ] = None,
    tokenizer: Annotated[
        str | None, typer.Option("--tokenizer", "-t", help="Tokenizer to count with.")
    ] = None,
    list_tokenizers: Annotated[
        bool, typer.Option("--list", help="List the tokenizers available and exit.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON on stdout.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")] = False,
) -> None:
    """Count the tokens in a file or a string, without converting it."""
    _configure_logging(verbose)
    registry = default_tokenizer_registry()

    if list_tokenizers:
        _list_tokenizers(registry, as_json=as_json)
        return

    if (target is None) == (text is None):
        _fail("give exactly one of a path/URL argument or --text")

    try:
        config = load_config()
    except TokenmillError as exc:
        _fail(exc.message, exc.hint)
    tokenizer_id = tokenizer or config.tokenizer

    if text is not None:
        content = text
        name = "<text>"
    else:
        source = _make_source(str(target))
        try:
            content = source.read_text()
        except ValueError as exc:
            _fail(str(exc), hint="tokens counts files and strings, not directories or URLs")
        name = source.name

    try:
        counter = registry.get(tokenizer_id)
        count = counter.count(content)
    except TokenmillError as exc:
        _fail(exc.message, exc.hint)

    info = counter.info
    if as_json:
        print(
            json.dumps(
                {
                    "source": name,
                    "tokenizer": info.id,
                    "counts": info.counts,
                    "is_model_tokenizer": info.is_model_tokenizer,
                    "characters": len(content),
                    "tokens": count,
                },
                indent=2,
            )
        )
        return

    print(
        format_table(
            ["source", "characters", info.counts, "tokenizer"],
            [[name, f"{len(content):,}", f"{count:,}", info.id]],
        )
    )
    if not info.is_model_tokenizer:
        print(
            f"note:  {info.id!r} counts {info.counts}, not model tokens; "
            f"do not quote this as a token count",
            file=sys.stderr,
        )


def _list_tokenizers(registry: Any, *, as_json: bool) -> None:
    """Print the tokenizers this installation can resolve.

    Args:
        registry: The tokenizer registry to list.
        as_json: Emit JSON instead of a table.
    """
    rows: list[list[str]] = []
    payload: list[dict[str, Any]] = []
    for provider in registry.providers():
        available = provider.available() if hasattr(provider, "available") else True
        names = provider.aliases() or (f"{provider.id}:<spec>",)
        for name in names:
            rows.append([name, provider.id, "yes" if available else "not installed"])
            payload.append({"id": name, "provider": provider.id, "available": bool(available)})
    if as_json:
        print(json.dumps(payload, indent=2))
        return
    print(format_table(["id", "provider", "installed"], rows))


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="Show the version and exit.")] = False,
) -> None:
    """Handle options that apply to every command.

    Args:
        ctx: The click context, used to tell "no command given" from "a command
            is about to run".
        version: Print the version and exit.
    """
    if version:
        print(f"tokenmill {__version__}")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
        raise typer.Exit(0)


def main() -> None:
    """Run the CLI, turning any unexpected exception into a bug report.

    Raises:
        SystemExit: Always, with the command's exit code.
    """
    try:
        app()
    except TokenmillError as exc:  # pragma: no cover - commands catch their own
        print(f"error: {exc.message}", file=sys.stderr)
        if exc.hint:
            print(f"hint:  {exc.hint}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
    except Exception as exc:  # pragma: no cover - only reachable via a bug
        print(f"internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "hint:  this is a bug in tokenmill; please report it at "
            "https://github.com/RSD-Studio/tokenmill/issues",
            file=sys.stderr,
        )
        sys.exit(EXIT_BUG)


if __name__ == "__main__":  # pragma: no cover
    main()
