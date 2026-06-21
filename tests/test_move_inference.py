# SPDX-License-Identifier: GPL-3.0-or-later

import chess
import pytest

from chessnut_maia_cli.board import BoardState
from chessnut_maia_cli.game import board_to_piece_map, infer_legal_move


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


def test_rejects_impossible_observation() -> None:
    board = chess.Board()
    impossible = BoardState({"e4": "P"})

    with pytest.raises(ValueError, match="does not match any legal move"):
        infer_legal_move(board, impossible)
