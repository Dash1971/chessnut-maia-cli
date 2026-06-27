# SPDX-License-Identifier: GPL-3.0-or-later

import chess
import pytest

from chessnut_maia_cli.cli import PlayerColor, _format_pgn, _parse_player_color
from chessnut_maia_cli.game import GameController


def test_format_pgn_supports_human_as_black() -> None:
    controller = GameController()
    controller.board.push(chess.Move.from_uci("e2e4"))
    controller.board.push(chess.Move.from_uci("e7e5"))

    pgn = _format_pgn(
        controller,
        white="maia2",
        black="Human",
        result="*",
        termination="Interrupted by user",
    )

    assert '[White "maia2"]' in pgn
    assert '[Black "Human"]' in pgn
    assert '[Termination "Interrupted by user"]' in pgn


def test_format_pgn_keeps_taken_back_moves_as_variation() -> None:
    controller = GameController()
    for move in ["e2e4", "e7e5"]:
        controller.board.push(chess.Move.from_uci(move))
    controller.takeback_last_turn()
    for move in ["d2d4", "d7d5"]:
        controller.board.push(chess.Move.from_uci(move))

    pgn = _format_pgn(controller, white="Human", black="maia2", result="*")

    assert "1. d4" in pgn
    assert "1... d5" in pgn
    assert "( 1. e4 e5 )" in pgn


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("white", PlayerColor.white),
        ("w", PlayerColor.white),
        ("black", PlayerColor.black),
        ("b", PlayerColor.black),
        ("random", PlayerColor.random),
        ("r", PlayerColor.random),
        (" W ", PlayerColor.white),
    ],
)
def test_parse_player_color_aliases(value: str, expected: PlayerColor) -> None:
    assert _parse_player_color(value) == expected


def test_parse_player_color_rejects_unknown_value() -> None:
    with pytest.raises(Exception, match="Choose white, black, random"):
        _parse_player_color("blue")
