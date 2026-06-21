# SPDX-License-Identifier: GPL-3.0-or-later

"""Command-line entry point."""

from __future__ import annotations

import asyncio
from enum import Enum

import typer

from .board import BoardDevice, ChessnutBoard
from .engine import EngineConfig
from .game import GameController, board_to_piece_map, infer_legal_move


class EngineName(str, Enum):
    maia2 = "maia2"
    maia3 = "maia3"


class PlayerColor(str, Enum):
    white = "white"
    black = "black"


app = typer.Typer(help="Play Maia engines on a Chessnut Go board.")


async def _resolve_board(address: str | None, scan_timeout: float = 5.0) -> BoardDevice:
    devices = await ChessnutBoard.scan(timeout=scan_timeout)
    if address is None:
        if not devices:
            typer.echo("No Chessnut boards found.")
            raise typer.Exit(code=1)
        return devices[0]

    for device in devices:
        if device.address == address:
            return device

    return BoardDevice(name="Chessnut", address=address)


@app.command()
def scan(timeout: float = typer.Option(5.0, help="Bluetooth scan timeout in seconds.")) -> None:
    """Scan for nearby Chessnut boards."""

    async def _scan() -> None:
        devices = await ChessnutBoard.scan(timeout=timeout)
        if not devices:
            typer.echo("No Chessnut boards found.")
            return
        for device in devices:
            typer.echo(f"{device.name}\t{device.address}")

    asyncio.run(_scan())


@app.command()
def read(
    address: str | None = typer.Option(None, help="Board BLE address. If omitted, scan first."),
    timeout: float = typer.Option(10.0, help="Seconds to wait for a board notification."),
) -> None:
    """Read live board states from a Chessnut board."""

    async def _read() -> None:
        device = await _resolve_board(address, scan_timeout=5.0)
        state = await ChessnutBoard(device).read_once(timeout=timeout)
        typer.echo(state.render())

    asyncio.run(_read())


@app.command()
def watch(
    address: str | None = typer.Option(None, help="Board BLE address. If omitted, scan first."),
    scan_timeout: float = typer.Option(5.0, help="Bluetooth scan timeout in seconds."),
) -> None:
    """Keep the board connected and print each changed board state."""

    async def _watch() -> None:
        device = await _resolve_board(address, scan_timeout=scan_timeout)
        typer.echo(f"Connected to {device.name} {device.address}. Press Ctrl-C to stop.")
        controller = GameController()
        previous: dict[str, str] | None = None
        synchronized = False
        async for state in ChessnutBoard(device).watch():
            current = state.normalized()
            if current == previous:
                continue
            if previous is not None:
                typer.echo("")
                if synchronized:
                    try:
                        move = infer_legal_move(controller.board, state)
                        san = controller.board.san(move)
                        controller.board.push(move)
                        typer.echo(f"Move: {move.uci()} ({san})")
                    except ValueError as exc:
                        synchronized = False
                        typer.echo(f"Move: unknown ({exc})")
            typer.echo(state.render())
            if previous is None:
                synchronized = current == board_to_piece_map(controller.board)
                if not synchronized:
                    typer.echo("Move inference paused: set up the starting position first.")
            previous = current

    try:
        asyncio.run(_watch())
    except KeyboardInterrupt:
        typer.echo("\nDisconnected.")


@app.command()
def play(
    engine: EngineName = typer.Option(EngineName.maia3, help="Maia engine to play."),
    color: PlayerColor = typer.Option(PlayerColor.white, help="Human player color."),
    elo: int | None = typer.Option(None, help="Optional Maia2 UCI Elo setting."),
    movetime_ms: int = typer.Option(1000, help="Engine move time in milliseconds."),
) -> None:
    """Play a game against Maia on a Chessnut board."""

    config = EngineConfig.default(engine.value, elo=elo)
    typer.echo(f"Engine: {config.name} at {config.path}")
    typer.echo(f"Human color: {color.value}")
    typer.echo(f"Move time: {movetime_ms} ms")
    typer.echo("Playable board loop is not implemented yet.")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
