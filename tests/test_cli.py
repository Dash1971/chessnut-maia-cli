# SPDX-License-Identifier: GPL-3.0-or-later

import chess
import pytest

from chessnut_maia_cli.cli import (
    PLAY_COMMANDS,
    PlayerColor,
    _format_pgn,
    _parse_player_color,
    _resignation_result,
    _save_pgn,
)
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
    assert '[Round "' not in pgn


def test_format_pgn_includes_engine_elo() -> None:
    controller = GameController()

    pgn = _format_pgn(
        controller,
        white="Human",
        black="maia2",
        black_elo=1500,
        result="*",
    )

    assert '[BlackElo "1500"]' in pgn
    assert '[WhiteElo "' not in pgn


def test_format_pgn_describes_checkmate_termination() -> None:
    controller = GameController()
    for move in ["f2f3", "e7e5", "g2g4", "d8h4"]:
        controller.board.push(chess.Move.from_uci(move))

    pgn = _format_pgn(controller, white="Human", black="maia2")

    assert '[Result "0-1"]' in pgn
    assert '[Termination "Black won by checkmate"]' in pgn


def test_format_pgn_describes_draw_termination() -> None:
    controller = GameController()
    controller.board = chess.Board("7k/5K2/6Q1/8/8/8/8/8 b - - 0 1")

    pgn = _format_pgn(controller, white="Human", black="maia2")

    assert '[Result "1/2-1/2"]' in pgn
    assert '[Termination "Draw by stalemate"]' in pgn


def test_resignation_result() -> None:
    assert _resignation_result(human_is_white=True) == ("0-1", "White resigned")
    assert _resignation_result(human_is_white=False) == ("1-0", "Black resigned")


def test_play_command_help_mentions_resign() -> None:
    assert "resign" in PLAY_COMMANDS


def test_save_pgn_uses_timestamp_and_player_names(tmp_path) -> None:
    path = _save_pgn(
        "1. e4 *",
        white="Human Player",
        black="maia2/1500",
        directory=tmp_path,
    )

    assert path.parent == tmp_path
    assert path.name.endswith("_Human-Player_maia2-1500.pgn")
    assert path.read_text(encoding="utf-8") == "1. e4 *\n"


def test_save_pgn_avoids_overwriting_existing_file(tmp_path) -> None:
    first = _save_pgn("first", white="Human", black="maia2", directory=tmp_path)
    second = _save_pgn("second", white="Human", black="maia2", directory=tmp_path)

    assert first != second
    assert second.stem.endswith("_2")


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
