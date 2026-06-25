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


def board_from_piece_map(pieces: PieceMap, *, white_to_move: bool) -> "chess.Board":
    """Build a chess board from a physical piece map.

    A Chessnut board reports piece placement only. Move counters, en-passant
    state, and historical castling rights cannot be recovered from sensors, so
    this helper reconstructs the useful playable state from what is visible.
    """

    import chess

    board = chess.Board(None)
    for square_name, symbol in pieces.items():
        square = chess.parse_square(square_name)
        board.set_piece_at(square, chess.Piece.from_symbol(symbol))

    board.turn = chess.WHITE if white_to_move else chess.BLACK
    board.castling_rights = _infer_castling_rights(board)
    board.ep_square = None
    board.halfmove_clock = 0
    board.fullmove_number = 1
    board.clear_stack()
    return board


def _infer_castling_rights(board: "chess.Board") -> int:
    import chess

    rights = 0
    home_positions = (
        (chess.E1, chess.H1, chess.WHITE),
        (chess.E1, chess.A1, chess.WHITE),
        (chess.E8, chess.H8, chess.BLACK),
        (chess.E8, chess.A8, chess.BLACK),
    )
    for king_square, rook_square, color in home_positions:
        king = board.piece_at(king_square)
        rook = board.piece_at(rook_square)
        if (
            king is not None
            and rook is not None
            and king.piece_type == chess.KING
            and rook.piece_type == chess.ROOK
            and king.color == color
            and rook.color == color
        ):
            rights |= chess.BB_SQUARES[rook_square]
    return rights


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
