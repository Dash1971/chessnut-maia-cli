# chessnut-maia-cli

Play Maia2 or Maia3 on a Chessnut Go electronic chessboard from a small
terminal app.

The CLI connects to a Chessnut board over Bluetooth LE, watches the physical
pieces, infers your legal moves, asks a local Maia UCI engine for a reply, and
lights Maia's move on the board LEDs.

This project is early-stage, but the main play loop has been tested on a real
Chessnut Go board on macOS.

## What You Need

- macOS, Linux, or another platform that supports Python BLE through `bleak`
- Python 3.10 or newer
- A Chessnut Go or compatible Chessnut board
- A local Maia2 or Maia3 UCI launcher
- Optional: a Polyglot opening book

Default engine launcher paths:

```text
~/chess/maia2-engine/maia2-engine.sh
~/chess/maia3-engine/maia3-engine.sh
```

If your engine is somewhere else, pass `--engine-path`.

## Quick Start

Clone and install in a virtual environment:

```bash
git clone https://github.com/Dash1971/chessnut-maia-cli.git
cd chessnut-maia-cli
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Check that the command is available:

```bash
chessnut-maia --help
```

Scan for a board:

```bash
chessnut-maia scan
```

Read one board position:

```bash
chessnut-maia read
```

Watch live board updates:

```bash
chessnut-maia watch
```

Play as White:

```bash
chessnut-maia play --engine maia2 --color white
```

Play as Black:

```bash
chessnut-maia play --engine maia2 --color black
```

Choose color randomly:

```bash
chessnut-maia play --engine maia2 --color random
```

Use a Polyglot opening book:

```bash
chessnut-maia play \
  --engine maia2 \
  --color black \
  --elo 1500 \
  --book-file ~/chess/books/lichess_1500_all.bin
```

## Commands

```bash
chessnut-maia scan
chessnut-maia read
chessnut-maia watch
chessnut-maia play
```

Useful `play` options:

- `--engine maia2|maia3`
- `--color white|black|random`
- `--color w|b|r`
- `--elo 1500`
- `--book-file /path/to/book.bin`
- `--engine-path /path/to/engine-launcher.sh`
- `--movetime-ms 1000`
- `--engine-timeout-s 30` (default UCI response timeout)
- `--human-time / --no-human-time`
- `--temperature 0.5` (Maia3 only)
- `--top-p 0.9` (Maia3 only)
- `--address <BLE address>`

During `play`, terminal commands are also available:

- `resync` - clear LEDs and request a fresh board update without changing the game
- `takeback`, `tb`, or `undo` - roll back the last player/Maia turn
- `resign` - resign the game and print/save the PGN
- `help`, `h`, or `?` - print the command reminder

## Maia3 Sampling

Maia3 samples from a move policy rather than searching for a single best move.
The CLI can pass through the wrapper's Maia3-only sampling controls:

- `--temperature`: lower values reduce randomness; `0` chooses the highest-logit
  legal move.
- `--top-p`: nucleus sampling cutoff; `1.0` disables filtering.

The wrapper defaults are `Temperature=1.0` and `TopP=1.0`. To try a narrower
move distribution while keeping human-like Maia3 play:

```bash
chessnut-maia play \
  --engine maia3 \
  --elo 1600 \
  --temperature 0.5 \
  --top-p 0.9 \
  --color random
```

## Playing a Game

Set up the board in the normal starting position before launching `play`.

At startup, `play` queries the board battery and prints an estimated level, for
example `Board battery: 67%` or `Board battery: 67% charging`. If the board does
not answer the battery query, the game continues and reports the battery as
unavailable.

If you play White, the CLI waits for your first physical move. After you move,
Maia replies in the terminal and lights the source and destination squares. Move
Maia's piece physically on the board, then continue.

If you play Black, Maia moves first. The CLI lights Maia's first move; make that
move physically, then play Black's reply.

When the game ends or you stop with `Ctrl-C`, the CLI prints a PGN and saves it
under:

```text
~/Documents/EnCroissant/
```

Saved PGN filenames use:

```text
yyyymmdd_hhmm_whiteplayer_blackplayer.pgn
```

For example:

```text
20260627_1526_Human_maia2.pgn
```

PGN headers include the engine Elo when `--elo` is provided. The `Termination`
header uses the final board outcome when available, such as `White won by
checkmate`, `Black won by checkmate`, `Draw by stalemate`, or `Draw by
repetition`. If you type `resign`, the PGN result is recorded as a win for Maia
and the termination is `White resigned` or `Black resigned`.

`--movetime-ms` controls how long Maia is asked to think. `--engine-timeout-s`
controls how long the CLI waits for the local UCI process to answer before
giving up. The default engine response timeout is 30 seconds, so with
`--movetime-ms 1000` the practical wall-clock wait is about 31 seconds.

If Maia still does not answer before that timeout, the CLI ends the game
cleanly, prints and saves the PGN, and records `Engine timed out` instead of
crashing with a Python traceback. Increase this timeout if your local engine
occasionally needs longer in unusual late endgames:

```bash
chessnut-maia play --movetime-ms 1000 --engine-timeout-s 60
```

If an unexpected board, Bluetooth, or runtime error escapes after moves have
been recorded, the CLI now prints the partial PGN before exiting, even if the
normal save path cannot complete.

If the board connection drops while `play` is running, the CLI keeps the current
game and PGN in memory and prompts:

```text
Press r to rescan/reconnect to board, or q to quit
```

Choose `r` after the board is powered back on and physically set to the current
position. Choose `q` to end the session and print/save the partial PGN.

## Board Sync

Chessnut boards report the current piece placement. The CLI compares that full
physical position against the internal chess game.

If the board starts in the normal starting position, play begins immediately.

If the board starts in a different valid game position, the CLI can offer to
resume from the visible pieces. Because sensors cannot recover move clocks,
en-passant state, or historical castling rights, resumed games reconstruct those
details from what is visible.

Setup mistakes are not treated as resumable games. For example, if all pawns and
pieces are still present but the back rank has a swapped king/queen, king/rook,
or king/bishop, the CLI waits for the real starting position instead of accepting
the bad setup.

Transient lifted-piece states are expected while you move pieces. The CLI waits
until the board reports a complete legal position.

## Takebacks

Type `takeback`, `tb`, or `undo` during `play`.

The normal takeback removes Maia's last move plus your previous move. This fits
the common case where Maia replies quickly and you then decide your last move
was a mistake.

The CLI lights every square that differs between the current physical board and
the reverted internal position. Restore the lit squares physically. Play resumes
only after the board exactly matches the reverted position.

Taken-back moves are kept in the final PGN as alternate lines. The moves played
after the takeback become the main line. If you take back multiple times, older
taken-back branches are preserved as continued variations when they are still
legal inside the earlier branch. This lets the PGN keep deeper rejected lines
instead of losing them or blocking PGN export.

Example shape:

```pgn
1. d4 ( 1. e4 e5 ) 1... d5
```

Multiple-takeback example shape:

```pgn
15. Nb3 g5 ( 15... Ng6 16. Nc5 Bxc5 17. dxc5 Nf4 18. Bxf4 ) 16. Nc5
```

## Check And Illegal-Move Alerts

When either side gives check or checkmate, the CLI sounds the Chessnut board
buzzer and prints the checked king plus the checking square.

Complete-looking illegal human move attempts also beep. Temporary lifted-piece
positions should not beep.

## Maia Setup

This repository expects Maia to already be available as a UCI-compatible command
line engine.

Recommended companion projects:

- Maia2 local stack: `https://github.com/Dash1971/maia2-local-stack`
- Maia3 local stack: `https://github.com/Dash1971/maia3-local-stack`

After setup, verify that your launcher works:

```bash
printf 'uci\nisready\nquit\n' | ~/chess/maia2-engine/maia2-engine.sh
printf 'uci\nisready\nquit\n' | ~/chess/maia3-engine/maia3-engine.sh
```

More detail: [docs/maia-setup.md](docs/maia-setup.md).

## Troubleshooting

Common checks:

- If no board appears, make sure it is powered on, awake, and not connected to
  another app.
- If macOS asks for Bluetooth permission, allow it for your terminal app.
- If the engine fails to start, check `--engine-path` and run the launcher by
  hand with `uci` / `isready`.
- If Maia's move stays pending, make sure you physically made Maia's lit move.
- If the board setup is wrong, fix the pieces and wait for the next board update.
  Use `resync` if the display still looks stale.

More detail: [docs/troubleshooting.md](docs/troubleshooting.md).

## Future Plans

A future version may add a lightweight Python launcher GUI for macOS and Linux.
The launcher would keep this CLI as the game engine and provide a small
cross-platform control panel for starting games without typing long commands.

Planned launcher scope:

- choose Maia2 or Maia3
- set Elo, player color, opening book, and engine path
- expose Maia3 sampling options such as temperature and top-p
- toggle human-like timing
- preview the generated `chessnut-maia play` command
- start the CLI as a subprocess and show live status/output
- optionally send supported runtime commands such as `takeback`, `resync`,
  `resign`, and `quit`

The intended first milestone is a launcher and live log, not a separate digital
board UI. The Chessnut board remains the physical interface, and the existing
CLI remains responsible for Bluetooth, Maia, game state, LEDs, alerts, and PGN
output.

## Development

Install with dev dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run tests:

```bash
pytest -q
```

Run static checks:

```bash
ruff check .
```

## Tested So Far

- Chessnut Go board
- macOS with a local Maia2 launcher
- macOS with a local Maia3 launcher
- Human as White
- Human as Black
- Board LEDs for Maia moves
- Chessnut board buzzer for check and complete illegal attempts
- PGN output with takeback variations

## Known Limitations

- The app is still experimental.
- There is no packaged release yet; install from source.
- The board cannot report move history, clocks, en-passant rights, or historical
  castling rights. Resumed games reconstruct the best playable state from
  visible pieces.
- En Croissant one-click import is not implemented yet. PGNs are saved to disk,
  but opening them in En Croissant is still a manual step.

## Attribution

Chessnut Bluetooth protocol details are adapted from Roberto Marabini's GPL-3.0
Chessnut Air Python reference:

https://github.com/rmarabini/chessnutair

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
