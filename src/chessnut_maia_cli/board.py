# SPDX-License-Identifier: GPL-3.0-or-later

"""Chessnut board transport primitives.

The Bluetooth implementation is intentionally small at this stage. The move
logic is testable without a physical board; the BLE details will be validated
against a Chessnut Go before this module grows protocol-specific behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


PieceMap = dict[str, str]


@dataclass(frozen=True)
class BoardState:
    """A physical board observation.

    Keys are algebraic square names such as ``"e4"``. Values use FEN piece
    letters: uppercase for White, lowercase for Black.
    """

    pieces: Mapping[str, str]

    def normalized(self) -> PieceMap:
        return {square: piece for square, piece in sorted(self.pieces.items()) if piece != "."}


@dataclass(frozen=True)
class BoardDevice:
    name: str
    address: str


class ChessnutBoard:
    """Bluetooth LE adapter for Chessnut boards."""

    def __init__(self, device: BoardDevice):
        self.device = device

    @staticmethod
    async def scan(timeout: float = 5.0) -> list[BoardDevice]:
        """Return nearby devices that look like Chessnut boards."""

        try:
            from bleak import BleakScanner
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("Install bleak to scan for Chessnut boards.") from exc

        devices = await BleakScanner.discover(timeout=timeout)
        matches: list[BoardDevice] = []
        for device in devices:
            name = device.name or ""
            if "chessnut" in name.lower():
                matches.append(BoardDevice(name=name, address=device.address))
        return matches

    async def read_once(self) -> BoardState:
        """Read one board state.

        This will become the protocol validation point once tested against a
        real Chessnut Go.
        """

        raise NotImplementedError("Board-state decoding is not implemented yet.")
