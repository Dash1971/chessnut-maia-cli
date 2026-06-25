# SPDX-License-Identifier: GPL-3.0-or-later

"""Command-line entry point."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import date
from enum import Enum
from pathlib import Path

import typer

from .board import BoardDevice, BoardState, ChessnutBoard
from .engine import EngineConfig, MaiaEngine
from .game import (
    GameController,
    board_from_piece_map,
    board_to_piece_map,
    infer_legal_move,
    infer_resilient_legal_move,
)


class EngineName(str, Enum):
    maia2 = "maia2"
    maia3 = "maia3"


class PlayerColor(str, Enum):
    white = "white"
    black = "black"


app = typer.Typer(help="Play Maia engines on a Chessnut Go board.")


PLAY_COMMANDS = "Type resync and press Enter to refresh board sync without changing the game."


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


def _prompt_white_to_move() -> bool:
    while True:
        value = typer.prompt("Whose move is it? [white/black]").strip().lower()
        if value in {"w", "white"}:
            return True
        if value in {"b", "black"}:
            return False
        typer.echo("Please enter white or black.")


def _resume_board_from_state(state: BoardState) -> "chess.Board":
    white_to_move = _prompt_white_to_move()
    return board_from_piece_map(state.normalized(), white_to_move=white_to_move)


def _pending_human_move_message(controller: GameController, color_name: str) -> str:
    if not controller.board.is_check():
        return f"{color_name} move: pending"

    import chess

    checkers = ", ".join(chess.square_name(square) for square in controller.board.checkers())
    return f"{color_name} move: pending (in check from {checkers}; move must answer check)"


def _terminal_bell() -> None:
    typer.echo("\a", nl=False)


async def _beep(board: ChessnutBoard) -> None:
    _terminal_bell()
    try:
        await board.beep()
        await asyncio.sleep(0.2)
    except Exception:
        pass


async def _announce_check(controller: GameController, board: ChessnutBoard) -> None:
    if not controller.board.is_check():
        return

    import chess

    checked_color = "White" if controller.board.turn == chess.WHITE else "Black"
    checkers = ", ".join(chess.square_name(square) for square in controller.board.checkers())
    await _beep(board)
    typer.echo(f"Check: {checked_color} king is in check from {checkers}.")


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
        typer.echo(PLAY_COMMANDS)

        maia = MaiaEngine(config)
        maia.start()
        command_queue: asyncio.Queue[str] = asyncio.Queue()
        terminal_reader_active = False

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
            await _announce_check(controller, board)
            await board.set_leds([maia_move.uci()[:2], maia_move.uci()[2:4]])
            return True

        def is_human_turn() -> bool:
            import chess

            return controller.board.turn == (chess.WHITE if human_is_white else chess.BLACK)

        def install_terminal_reader() -> None:
            nonlocal terminal_reader_active
            if terminal_reader_active or not sys.stdin.isatty():
                return

            def queue_terminal_line() -> None:
                line = sys.stdin.readline()
                if line:
                    command_queue.put_nowait(line.strip().lower())

            asyncio.get_running_loop().add_reader(sys.stdin.fileno(), queue_terminal_line)
            terminal_reader_active = True

        def remove_terminal_reader() -> None:
            nonlocal terminal_reader_active
            if terminal_reader_active:
                asyncio.get_running_loop().remove_reader(sys.stdin.fileno())
                terminal_reader_active = False

        async def handle_command(command: str) -> bool:
            nonlocal previous, synchronized, waiting_for_engine_move
            command_name = command.split()[0] if command else ""
            if command_name in {"", "help", "h", "?"}:
                typer.echo(PLAY_COMMANDS)
                return True
            if command_name != "resync":
                typer.echo("Unknown command.")
                typer.echo(PLAY_COMMANDS)
                return True

            typer.echo("")
            typer.echo("Resync requested. Keeping move list, side to move, and PGN intact.")
            previous = None
            waiting_for_engine_move = False
            try:
                await board.set_leds([])
                await board.initialize()
            except RuntimeError as exc:
                typer.echo(f"Resync failed: {exc}")
                return True
            typer.echo("Waiting for the next board update.")
            return True

        async def next_board_state(states: AsyncIterator[BoardState]) -> BoardState:
            return await states.__anext__()

        async def watch_with_commands() -> AsyncIterator[BoardState]:
            states = board.watch().__aiter__()
            state_task = asyncio.create_task(next_board_state(states))
            command_task = asyncio.create_task(command_queue.get())
            try:
                while True:
                    done, _pending = await asyncio.wait(
                        {state_task, command_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if command_task in done:
                        if not await handle_command(command_task.result()):
                            state_task.cancel()
                            break
                        command_task = asyncio.create_task(command_queue.get())
                        continue

                    state = state_task.result()
                    yield state
                    state_task = asyncio.create_task(next_board_state(states))
            finally:
                state_task.cancel()
                command_task.cancel()

        try:
            async for state in watch_with_commands():
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
                        install_terminal_reader()
                        if is_human_turn():
                            typer.echo(f"Ready for {human_color_name}'s move.")
                        else:
                            if await play_engine_move():
                                waiting_for_engine_move = True
                    else:
                        remove_terminal_reader()
                        if typer.confirm("Start from this physical board position?", default=True):
                            controller.board = _resume_board_from_state(state)
                            synchronized = True
                            expected = board_to_piece_map(controller.board)
                            current = expected
                            install_terminal_reader()
                            await _announce_check(controller, board)
                            if is_human_turn():
                                typer.echo(f"Ready for {human_color_name}'s move.")
                            else:
                                if await play_engine_move():
                                    waiting_for_engine_move = True
                        else:
                            typer.echo("Set up the starting position to begin.")
                            install_terminal_reader()
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
                    human_move = infer_resilient_legal_move(controller.board, state)
                except ValueError:
                    await _beep(board)
                    typer.echo(_pending_human_move_message(controller, human_color_name))
                    typer.echo(state.render())
                    previous = current
                    continue

                human_san = controller.board.san(human_move)
                controller.board.push(human_move)
                typer.echo(f"{human_color_name}: {human_move.uci()} ({human_san})")
                await _announce_check(controller, board)
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
            remove_terminal_reader()
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
