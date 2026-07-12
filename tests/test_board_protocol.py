# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio

import pytest

from chessnut_maia_cli.board import (
    BoardDevice,
    BoardState,
    ChessnutBoard,
    decode_battery_response,
    decode_board_notification,
    decode_board_payload,
    encode_beep_command,
    encode_led_command,
)


STARTING_POSITION_PAYLOAD = bytes.fromhex(
    "58 23 31 85 44 44 44 44"
    "00 00 00 00 00 00 00 00"
    "00 00 00 00 00 00 00 00"
    "77 77 77 77 A6 C9 9B 6A"
)


def test_decode_starting_position_payload() -> None:
    state = decode_board_payload(STARTING_POSITION_PAYLOAD)

    assert state.normalized() == {
        "a1": "R",
        "b1": "N",
        "c1": "B",
        "d1": "Q",
        "e1": "K",
        "f1": "B",
        "g1": "N",
        "h1": "R",
        "a2": "P",
        "b2": "P",
        "c2": "P",
        "d2": "P",
        "e2": "P",
        "f2": "P",
        "g2": "P",
        "h2": "P",
        "a7": "p",
        "b7": "p",
        "c7": "p",
        "d7": "p",
        "e7": "p",
        "f7": "p",
        "g7": "p",
        "h7": "p",
        "a8": "r",
        "b8": "n",
        "c8": "b",
        "d8": "q",
        "e8": "k",
        "f8": "b",
        "g8": "n",
        "h8": "r",
    }


def test_decode_full_notification() -> None:
    notification = b"\x01\x24" + STARTING_POSITION_PAYLOAD + b"\x00\x00\x00\x00"
    state = decode_board_notification(notification)
    assert state.normalized()["e1"] == "K"
    assert state.normalized()["e8"] == "k"


def test_render_board_state() -> None:
    state = BoardState({"e4": "P", "e5": "p"})
    assert state.render().splitlines()[3] == "5  . . . . p . . ."
    assert state.render().splitlines()[4] == "4  . . . . P . . ."


def test_encode_led_command_for_move() -> None:
    assert encode_led_command(["e2", "e4"]) == bytes.fromhex("0A 08 00 00 00 00 08 00 08 00")


def test_encode_led_command_rejects_bad_square() -> None:
    with pytest.raises(ValueError, match="Invalid square"):
        encode_led_command(["i9"])


def test_encode_beep_command_defaults() -> None:
    assert encode_beep_command() == bytes.fromhex("0B 04 03 E8 00 C8")


def test_encode_beep_command_rejects_out_of_range_values() -> None:
    with pytest.raises(ValueError, match="frequency_hz"):
        encode_beep_command(frequency_hz=0)
    with pytest.raises(ValueError, match="duration_ms"):
        encode_beep_command(duration_ms=0)


def test_decode_battery_response() -> None:
    battery = decode_battery_response(bytes.fromhex("2A 02 43 00"))

    assert battery.percent == 67
    assert battery.charging is False


def test_decode_charging_battery_response() -> None:
    battery = decode_battery_response(bytes.fromhex("2A 02 C3 00"))

    assert battery.percent == 67
    assert battery.charging is True


def test_decode_battery_response_rejects_bad_packets() -> None:
    with pytest.raises(ValueError, match="battery response"):
        decode_battery_response(bytes.fromhex("23 01 00"))
    with pytest.raises(ValueError, match="percentage"):
        decode_battery_response(bytes.fromhex("2A 02 7F 00"))


def test_watch_suppresses_stop_notify_failure_during_cleanup(monkeypatch) -> None:
    class HalfDisconnectedClient:
        async def start_notify(self, *_args) -> None:
            return None

        async def write_gatt_char(self, *_args) -> None:
            return None

        async def stop_notify(self, *_args) -> None:
            raise RuntimeError("Service Discovery has not been performed yet")

        async def disconnect(self) -> None:
            return None

    async def run_watch_cleanup() -> None:
        board = ChessnutBoard(BoardDevice(name="Chessnut", address="test"))

        async def fake_connect() -> None:
            board._client = HalfDisconnectedClient()

        monkeypatch.setattr(board, "connect", fake_connect)
        states = board.watch().__aiter__()
        task = asyncio.create_task(states.__anext__())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert board._client is None

    asyncio.run(run_watch_cleanup())
