# chessnut-maia-cli

CLI bridge for playing Maia2 and Maia3 on a Chessnut Go electronic board over
Bluetooth LE.

This project is early-stage. The first target is a small macOS-friendly command
line app that can:

- connect to a Chessnut Go board over Bluetooth LE,
- read the physical board position,
- infer the human move,
- send the current position to a local Maia2 or Maia3 UCI engine,
- show the bot move in the terminal and on the board LEDs.

## Planned commands

```bash
chessnut-maia scan
chessnut-maia read
chessnut-maia watch
chessnut-maia play --engine maia2 --elo 1500 --book-file ~/chess/books/lichess_1600_all.bin --color white
chessnut-maia play --engine maia2 --elo 1500 --book-file ~/chess/books/lichess_1600_all.bin --color black
chessnut-maia play --engine maia3 --color white
```

## Expected local engine paths

The default engine paths follow the Maia local-stack guides:

```text
~/chess/maia2-engine/maia2-engine.sh
~/chess/maia3-engine/maia3-engine.sh
```

Both engines are treated as UCI-compatible command-line engines. Custom paths
will be supported through CLI options.

## Development status

Current focus:

1. package skeleton,
2. legal move inference from observed board states,
3. UCI engine launching,
4. Chessnut Go Bluetooth scanning and board-state decoding,
5. playable human-vs-Maia loop.

Validated on a physical Chessnut Go:

- Bluetooth scanning,
- one-shot board reads,
- persistent board-state watching,
- transient lifted-piece handling,
- legal move inference from physical moves.

The first `play` loop is experimental, with support for human-as-White and
human-as-Black. When playing as Black, Maia moves first, lights the move on the
board, and waits for the player to make Maia's move physically before accepting
Black's reply.

For Maia2 book play, pass a Polyglot book with `--book-file`. The CLI forwards
that path to the Maia wrapper's `BookFile` UCI option.

## Attribution

Chessnut Bluetooth protocol details are adapted from Roberto Marabini's GPL-3.0
Chessnut Air Python reference:

https://github.com/rmarabini/chessnutair

## Install for development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## License

GPL-3.0-or-later. See `LICENSE`.
