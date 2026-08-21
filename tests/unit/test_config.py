"""Layered configuration: defaults, then file, then environment, then flags."""

from __future__ import annotations

from pathlib import Path

import pytest

from tokenmill.core.config import (
    CONFIG_PATH_ENV,
    Config,
    find_config_file,
    load_config,
)
from tokenmill.core.errors import ConfigError
from tokenmill.core.models import ImageHandling, LinkHandling, OutputFormat


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep the developer's own config and environment out of these tests."""
    for name in list(__import__("os").environ):
        if name.startswith("TOKENMILL_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def write_config(directory: Path, body: str, name: str = "tokenmill.toml") -> Path:
    """Write a config file and return its path.

    Args:
        directory: Where to write it.
        body: The TOML body.
        name: The file name.

    Returns:
        The path written.
    """
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


class TestDefaults:
    def test_the_defaults_are_the_documented_ones(self) -> None:
        config = Config()

        assert config.tokenizer == "o200k_base"
        assert config.backend is None
        assert config.output_format is OutputFormat.MARKDOWN
        assert config.post_processors is None
        assert config.allow_network is False

    def test_loading_with_no_file_anywhere_gives_the_defaults(self, tmp_path: Path) -> None:
        config = load_config(start=tmp_path)

        assert config == Config()
        assert config.source_path is None


class TestFileLayer:
    def test_a_bare_table_is_read(self, tmp_path: Path) -> None:
        path = write_config(tmp_path, 'tokenizer = "cl100k_base"\nbackend = "plaintext"\n')

        config = load_config(path)

        assert config.tokenizer == "cl100k_base"
        assert config.backend == "plaintext"
        assert config.source_path == path

    def test_a_tokenmill_section_is_read_so_a_file_can_be_shared(self, tmp_path: Path) -> None:
        path = write_config(tmp_path, '[tokenmill]\ntokenizer = "p50k_base"\n')

        assert load_config(path).tokenizer == "p50k_base"

    def test_enums_are_coerced_from_strings(self, tmp_path: Path) -> None:
        path = write_config(
            tmp_path,
            'output_format = "text"\nimage_handling = "alt"\nlink_handling = "strip"\n',
        )

        config = load_config(path)

        assert config.output_format is OutputFormat.TEXT
        assert config.image_handling is ImageHandling.ALT
        assert config.link_handling is LinkHandling.STRIP

    def test_a_post_processor_list_becomes_a_tuple(self, tmp_path: Path) -> None:
        path = write_config(tmp_path, 'post_processors = ["links", "normalize_whitespace"]\n')

        assert load_config(path).post_processors == ("links", "normalize_whitespace")

    def test_an_unknown_setting_is_rejected_rather_than_ignored(self, tmp_path: Path) -> None:
        """A silently ignored typo is a setting that mysteriously does nothing."""
        path = write_config(tmp_path, 'tokeniser = "cl100k_base"\n')

        with pytest.raises(ConfigError, match="unknown setting 'tokeniser'"):
            load_config(path)

    def test_a_bad_enum_value_names_the_setting(self, tmp_path: Path) -> None:
        path = write_config(tmp_path, 'output_format = "parquet"\n')

        with pytest.raises(ConfigError, match="output_format"):
            load_config(path)

    def test_malformed_toml_is_reported_with_its_path(self, tmp_path: Path) -> None:
        path = write_config(tmp_path, "this is not toml = = =\n")

        with pytest.raises(ConfigError, match="not valid TOML"):
            load_config(path)

    def test_an_unreadable_file_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="could not read"):
            load_config(tmp_path / "directory-not-a-file" / "x.toml")


class TestEnvironmentLayer:
    def test_the_environment_overrides_the_file(self, tmp_path: Path) -> None:
        path = write_config(tmp_path, 'tokenizer = "from-file"\n')

        config = load_config(path, environ={"TOKENMILL_TOKENIZER": "from-env"})

        assert config.tokenizer == "from-env"

    def test_booleans_accept_the_usual_spellings(self, tmp_path: Path) -> None:
        for text, expected in [("1", True), ("true", True), ("no", False), ("OFF", False)]:
            config = load_config(start=tmp_path, environ={"TOKENMILL_ALLOW_NETWORK": text})
            assert config.allow_network is expected

    def test_a_bad_boolean_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="allow_network"):
            load_config(start=tmp_path, environ={"TOKENMILL_ALLOW_NETWORK": "perhaps"})

    def test_a_comma_separated_chain_is_split(self, tmp_path: Path) -> None:
        config = load_config(
            start=tmp_path, environ={"TOKENMILL_POST_PROCESSORS": "links, normalize_whitespace"}
        )

        assert config.post_processors == ("links", "normalize_whitespace")

    def test_numbers_are_coerced(self, tmp_path: Path) -> None:
        config = load_config(
            start=tmp_path,
            environ={"TOKENMILL_TIMEOUT_S": "30", "TOKENMILL_MAX_BYTES": "1024"},
        )

        assert config.timeout_s == 30.0
        assert config.max_bytes == 1024


class TestFlagLayer:
    def test_flags_override_everything(self, tmp_path: Path) -> None:
        path = write_config(tmp_path, 'tokenizer = "from-file"\n')
        config = load_config(path, environ={"TOKENMILL_TOKENIZER": "from-env"})

        options = config.to_options(tokenizer="from-flag")

        assert options.tokenizer == "from-flag"

    def test_a_flag_that_was_not_passed_does_not_clobber_a_configured_value(
        self, tmp_path: Path
    ) -> None:
        path = write_config(tmp_path, 'tokenizer = "from-file"\nbackend = "plaintext"\n')
        config = load_config(path)

        options = config.to_options(tokenizer=None, backend=None)

        assert options.tokenizer == "from-file"
        assert options.backend == "plaintext"

    def test_to_options_carries_every_setting_across(self, tmp_path: Path) -> None:
        path = write_config(
            tmp_path,
            'tokenizer = "t"\nallow_network = true\ntimeout_s = 5.0\nmax_bytes = 99\n',
        )

        options = load_config(path).to_options()

        assert options.tokenizer == "t"
        assert options.allow_network is True
        assert options.timeout_s == 5.0
        assert options.max_bytes == 99


class TestDiscovery:
    def test_the_explicit_environment_path_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chosen = write_config(tmp_path, "", name="chosen.toml")
        write_config(tmp_path, "")
        monkeypatch.setenv(CONFIG_PATH_ENV, str(chosen))

        assert find_config_file(tmp_path) == chosen

    def test_a_project_file_beats_the_user_config(self, tmp_path: Path) -> None:
        user = tmp_path / "xdg" / "tokenmill" / "config.toml"
        user.parent.mkdir(parents=True)
        user.write_text("", encoding="utf-8")
        project = write_config(tmp_path, "")

        assert find_config_file(tmp_path) == project

    def test_the_dotfile_name_is_also_recognised(self, tmp_path: Path) -> None:
        path = write_config(tmp_path, "", name=".tokenmill.toml")

        assert find_config_file(tmp_path) == path

    def test_the_user_config_is_used_when_there_is_no_project_file(self, tmp_path: Path) -> None:
        user = tmp_path / "xdg" / "tokenmill" / "config.toml"
        user.parent.mkdir(parents=True)
        user.write_text("", encoding="utf-8")

        assert find_config_file(tmp_path) == user

    def test_a_missing_explicit_path_finds_nothing_rather_than_falling_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A named-but-absent config file is a mistake worth surfacing.

        Quietly loading a different file instead would hide the typo.
        """
        write_config(tmp_path, "")
        monkeypatch.setenv(CONFIG_PATH_ENV, str(tmp_path / "absent.toml"))

        assert find_config_file(tmp_path) is None
