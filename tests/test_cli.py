# SPDX-License-Identifier: GPL-3.0-or-later

import chess

from chessnut_maia_cli.cli import _format_pgn
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
