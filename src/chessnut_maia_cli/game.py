# SPDX-License-Identifier: GPL-3.0-or-later

"""Game-state and move-inference helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from .board import BoardState, PieceMap


def board_to_piece_map(board: "chess.Board") -> PieceMap:
    """Convert a python-chess board to a physical-board style piece map."""

    import chess

    pieces: PieceMap = {}
    for square, piece in board.piece_map().items():
        pieces[chess.square_name(square)] = piece.symbol()
    return pieces


def infer_legal_move(board: "chess.Board", observed_after: BoardState) -> "chess.Move":
    """Infer the legal move that transforms ``board`` into ``observed_after``.

    Comparing complete legal outcomes is more robust than hand-parsing square
    deltas because it naturally covers captures, castling, en passant, and
    promotion piece identity.
    """

    matches = []
    target = observed_after.normalized()
    for move in board.legal_moves:
        candidate = board.copy(stack=False)
        candidate.push(move)
        if board_to_piece_map(candidate) == target:
            matches.append(move)

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError("Observed board state does not match any legal move.")

    moves = ", ".join(move.uci() for move in matches)
    raise ValueError(f"Observed board state is ambiguous: {moves}.")


@dataclass
class GameController:
    """Coordinate board observations and engine moves."""

    board: "chess.Board" = field(default_factory=lambda: _new_board())

    def accept_human_position(self, observed_after: BoardState) -> "chess.Move":
        move = infer_legal_move(self.board, observed_after)
        self.board.push(move)
        return move

    def accept_engine_move(self, move: "chess.Move") -> None:
        if move not in self.board.legal_moves:
            raise ValueError(f"Engine returned illegal move: {move.uci()}")
        self.board.push(move)


def _new_board() -> "chess.Board":
    import chess

    return chess.Board()
