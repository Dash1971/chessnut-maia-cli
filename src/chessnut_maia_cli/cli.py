# SPDX-License-Identifier: GPL-3.0-or-later

"""Command-line entry point."""

from __future__ import annotations

import asyncio
from datetime import date
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


def _format_pgn(
    controller: GameController,
    *,
    white: str,
    black: str,
    result: str | None = None,
    termination: str | None = None,
) -> str:
    import chess.pgn

    board = controller.board
    final_result = result or (
        board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else "*"
    )
    game = chess.pgn.Game.from_board(board)
    game.headers["Event"] = "Chessnut Maia CLI game"
    game.headers["Site"] = "Chessnut Go / local engine"
    game.headers["Date"] = date.today().strftime("%Y.%m.%d")
    game.headers["Round"] = "-"
    game.headers["White"] = white
    game.headers["Black"] = black
    game.headers["Result"] = final_result
    if termination is not None:
        game.headers["Termination"] = termination
    return str(game)


def _print_pgn(
    controller: GameController,
    *,
    white: str,
    black: str,
    result: str | None = None,
    termination: str | None = None,
) -> None:
    typer.echo("")
    typer.echo("PGN:")
    typer.echo(
        _format_pgn(
            controller,
            white=white,
            black=black,
            result=result,
            termination=termination,
        )
    )


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
    engine: EngineName = typer.Option(EngineName.maia2, help="Maia engine to play."),
    color: PlayerColor = typer.Option(PlayerColor.white, help="Human player color."),
    elo: int | None = typer.Option(None, help="Optional Maia UCI Elo setting."),
    book_file: Path | None = typer.Option(None, help="Optional Polyglot opening book path."),
    human_time: bool = typer.Option(False, help="Enable the engine wrapper's HumanTime option."),
    movetime_ms: int = typer.Option(1000, help="Engine move time in milliseconds."),
    engine_path: Path | None = typer.Option(None, help="Custom UCI engine launcher path."),
    address: str | None = typer.Option(None, help="Board BLE address. If omitted, scan first."),
    scan_timeout: float = typer.Option(5.0, help="Bluetooth scan timeout in seconds."),
) -> None:
    """Play a game against Maia on a Chessnut board."""

    config = EngineConfig.default(
        engine.value,
        elo=elo,
        book_file=book_file,
        human_time=human_time,
    )
    if engine_path is not None:
        config = EngineConfig(
            config.name,
            engine_path.expanduser(),
            config.elo,
            config.book_file,
            config.human_time,
        )
    human_is_white = color == PlayerColor.white
    human_color_name = "White" if human_is_white else "Black"
    engine_color_name = "Black" if human_is_white else "White"
    pgn_white = "Human" if human_is_white else config.name
    pgn_black = config.name if human_is_white else "Human"

    controller: GameController | None = None

    async def _play() -> None:
        nonlocal controller
        device = await _resolve_board(address, scan_timeout=scan_timeout)
        board = ChessnutBoard(device)
        controller = GameController()
        synchronized = False
        waiting_for_engine_move = False
        previous: dict[str, str] | None = None

        typer.echo(f"Connected to {device.name} {device.address}. Press Ctrl-C to stop.")
        typer.echo(f"Engine: {config.name} at {config.path}")
        if config.book_file is not None:
            typer.echo(f"Book: {config.book_file}")
        typer.echo(f"Human: {human_color_name}")
        typer.echo(f"Move time: {movetime_ms} ms")

        maia = MaiaEngine(config)
        maia.start()

        async def finish_game(result: str, termination: str) -> None:
            await board.set_leds([])
            typer.echo(f"Game over: {result}")
            _print_pgn(
                controller,
                white=pgn_white,
                black=pgn_black,
                result=result,
                termination=termination,
            )

        async def play_engine_move() -> bool:
            maia_move = maia.play(controller.board, movetime_ms=movetime_ms)
            if maia_move is None or maia_move.uci() == "0000":
                result = controller.board.result(claim_draw=True)
                await finish_game(result, "No legal engine move")
                return False

            maia_san = controller.board.san(maia_move)
            controller.board.push(maia_move)
            typer.echo(f"{engine_color_name}: {maia_move.uci()} ({maia_san})")
            await board.set_leds([maia_move.uci()[:2], maia_move.uci()[2:4]])
            return True

        def is_human_turn() -> bool:
            import chess

            return controller.board.turn == (chess.WHITE if human_is_white else chess.BLACK)

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
                        if is_human_turn():
                            typer.echo(f"Ready for {human_color_name}'s move.")
                        else:
                            if await play_engine_move():
                                waiting_for_engine_move = True
                    else:
                        typer.echo("Set up the starting position to begin.")
                    previous = current
                    continue

                if current == expected:
                    typer.echo(state.render())
                    if waiting_for_engine_move:
                        await board.set_leds([])
                        waiting_for_engine_move = False
                        if controller.board.is_game_over(claim_draw=True):
                            result = controller.board.result(claim_draw=True)
                            await finish_game(result, "Game over")
                            break
                        if is_human_turn():
                            typer.echo(f"Ready for {human_color_name}'s move.")
                        else:
                            if await play_engine_move():
                                waiting_for_engine_move = True
                    previous = current
                    continue

                if waiting_for_engine_move:
                    typer.echo("Maia move: pending")
                    typer.echo(state.render())
                    previous = current
                    continue

                if not is_human_turn():
                    typer.echo("Maia move: pending")
                    typer.echo(state.render())
                    previous = current
                    continue

                try:
                    human_move = infer_legal_move(controller.board, state)
                except ValueError:
                    typer.echo(f"{human_color_name} move: pending")
                    typer.echo(state.render())
                    previous = current
                    continue

                human_san = controller.board.san(human_move)
                controller.board.push(human_move)
                typer.echo(f"{human_color_name}: {human_move.uci()} ({human_san})")
                typer.echo(state.render())

                if controller.board.is_game_over(claim_draw=True):
                    result = controller.board.result(claim_draw=True)
                    await finish_game(result, "Game over")
                    previous = current
                    break

                if await play_engine_move():
                    waiting_for_engine_move = True
                else:
                    previous = current
                    break
                previous = current
        finally:
            maia.quit()

    try:
        asyncio.run(_play())
    except KeyboardInterrupt:
        typer.echo("\nDisconnected.")
        if controller is not None and controller.board.move_stack:
            _print_pgn(
                controller,
                white=pgn_white,
                black=pgn_black,
                result="*",
                termination="Interrupted by user",
            )


if __name__ == "__main__":
    app()
