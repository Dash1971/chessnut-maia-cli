# SPDX-License-Identifier: GPL-3.0-or-later

"""Command-line entry point."""

from __future__ import annotations

import asyncio
from enum import Enum
from pathlib import Path

import typer

from .board import BoardDevice, ChessnutBoard
from .engine import EngineConfig, MaiaEngine
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
                    except ValueError:
                        typer.echo("Move: pending")
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
    engine_path: Path | None = typer.Option(None, help="Custom UCI engine launcher path."),
    address: str | None = typer.Option(None, help="Board BLE address. If omitted, scan first."),
    scan_timeout: float = typer.Option(5.0, help="Bluetooth scan timeout in seconds."),
) -> None:
    """Play a game against Maia on a Chessnut board."""

    config = EngineConfig.default(engine.value, elo=elo)
    if engine_path is not None:
        config = EngineConfig(config.name, engine_path.expanduser(), config.elo)
    if color != PlayerColor.white:
        typer.echo("Only human-as-white play is implemented so far.")
        raise typer.Exit(code=1)

    async def _play() -> None:
        device = await _resolve_board(address, scan_timeout=scan_timeout)
        board = ChessnutBoard(device)
        controller = GameController()
        synchronized = False
        waiting_for_engine_move = False
        previous: dict[str, str] | None = None

        typer.echo(f"Connected to {device.name} {device.address}. Press Ctrl-C to stop.")
        typer.echo(f"Engine: {config.name} at {config.path}")
        typer.echo(f"Move time: {movetime_ms} ms")

        maia = MaiaEngine(config)
        maia.start()
        try:
            async for state in board.watch():
                current = state.normalized()
                if current == previous:
                    continue
                if previous is not None:
                    typer.echo("")

                expected = board_to_piece_map(controller.board)
                if not synchronized:
                    synchronized = current == expected
                    typer.echo(state.render())
                    if synchronized:
                        typer.echo("Ready for White's move.")
                    else:
                        typer.echo("Set up the starting position to begin.")
                    previous = current
                    continue

                if current == expected:
                    typer.echo(state.render())
                    if waiting_for_engine_move:
                        await board.set_leds([])
                        waiting_for_engine_move = False
                        typer.echo("Ready for White's move.")
                    previous = current
                    continue

                if waiting_for_engine_move:
                    typer.echo("Maia move: pending")
                    typer.echo(state.render())
                    previous = current
                    continue

                try:
                    human_move = infer_legal_move(controller.board, state)
                except ValueError:
                    typer.echo("White move: pending")
                    typer.echo(state.render())
                    previous = current
                    continue

                human_san = controller.board.san(human_move)
                controller.board.push(human_move)
                typer.echo(f"White: {human_move.uci()} ({human_san})")
                typer.echo(state.render())

                if controller.board.is_game_over(claim_draw=True):
                    await board.set_leds([])
                    typer.echo(f"Game over: {controller.board.result(claim_draw=True)}")
                    previous = current
                    break

                maia_move = maia.play(controller.board, movetime_ms=movetime_ms)
                if maia_move is None or maia_move.uci() == "0000":
                    await board.set_leds([])
                    typer.echo(f"Game over: {controller.board.result(claim_draw=True)}")
                    previous = current
                    break

                maia_san = controller.board.san(maia_move)
                controller.board.push(maia_move)
                typer.echo(f"Maia: {maia_move.uci()} ({maia_san})")
                await board.set_leds([maia_move.uci()[:2], maia_move.uci()[2:4]])
                waiting_for_engine_move = True
                previous = current
        finally:
            maia.quit()

    try:
        asyncio.run(_play())
    except KeyboardInterrupt:
        typer.echo("\nDisconnected.")


if __name__ == "__main__":
    app()
