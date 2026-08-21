"""Layered configuration.

Settings come from four places, each overriding the one before it::

    built-in defaults  →  config file  →  environment  →  CLI flags

That order is the least surprising one: a project's config file beats the
defaults, a shell environment beats the file (so CI can override without editing
anything), and an explicit flag beats everything, because someone who typed it
meant it.

The config file is TOML, read with the standard library's :mod:`tomllib`. It is
looked for at, in order of preference:

1. the path in ``TOKENMILL_CONFIG``;
2. ``tokenmill.toml`` or ``.tokenmill.toml`` in the working directory;
3. ``$XDG_CONFIG_HOME/tokenmill/config.toml``, defaulting to
   ``~/.config/tokenmill/config.toml``.

Only the first file found is read. Configuration files do not merge across
locations — a partially-applied config is far harder to debug than a
wholly-applied one.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Final

from tokenmill.core.errors import ConfigError
from tokenmill.core.models import ConvertOptions, ImageHandling, LinkHandling, OutputFormat

__all__ = ["Config", "find_config_file", "load_config"]

#: Environment variable naming an explicit config file.
CONFIG_PATH_ENV: Final = "TOKENMILL_CONFIG"

#: Prefix for per-setting environment overrides, e.g. ``TOKENMILL_TOKENIZER``.
ENV_PREFIX: Final = "TOKENMILL_"

#: Config file names looked for in the working directory.
PROJECT_FILENAMES: Final = ("tokenmill.toml", ".tokenmill.toml")


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved settings for a tokenmill run.

    Attributes:
        tokenizer: Default tokenizer id.
        backend: Default backend id, or ``None`` to auto-select.
        output_format: Default output format.
        post_processors: Default post-processor chain, or ``None`` for the
            registry's non-destructive default.
        image_handling: Default image handling.
        link_handling: Default link handling.
        allow_network: Whether backends may make network calls.
        timeout_s: Default per-conversion time budget in seconds.
        max_bytes: Default maximum input size in bytes.
        source_path: The config file these settings came from, if any. Recorded
            so ``tokenmill config`` can say where a surprising value came from.
    """

    tokenizer: str = "o200k_base"
    backend: str | None = None
    output_format: OutputFormat = OutputFormat.MARKDOWN
    post_processors: tuple[str, ...] | None = None
    image_handling: ImageHandling = ImageHandling.KEEP
    link_handling: LinkHandling = LinkHandling.KEEP
    allow_network: bool = False
    timeout_s: float = 120.0
    max_bytes: int = 256 * 1024 * 1024
    source_path: Path | None = None

    def to_options(self, **overrides: Any) -> ConvertOptions:
        """Build the conversion options this config implies.

        Args:
            **overrides: The final layer — CLI flags. ``None`` values are
                ignored, so a flag the user did not pass never clobbers a
                configured value.

        Returns:
            The resolved options.
        """
        options = ConvertOptions(
            tokenizer=self.tokenizer,
            backend=self.backend,
            output_format=self.output_format,
            post_processors=self.post_processors,
            image_handling=self.image_handling,
            link_handling=self.link_handling,
            allow_network=self.allow_network,
            timeout_s=self.timeout_s,
            max_bytes=self.max_bytes,
        )
        supplied = {k: v for k, v in overrides.items() if v is not None}
        return options.with_(**supplied) if supplied else options


def find_config_file(start: Path | None = None) -> Path | None:
    """Locate the config file to read.

    Args:
        start: Directory to treat as the working directory. Defaults to the
            real one.

    Returns:
        The first existing config file in the documented order, or ``None``.
    """
    explicit = os.environ.get(CONFIG_PATH_ENV)
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else None

    directory = start if start is not None else Path.cwd()
    for name in PROJECT_FILENAMES:
        candidate = directory / name
        if candidate.is_file():
            return candidate

    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    user = base / "tokenmill" / "config.toml"
    return user if user.is_file() else None


def load_config(
    path: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    start: Path | None = None,
) -> Config:
    """Build a config from the defaults, a config file and the environment.

    Args:
        path: An explicit config file. When omitted, :func:`find_config_file`
            decides.
        environ: The environment to read overrides from. Defaults to the real
            one.
        start: Directory to search for a project config file.

    Returns:
        The resolved config, before CLI flags are applied.

    Raises:
        ConfigError: If the file is unreadable, is not valid TOML, contains an
            unknown key, or gives a value the wrong type.
    """
    config = Config()
    resolved = path if path is not None else find_config_file(start)
    if resolved is not None:
        config = _apply_file(config, resolved)
    return _apply_env(config, environ if environ is not None else os.environ)


def _apply_file(config: Config, path: Path) -> Config:
    """Overlay a TOML config file onto ``config``.

    Args:
        config: The config so far.
        path: The file to read.

    Returns:
        The updated config.

    Raises:
        ConfigError: If the file is unreadable, malformed, or has a bad key.
    """
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        msg = f"could not read config file {path}: {exc}"
        raise ConfigError(msg) from exc
    except tomllib.TOMLDecodeError as exc:
        msg = f"config file {path} is not valid TOML: {exc}"
        raise ConfigError(msg) from exc

    # A [tokenmill] table is supported so settings can live in a shared file
    # alongside other tools' sections.
    section = data.get("tokenmill", data)
    if not isinstance(section, dict):
        msg = f"config file {path}: [tokenmill] must be a table"
        raise ConfigError(msg)

    known = {f.name for f in fields(Config)} - {"source_path"}
    changes: dict[str, Any] = {}
    for key, value in section.items():
        if key not in known:
            msg = f"config file {path}: unknown setting {key!r} (known: {', '.join(sorted(known))})"
            raise ConfigError(msg)
        changes[key] = _coerce(key, value, str(path))
    return replace(config, **changes, source_path=path)


def _apply_env(config: Config, environ: Mapping[str, str]) -> Config:
    """Overlay ``TOKENMILL_*`` environment variables onto ``config``.

    Args:
        config: The config so far.
        environ: The environment to read.

    Returns:
        The updated config.

    Raises:
        ConfigError: If a variable holds a value of the wrong type.
    """
    known = {f.name for f in fields(Config)} - {"source_path"}
    changes: dict[str, Any] = {}
    for name in known:
        raw = environ.get(f"{ENV_PREFIX}{name.upper()}")
        if raw is None:
            continue
        changes[name] = _coerce(name, raw, f"${ENV_PREFIX}{name.upper()}")
    return replace(config, **changes) if changes else config


def _coerce(key: str, value: Any, origin: str) -> Any:
    """Convert a raw config value to the type its field expects.

    Args:
        key: The setting name.
        value: The raw value, from TOML or from the environment as a string.
        origin: Where it came from, for the error message.

    Returns:
        The converted value.

    Raises:
        ConfigError: If the value cannot be converted.
    """
    try:
        if key == "output_format":
            return OutputFormat(str(value))
        if key == "image_handling":
            return ImageHandling(str(value))
        if key == "link_handling":
            return LinkHandling(str(value))
        if key == "allow_network":
            return _as_bool(value)
        if key == "timeout_s":
            return float(value)
        if key == "max_bytes":
            return int(value)
        if key == "post_processors":
            if isinstance(value, str):
                return tuple(part.strip() for part in value.split(",") if part.strip())
            return tuple(str(item) for item in value)
        if key == "backend":
            text = str(value)
            return text or None
        return str(value)
    except (TypeError, ValueError) as exc:
        msg = f"{origin}: {key} = {value!r} is not valid: {exc}"
        raise ConfigError(msg) from exc


def _as_bool(value: Any) -> bool:
    """Interpret a TOML or environment value as a boolean.

    Args:
        value: A real boolean, or one of ``1/0``, ``true/false``, ``yes/no``,
            ``on/off``, case-insensitively.

    Returns:
        The boolean.

    Raises:
        ValueError: If the value is not recognisable as a boolean.
    """
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    msg = f"expected a boolean, got {value!r}"
    raise ValueError(msg)
