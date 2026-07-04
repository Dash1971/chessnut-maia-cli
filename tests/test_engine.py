# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

from chessnut_maia_cli.engine import EngineConfig, MaiaEngine


def test_engine_config_expands_opening_book_path() -> None:
    config = EngineConfig.default(
        "maia2",
        elo=1500,
        book_file=Path("~/chess/books/lichess_1600_all.bin"),
        human_time=False,
    )

    assert config.name == "maia2"
    assert config.elo == 1500
    assert config.book_file == Path.home() / "chess/books/lichess_1600_all.bin"
    assert config.human_time is False
    assert config.timeout_s == 30.0


def test_engine_config_accepts_maia3_sampling_options() -> None:
    config = EngineConfig.default(
        "maia3",
        temperature=0.5,
        top_p=0.9,
    )

    assert config.name == "maia3"
    assert config.temperature == 0.5
    assert config.top_p == 0.9


def test_engine_config_accepts_custom_timeout() -> None:
    config = EngineConfig.default("maia3", timeout_s=45.0)

    assert config.timeout_s == 45.0


def test_maia3_uci_options_include_sampling() -> None:
    config = EngineConfig.default(
        "maia3",
        elo=1600,
        book_file=Path("~/chess/books/lichess_1600_all.bin"),
        human_time=True,
        temperature=0.5,
        top_p=0.9,
    )

    assert MaiaEngine(config).uci_options() == {
        "Elo": 1600,
        "BookFile": str(Path.home() / "chess/books/lichess_1600_all.bin"),
        "HumanTime": True,
        "Temperature": 0.5,
        "TopP": 0.9,
    }
