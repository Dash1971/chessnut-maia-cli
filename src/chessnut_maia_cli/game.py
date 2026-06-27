# SPDX-License-Identifier: GPL-3.0-or-later

"""Game-state and move-inference helpers."""

from __future__ import annotations

from collections import Counter
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

    if _looks_like_mis_set_starting_position(pieces):
        raise ValueError("Physical board looks like a mis-set starting position.")

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
    if not board.is_valid():
        raise ValueError("Physical board position is not a valid chess position.")
    return board


def is_resumable_piece_map(pieces: PieceMap) -> bool:
    """Return whether a physical position is complete enough to offer resume."""

    for white_to_move in (True, False):
        try:
            board_from_piece_map(pieces, white_to_move=white_to_move)
        except ValueError:
            continue
        return True
    return False


def _looks_like_mis_set_starting_position(pieces: PieceMap) -> bool:
    """Catch all-pieces-present setup mistakes before resuming a poisoned game."""

    import chess

    starting = board_to_piece_map(chess.Board())
    if pieces == starting:
        return False
    if Counter(pieces.values()) != Counter(starting.values()):
        return False
    pawn_squares = [f"{file}{rank}" for file in "abcdefgh" for rank in ("2", "7")]
    return all(pieces.get(square) == starting[square] for square in pawn_squares)


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


def infer_resilient_legal_move(board: "chess.Board", observed_after: BoardState) -> "chess.Move":
    """Infer a move, tolerating unrelated sensor mismatches after resync.

    The normal path requires the full physical board to match the exact legal
    post-move position. If the board missed a prior notification, a later
    position can include a clear human move plus stale differences elsewhere.
    This fallback accepts only a unique legal move whose source emptied and
    destination contains the moved piece.
    """

    import chess

    try:
        return infer_legal_move(board, observed_after)
    except ValueError as exact_error:
        target = observed_after.normalized()
        plausible: list[tuple[int, chess.Move]] = []

        for move in board.legal_moves:
            piece = board.piece_at(move.from_square)
            if piece is None:
                continue

            from_square = chess.square_name(move.from_square)
            to_square = chess.square_name(move.to_square)
            moved_symbol = piece.symbol()
            if move.promotion is not None:
                moved_symbol = chess.Piece(move.promotion, piece.color).symbol()

            if target.get(to_square) != moved_symbol:
                continue
            if target.get(from_square) == piece.symbol():
                continue

            candidate = board.copy(stack=False)
            candidate.push(move)
            candidate_map = board_to_piece_map(candidate)
            mismatches = _piece_map_mismatch_count(candidate_map, target)
            plausible.append((mismatches, move))

        if not plausible:
            raise exact_error

        plausible.sort(key=lambda item: item[0])
        best_mismatch_count, best_move = plausible[0]
        if len(plausible) == 1 or best_mismatch_count < plausible[1][0]:
            return best_move

        tied = [move.uci() for count, move in plausible if count == best_mismatch_count]
        moves = ", ".join(tied)
        raise ValueError(f"Observed board state is ambiguous after resync: {moves}.") from exact_error


def _piece_map_mismatch_count(left: PieceMap, right: PieceMap) -> int:
    squares = set(left) | set(right)
    return sum(1 for square in squares if left.get(square) != right.get(square))


def changed_squares(left: PieceMap, right: PieceMap) -> list[str]:
    """Return squares whose visible pieces differ between two physical positions."""

    return sorted(
        square for square in set(left) | set(right) if left.get(square) != right.get(square)
    )


def takeback_last_turn(board: "chess.Board") -> list["chess.Move"]:
    """Pop the last player/engine turn, or the only available move."""

    if not board.move_stack:
        raise ValueError("No moves to take back.")

    pop_count = min(2, len(board.move_stack))
    return [board.pop() for _ in range(pop_count)]


@dataclass
class TakebackVariation:
    """A sequence removed by takeback, anchored to a mainline ply."""

    base_ply: int
    moves: tuple["chess.Move", ...]


@dataclass
class GameController:
    """Coordinate board observations and engine moves."""

    board: "chess.Board" = field(default_factory=lambda: _new_board())
    takeback_variations: list[TakebackVariation] = field(default_factory=list)

    def accept_human_position(self, observed_after: BoardState) -> "chess.Move":
        move = infer_legal_move(self.board, observed_after)
        self.board.push(move)
        return move

    def accept_engine_move(self, move: "chess.Move") -> None:
        if move not in self.board.legal_moves:
            raise ValueError(f"Engine returned illegal move: {move.uci()}")
        self.board.push(move)

    def takeback_last_turn(self) -> list["chess.Move"]:
        popped_moves = takeback_last_turn(self.board)
        self.takeback_variations.append(
            TakebackVariation(
                base_ply=len(self.board.move_stack),
                moves=tuple(reversed(popped_moves)),
            )
        )
        return popped_moves


def _new_board() -> "chess.Board":
    import chess

    return chess.Board()
