# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

from chessnut_maia_cli.engine import EngineConfig


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
