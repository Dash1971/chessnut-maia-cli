# SPDX-License-Identifier: GPL-3.0-or-later

"""Command-line entry point."""

from __future__ import annotations

import asyncio
from enum import Enum

import typer

from .board import ChessnutBoard
from .engine import EngineConfig


class EngineName(str, Enum):
    maia2 = "maia2"
    maia3 = "maia3"


class PlayerColor(str, Enum):
    white = "white"
    black = "black"


app = typer.Typer(help="Play Maia engines on a Chessnut Go board.")


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
def read() -> None:
    """Read live board states from a Chessnut board."""

    typer.echo("Board reading is not implemented yet.")
    raise typer.Exit(code=1)


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
