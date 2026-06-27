# SPDX-License-Identifier: GPL-3.0-or-later

"""Command-line entry point."""

from __future__ import annotations

import asyncio
import random
import shlex
import sys
from collections.abc import AsyncIterator
from datetime import date, datetime
from enum import Enum
from pathlib import Path

import typer

from .board import BoardDevice, BoardState, ChessnutBoard
from .engine import EngineConfig, MaiaEngine
from .game import (
    GameController,
    board_from_piece_map,
    board_to_piece_map,
    changed_squares,
    infer_legal_move,
    infer_resilient_legal_move,
    is_resumable_piece_map,
)


class EngineName(str, Enum):
    maia2 = "maia2"
    maia3 = "maia3"


class PlayerColor(str, Enum):
    white = "white"
    black = "black"
    random = "random"


app = typer.Typer(help="Play Maia engines on a Chessnut Go board.")


PLAY_COMMANDS = (
    "Type resync to refresh board sync, or takeback/tb/undo to undo the last Maia/player turn."
)
DEFAULT_PGN_DIR = Path("~/Documents/EnCroissant")


def _parse_player_color(value: str) -> PlayerColor:
    normalized = value.strip().lower()
    aliases = {
        "w": PlayerColor.white,
        "white": PlayerColor.white,
        "b": PlayerColor.black,
        "black": PlayerColor.black,
        "r": PlayerColor.random,
        "random": PlayerColor.random,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise typer.BadParameter("Choose white, black, random, w, b, or r.") from exc


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
    white_elo: int | None = None,
    black_elo: int | None = None,
    result: str | None = None,
    termination: str | None = None,
) -> str:
    import chess.pgn

    board = controller.board
    final_result = result or (
        board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else "*"
    )
    game = _pgn_game_from_controller(controller)
    game.headers["Event"] = "Chessnut Maia CLI game"
    game.headers["Site"] = "Chessnut Go / local engine"
    game.headers["Date"] = date.today().strftime("%Y.%m.%d")
    if "Round" in game.headers:
        del game.headers["Round"]
    game.headers["White"] = white
    game.headers["Black"] = black
    if white_elo is not None:
        game.headers["WhiteElo"] = str(white_elo)
    if black_elo is not None:
        game.headers["BlackElo"] = str(black_elo)
    game.headers["Result"] = final_result
    final_termination = termination or _termination_from_board(board)
    if final_termination is not None:
        game.headers["Termination"] = final_termination
    return str(game)


def _termination_from_board(board: "chess.Board") -> str | None:
    import chess

    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return None

    if outcome.termination == chess.Termination.CHECKMATE:
        winner = "White" if outcome.winner == chess.WHITE else "Black"
        return f"{winner} won by checkmate"

    draw_terminations = {
        chess.Termination.STALEMATE: "Draw by stalemate",
        chess.Termination.INSUFFICIENT_MATERIAL: "Draw by insufficient material",
        chess.Termination.SEVENTYFIVE_MOVES: "Draw by seventy-five-move rule",
        chess.Termination.FIVEFOLD_REPETITION: "Draw by fivefold repetition",
        chess.Termination.FIFTY_MOVES: "Draw by fifty-move rule",
        chess.Termination.THREEFOLD_REPETITION: "Draw by repetition",
    }
    return draw_terminations.get(outcome.termination, f"Game ended by {outcome.termination.name}")


def _pgn_game_from_controller(controller: GameController) -> "chess.pgn.Game":
    import chess.pgn

    game = chess.pgn.Game.from_board(controller.board)
    for variation in controller.takeback_variations:
        base_node = _pgn_node_at_ply(game, variation.base_ply)
        if base_node is None:
            continue
        node = base_node
        for move in variation.moves:
            node = node.add_variation(move)
    return game


def _pgn_node_at_ply(game: "chess.pgn.Game", ply: int) -> "chess.pgn.GameNode | None":
    node = game
    for _ in range(ply):
        if not node.variations:
            return None
        node = node.variations[0]
    return node


def _print_pgn(
    controller: GameController,
    *,
    white: str,
    black: str,
    white_elo: int | None = None,
    black_elo: int | None = None,
    result: str | None = None,
    termination: str | None = None,
) -> None:
    pgn = _format_pgn(
        controller,
        white=white,
        black=black,
        white_elo=white_elo,
        black_elo=black_elo,
        result=result,
        termination=termination,
    )
    typer.echo("")
    typer.echo("PGN:")
    typer.echo(pgn)
    try:
        pgn_path = _save_pgn(pgn, white=white, black=black)
    except OSError as exc:
        typer.echo(f"Could not save PGN: {exc}")
        return
    typer.echo("")
    typer.echo(f"PGN saved: {pgn_path}")
    typer.echo(f"Open in En Croissant: open -a \"En Croissant\" {shlex.quote(str(pgn_path))}")


def _save_pgn(
    pgn: str,
    *,
    white: str,
    black: str,
    directory: Path = DEFAULT_PGN_DIR,
) -> Path:
    pgn_dir = directory.expanduser()
    pgn_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{timestamp}_{_filename_token(white)}_{_filename_token(black)}.pgn"
    path = _unique_path(pgn_dir / filename)
    path.write_text(pgn + "\n", encoding="utf-8")
    return path


def _filename_token(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "unknown"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise OSError(f"Could not find available filename for {path}")


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


async def _beep(board: ChessnutBoard) -> None:
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
    if controller.board.is_checkmate():
        typer.echo(f"Checkmate: {checked_color} king is mated by {checkers}.")
    else:
        typer.echo(f"Check: {checked_color} king is in check from {checkers}.")


def _looks_like_complete_move_attempt(controller: GameController, state: BoardState) -> bool:
    import chess

    moving_color = controller.board.turn
    before = board_to_piece_map(controller.board)
    after = state.normalized()

    def is_moving_piece(piece: str | None) -> bool:
        if piece is None:
            return False
        return piece.isupper() if moving_color == chess.WHITE else piece.islower()

    removed_or_changed = [
        square
        for square, piece in before.items()
        if is_moving_piece(piece) and after.get(square) != piece
    ]
    added_or_changed = [
        square
        for square, piece in after.items()
        if is_moving_piece(piece) and before.get(square) != piece
    ]
    return bool(removed_or_changed and added_or_changed)


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
    color: str = typer.Option(
        "white",
        help="Human player color: white, black, random, w, b, or r.",
    ),
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
    player_color = _parse_player_color(color)
    if player_color == PlayerColor.random:
        player_color = random.choice([PlayerColor.white, PlayerColor.black])
    human_is_white = player_color == PlayerColor.white
    human_color_name = "White" if human_is_white else "Black"
    engine_color_name = "Black" if human_is_white else "White"
    pgn_white = "Human" if human_is_white else config.name
    pgn_black = config.name if human_is_white else "Human"
    pgn_white_elo = None if human_is_white else config.elo
    pgn_black_elo = config.elo if human_is_white else None

    controller: GameController | None = None

    async def _play() -> None:
        nonlocal controller
        device = await _resolve_board(address, scan_timeout=scan_timeout)
        board = ChessnutBoard(device)
        controller = GameController()
        synchronized = False
        waiting_for_engine_move = False
        takeback_restore_active = False
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

        async def finish_game(result: str, termination: str | None = None) -> None:
            await board.set_leds([])
            typer.echo(f"Game over: {result}")
            _print_pgn(
                controller,
                white=pgn_white,
                black=pgn_black,
                white_elo=pgn_white_elo,
                black_elo=pgn_black_elo,
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
            nonlocal previous, synchronized, waiting_for_engine_move, takeback_restore_active
            command_name = command.split()[0] if command else ""
            if command_name in {"", "help", "h", "?"}:
                typer.echo(PLAY_COMMANDS)
                return True
            if command_name in {"takeback", "tb", "undo"}:
                if not synchronized:
                    typer.echo("Cannot take back until the physical board is synchronized.")
                    return True
                try:
                    popped_moves = controller.takeback_last_turn()
                except ValueError as exc:
                    typer.echo(str(exc))
                    return True

                waiting_for_engine_move = False
                takeback_restore_active = True
                target = board_to_piece_map(controller.board)
                current = previous or {}
                restore_squares = changed_squares(current, target)
                await board.set_leds(restore_squares)
                moves = ", ".join(move.uci() for move in popped_moves)
                typer.echo("")
                typer.echo(f"Takeback: {moves}")
                if restore_squares:
                    typer.echo("Restore the lit squares to the previous position.")
                else:
                    typer.echo("Physical board already matches the takeback position.")
                    takeback_restore_active = False
                    if is_human_turn():
                        typer.echo(f"Ready for {human_color_name}'s move.")
                    else:
                        if await play_engine_move():
                            waiting_for_engine_move = True
                if takeback_restore_active:
                    await board.initialize()
                return True
            if command_name != "resync":
                typer.echo("Unknown command.")
                typer.echo(PLAY_COMMANDS)
                return True

            typer.echo("")
            typer.echo("Resync requested. Keeping move list, side to move, and PGN intact.")
            previous = None
            waiting_for_engine_move = False
            takeback_restore_active = False
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
                if takeback_restore_active:
                    typer.echo(state.render())
                    if current == expected:
                        await board.set_leds([])
                        takeback_restore_active = False
                        typer.echo("Takeback complete.")
                        if is_human_turn():
                            typer.echo(f"Ready for {human_color_name}'s move.")
                        else:
                            if await play_engine_move():
                                waiting_for_engine_move = True
                    else:
                        await board.set_leds(changed_squares(current, expected))
                        typer.echo("Takeback: restore the lit squares.")
                    previous = current
                    continue

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
                        if not is_resumable_piece_map(current):
                            typer.echo("Set up the starting position to begin.")
                            install_terminal_reader()
                        elif typer.confirm(
                            "Start from this physical board position?",
                            default=True,
                        ):
                            try:
                                controller.board = _resume_board_from_state(state)
                            except ValueError as exc:
                                typer.echo(f"Cannot start from this position: {exc}")
                                typer.echo(
                                    "Fix the physical board, then use resync "
                                    "or wait for the next update."
                                )
                                install_terminal_reader()
                                previous = current
                                continue
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
                            await finish_game(result)
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
                    if _looks_like_complete_move_attempt(controller, state):
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
                    await finish_game(result)
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
                white_elo=pgn_white_elo,
                black_elo=pgn_black_elo,
                result="*",
                termination="Interrupted by user",
            )


if __name__ == "__main__":
    app()
