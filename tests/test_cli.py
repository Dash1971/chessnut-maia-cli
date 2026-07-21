# SPDX-License-Identifier: GPL-3.0-or-later

import chess
import pytest

from chessnut_maia_cli.cli import (
    PLAY_COMMANDS,
    PlayerColor,
    _format_pgn,
    _parse_player_color,
    _print_crash_pgn,
    _prompt_reconnect_to_board,
    _resignation_result,
    _save_pgn,
)
from chessnut_maia_cli.game import GameController, TakebackVariation


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


def test_format_pgn_skips_stale_takeback_variation_after_new_mainline() -> None:
    controller = GameController()
    moves = [
        "e2e4",
        "e7e6",
        "d2d4",
        "d7d5",
        "e4d5",
        "e6d5",
        "f1d3",
        "f8d6",
        "h2h3",
        "g8e7",
        "g1f3",
        "b8c6",
        "c2c3",
        "c8e6",
        "e1g1",
        "d8d7",
        "f1e1",
        "f7f6",
        "d1e2",
        "e6h3",
        "g2h3",
        "d7h3",
        "b1d2",
        "e8c8",
        "e2f1",
        "h3d7",
        "f1g2",
        "c8b8",
        "d2b3",
        "g7g5",
        "b3c5",
        "d6c5",
        "d4c5",
    ]
    for move in moves:
        controller.board.push(chess.Move.from_uci(move))
    controller.takeback_variations.append(
        TakebackVariation(
            base_ply=len(moves),
            moves=(
                chess.Move.from_uci("g6f4"),
                chess.Move.from_uci("c1f4"),
            ),
        )
    )

    pgn = _format_pgn(controller, white="maia3", black="Human", result="*")

    assert "15. Nb3 g5" in pgn
    assert "Nf4" not in pgn


def test_format_pgn_preserves_deeper_takebacks_as_continued_variation() -> None:
    controller = GameController()
    for move in [
        "e2e4",
        "e7e6",
        "d2d4",
        "d7d5",
        "e4d5",
        "e6d5",
        "f1d3",
        "f8d6",
        "h2h3",
        "g8e7",
        "g1f3",
        "b8c6",
        "c2c3",
        "c8e6",
        "e1g1",
        "d8d7",
        "f1e1",
        "f7f6",
        "d1e2",
        "e6h3",
        "g2h3",
        "d7h3",
        "b1d2",
        "e8c8",
        "e2f1",
        "h3d7",
        "f1g2",
        "c8b8",
        "d2b3",
        "e7g6",
        "b3c5",
        "d6c5",
        "d4c5",
        "g6f4",
        "c1f4",
    ]:
        controller.board.push(chess.Move.from_uci(move))

    controller.takeback_last_turn()
    controller.takeback_last_turn()
    controller.takeback_last_turn()
    for move in ["g7g5", "b3c5", "d6c5", "d4c5"]:
        controller.board.push(chess.Move.from_uci(move))

    pgn = _format_pgn(controller, white="maia3", black="Human", result="*")

    assert "15. Nb3 g5" in pgn
    assert "( 15... Ng6 16. Nc5 Bxc5 17. dxc5 Nf4 18. Bxf4 )" in pgn


def test_print_crash_pgn_outputs_partial_game(capsys) -> None:
    controller = GameController()
    controller.board.push(chess.Move.from_uci("d2d4"))
    controller.board.push(chess.Move.from_uci("e7e5"))

    _print_crash_pgn(
        controller,
        white="Human",
        black="maia3",
        black_elo=1600,
        error=RuntimeError("board disconnected"),
    )

    output = capsys.readouterr().out
    assert "Unexpected error: board disconnected" in output
    assert "Printing partial PGN before exiting." in output
    assert '[Termination "Aborted after error: RuntimeError"]' in output
    assert "1. d4 e5 *" in output


def test_prompt_reconnect_to_board_accepts_reconnect(monkeypatch) -> None:
    monkeypatch.setattr("typer.prompt", lambda _message: "r")

    assert _prompt_reconnect_to_board(RuntimeError("lost")) is True


def test_prompt_reconnect_to_board_accepts_quit(monkeypatch) -> None:
    monkeypatch.setattr("typer.prompt", lambda _message: "q")

    assert _prompt_reconnect_to_board(RuntimeError("lost")) is False


def test_prompt_reconnect_to_board_reprompts_invalid_choice(monkeypatch, capsys) -> None:
    choices = iter(["x", "reconnect"])
    monkeypatch.setattr("typer.prompt", lambda _message: next(choices))

    assert _prompt_reconnect_to_board(RuntimeError("lost")) is True
    assert "Please enter r to reconnect or q to quit." in capsys.readouterr().out


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
