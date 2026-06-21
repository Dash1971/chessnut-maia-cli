# SPDX-License-Identifier: GPL-3.0-or-later

"""Chessnut board transport primitives.

Protocol details are adapted from the GPL-3.0 Chessnut Air reference by
Roberto Marabini: https://github.com/rmarabini/chessnutair
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Iterable, Mapping


PieceMap = dict[str, str]

INIT_CODE = b"\x21\x01\x00"
WRITE_CHARACTERISTIC = "1B7E8272-2877-41C3-B46E-CF057C562023"
READ_CONFIRMATION_CHARACTERISTIC = "1B7E8273-2877-41C3-B46E-CF057C562023"
READ_DATA_CHARACTERISTIC = "1B7E8262-2877-41C3-B46E-CF057C562023"
BOARD_NOTIFICATION_HEADER = b"\x01\x24"
BOARD_PAYLOAD_LENGTH = 32
LED_COMMAND_PREFIX = b"\x0A\x08"
DEVICE_NAME_HINTS = ("Chessnut", "Smart Chess")

PIECE_CODES = {
    0x0: ".",
    0x1: "q",
    0x2: "k",
    0x3: "b",
    0x4: "p",
    0x5: "n",
    0x6: "R",
    0x7: "P",
    0x8: "r",
    0x9: "B",
    0xA: "N",
    0xB: "Q",
    0xC: "K",
}

FILES_FROM_BOARD_PAYLOAD = ("h", "g", "f", "e", "d", "c", "b", "a")


@dataclass(frozen=True)
class BoardState:
    """A physical board observation.

    Keys are algebraic square names such as ``"e4"``. Values use FEN piece
    letters: uppercase for White, lowercase for Black.
    """

    pieces: Mapping[str, str]

    def normalized(self) -> PieceMap:
        return {square: piece for square, piece in sorted(self.pieces.items()) if piece != "."}

    def render(self) -> str:
        lines = []
        pieces = self.normalized()
        for rank in range(8, 0, -1):
            row = [pieces.get(f"{file}{rank}", ".") for file in "abcdefgh"]
            lines.append(f"{rank}  {' '.join(row)}")
        lines.append("   a b c d e f g h")
        return "\n".join(lines)


@dataclass(frozen=True)
class BoardDevice:
    name: str
    address: str
    backend_device: object | None = None


class ChessnutBoard:
    """Bluetooth LE adapter for Chessnut boards."""

    def __init__(self, device: BoardDevice):
        self.device = device
        self._client = None

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
            if any(hint.lower() in name.lower() for hint in DEVICE_NAME_HINTS):
                matches.append(
                    BoardDevice(name=name, address=device.address, backend_device=device)
                )
        return matches

    async def connect(self) -> None:
        try:
            from bleak import BleakClient
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("Install bleak to connect to Chessnut boards.") from exc

        self._client = BleakClient(self.device.backend_device or self.device.address)
        await self._client.connect()

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    async def initialize(self) -> None:
        if self._client is None:
            raise RuntimeError("Board is not connected.")
        await self._client.write_gatt_char(WRITE_CHARACTERISTIC, INIT_CODE)

    async def read_once(self, timeout: float = 10.0) -> BoardState:
        """Connect, initialize, and wait for one board-state notification."""

        queue: asyncio.Queue[BoardState] = asyncio.Queue(maxsize=1)

        def notification_handler(_characteristic: object, data: bytearray) -> None:
            try:
                state = decode_board_notification(bytes(data))
            except ValueError:
                return
            if queue.empty():
                queue.put_nowait(state)

        await self.connect()
        try:
            if self._client is None:
                raise RuntimeError("Board is not connected.")
            await self._client.start_notify(READ_DATA_CHARACTERISTIC, notification_handler)
            await self.initialize()
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        finally:
            if self._client is not None:
                await self._client.stop_notify(READ_DATA_CHARACTERISTIC)
            await self.disconnect()

    async def watch(self) -> AsyncIterator[BoardState]:
        """Keep the board connected and yield each decoded board state."""

        queue: asyncio.Queue[BoardState] = asyncio.Queue()

        def notification_handler(_characteristic: object, data: bytearray) -> None:
            try:
                state = decode_board_notification(bytes(data))
            except ValueError:
                return
            queue.put_nowait(state)

        await self.connect()
        try:
            if self._client is None:
                raise RuntimeError("Board is not connected.")
            await self._client.start_notify(READ_DATA_CHARACTERISTIC, notification_handler)
            await self.initialize()
            while True:
                yield await queue.get()
        finally:
            if self._client is not None:
                await self._client.stop_notify(READ_DATA_CHARACTERISTIC)
            await self.disconnect()

    async def set_leds(self, squares: Iterable[str]) -> None:
        """Light the supplied squares on a connected board."""

        if self._client is None:
            raise RuntimeError("Board is not connected.")
        await self._client.write_gatt_char(WRITE_CHARACTERISTIC, encode_led_command(squares))


def decode_board_notification(data: bytes) -> BoardState:
    """Decode a full Chessnut board notification into a board state."""

    payload = extract_board_payload(data)
    return decode_board_payload(payload)


def extract_board_payload(data: bytes) -> bytes:
    """Extract the 32 board bytes from a notification or raw payload."""

    if len(data) == BOARD_PAYLOAD_LENGTH:
        return data
    if len(data) >= 34 and data[:2] == BOARD_NOTIFICATION_HEADER:
        return data[2:34]
    raise ValueError(f"Expected 32-byte payload or Chessnut notification, got {len(data)} bytes.")


def decode_board_payload(payload: bytes) -> BoardState:
    """Decode the 32-byte Chessnut board payload.

    The payload is ordered H8, G8, F8, E8 ... B1, A1. Each byte stores two
    squares: low nibble first, high nibble second.
    """

    if len(payload) != BOARD_PAYLOAD_LENGTH:
        raise ValueError(f"Expected {BOARD_PAYLOAD_LENGTH} board bytes, got {len(payload)}.")

    pieces: PieceMap = {}
    index = 0
    for rank in range(8, 0, -1):
        for file_pair in range(0, 8, 2):
            byte = payload[index]
            index += 1
            for file_name, code in (
                (FILES_FROM_BOARD_PAYLOAD[file_pair], byte & 0x0F),
                (FILES_FROM_BOARD_PAYLOAD[file_pair + 1], byte >> 4),
            ):
                piece = PIECE_CODES.get(code)
                if piece is None:
                    raise ValueError(f"Unknown Chessnut piece code: 0x{code:x}.")
                if piece != ".":
                    pieces[f"{file_name}{rank}"] = piece
    return BoardState(pieces)


def encode_led_command(squares: Iterable[str]) -> bytes:
    """Encode a Chessnut LED command for algebraic square names."""

    rows = [0] * 8
    for square in squares:
        normalized = square.strip().lower()
        valid_square = (
            len(normalized) == 2
            and normalized[0] in "abcdefgh"
            and normalized[1] in "12345678"
        )
        if not valid_square:
            raise ValueError(f"Invalid square: {square!r}.")
        file_index = ord(normalized[0]) - ord("a")
        rank = int(normalized[1])
        row_index = 8 - rank
        bit = 7 - file_index
        rows[row_index] |= 1 << bit
    return LED_COMMAND_PREFIX + bytes(rows)
