# SPDX-License-Identifier: GPL-3.0-or-later

import chess
import pytest

from chessnut_maia_cli.board import BoardState
from chessnut_maia_cli.game import (
    GameController,
    board_from_piece_map,
    board_to_piece_map,
    changed_squares,
    infer_legal_move,
    infer_resilient_legal_move,
    takeback_last_turn,
)


def observed_after(board: chess.Board, move_uci: str) -> BoardState:
    board = board.copy(stack=False)
    board.push(chess.Move.from_uci(move_uci))
    return BoardState(board_to_piece_map(board))


def test_infers_simple_pawn_move() -> None:
    board = chess.Board()
    move = infer_legal_move(board, observed_after(board, "e2e4"))
    assert move == chess.Move.from_uci("e2e4")


def test_infers_capture() -> None:
    board = chess.Board()
    for move in ["e2e4", "d7d5"]:
        board.push(chess.Move.from_uci(move))

    move = infer_legal_move(board, observed_after(board, "e4d5"))
    assert move == chess.Move.from_uci("e4d5")


def test_infers_kingside_castle() -> None:
    board = chess.Board("rnbqkbnr/pppppppp/8/8/8/5N2/PPPPBPPP/RNBQK2R w KQkq - 2 3")
    move = infer_legal_move(board, observed_after(board, "e1g1"))
    assert move == chess.Move.from_uci("e1g1")


def test_builds_board_from_physical_position() -> None:
    original = chess.Board()
    for move in ["e2e4", "e7e5", "g1f3"]:
        original.push(chess.Move.from_uci(move))

    resumed = board_from_piece_map(board_to_piece_map(original), white_to_move=False)

    assert board_to_piece_map(resumed) == board_to_piece_map(original)
    assert resumed.turn == chess.BLACK


def test_rejects_invalid_physical_resume_position() -> None:
    pieces = board_to_piece_map(chess.Board())
    pieces["e1"] = "R"
    pieces["h1"] = "K"

    with pytest.raises(ValueError, match="mis-set starting position"):
        board_from_piece_map(pieces, white_to_move=True)


def test_resumed_castled_position_has_no_castling_rights_for_castled_side() -> None:
    board = chess.Board("rnbqkbnr/pppppppp/8/8/8/5N2/PPPPBPPP/RNBQK2R w KQkq - 2 3")
    board.push(chess.Move.from_uci("e1g1"))

    resumed = board_from_piece_map(board_to_piece_map(board), white_to_move=False)

    assert not resumed.has_castling_rights(chess.WHITE)
    assert resumed.has_castling_rights(chess.BLACK)


def test_rejects_impossible_observation() -> None:
    board = chess.Board()
    impossible = BoardState({"e4": "P"})

    with pytest.raises(ValueError, match="does not match any legal move"):
        infer_legal_move(board, impossible)


def test_resilient_inference_accepts_unique_move_with_unrelated_mismatch() -> None:
    board = chess.Board()
    for move in ["e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6"]:
        board.push(chess.Move.from_uci(move))

    observed = observed_after(board, "h5f7")
    pieces = observed.normalized()
    del pieces["a8"]

    move = infer_resilient_legal_move(board, BoardState(pieces))

    assert move == chess.Move.from_uci("h5f7")


def test_changed_squares_reports_visible_differences() -> None:
    assert changed_squares({"e2": "P", "e4": "p"}, {"e4": "P"}) == ["e2", "e4"]


def test_takeback_pops_engine_and_human_even_when_engine_move_is_pending() -> None:
    board = chess.Board()
    for move in ["e2e4", "e7e5"]:
        board.push(chess.Move.from_uci(move))

    popped = takeback_last_turn(board)

    assert popped == [chess.Move.from_uci("e7e5"), chess.Move.from_uci("e2e4")]
    assert not board.move_stack


def test_takeback_records_removed_moves_as_variation() -> None:
    controller = GameController()
    for move in ["e2e4", "e7e5"]:
        controller.board.push(chess.Move.from_uci(move))

    popped = controller.takeback_last_turn()

    assert popped == [chess.Move.from_uci("e7e5"), chess.Move.from_uci("e2e4")]
    assert controller.takeback_variations[0].base_ply == 0
    assert controller.takeback_variations[0].moves == (
        chess.Move.from_uci("e2e4"),
        chess.Move.from_uci("e7e5"),
    )


def test_takeback_single_available_move() -> None:
    board = chess.Board()
    board.push(chess.Move.from_uci("e2e4"))

    popped = takeback_last_turn(board)

    assert popped == [chess.Move.from_uci("e2e4")]
    assert not board.move_stack
