# Troubleshooting

## The Board Is Not Found

Run:

```bash
chessnut-maia scan
```

If no board appears:

- Turn the board off and on.
- Make sure it is not connected to another app.
- Move it close to the computer.
- On macOS, allow Bluetooth access for your terminal app.
- Try scanning again; BLE discovery can be intermittent.

You can also pass a known address:

```bash
chessnut-maia play --address <BLE address>
```

## macOS Bluetooth Permission

If macOS blocks Bluetooth access, open:

```text
System Settings -> Privacy & Security -> Bluetooth
```

Allow the terminal application you are using, such as Terminal, iTerm2, or VS
Code.

Restart the terminal after changing permission.

## The Engine Launcher Is Not Found

The defaults are:

```text
~/chess/maia2-engine/maia2-engine.sh
~/chess/maia3-engine/maia3-engine.sh
```

Check:

```bash
ls -l ~/chess/maia2-engine/maia2-engine.sh
ls -l ~/chess/maia3-engine/maia3-engine.sh
```

If your engine is elsewhere:

```bash
chessnut-maia play --engine maia2 --engine-path /path/to/maia2-engine.sh
```

## The Engine Starts But Does Not Respond

Test it directly:

```bash
printf 'uci\nisready\nquit\n' | ~/chess/maia2-engine/maia2-engine.sh
```

You should see:

```text
uciok
readyok
```

If not, fix the Maia install before using the Chessnut CLI.

## Maia Move: Pending

`Maia move: pending` means the internal game contains Maia's move, but the
physical board does not yet match that move.

Check the lit squares. Move Maia's piece physically from the lit source square
to the lit destination square.

If the board display still looks stale after you make the move:

```text
resync
```

## Human Move: Pending

`Human move: pending` means the physical board does not match any legal move
from the current internal position.

Common causes:

- A piece is still lifted.
- A capture was not completed.
- Maia's previous move was not made physically.
- The move is illegal.
- The board state is stale.

Fix the board position, or type:

```text
resync
```

## The Starting Position Is Wrong

If the back rank has swapped pieces, the CLI should not offer to resume from it.
It should wait for the normal starting position.

Fix the physical board and wait for another update. If nothing changes:

```text
resync
```

## Takeback Is Waiting

After `takeback`, the CLI lights the squares that differ between the current
physical board and the reverted internal board.

Restore those squares physically. Play resumes only when the full board matches
the reverted position.

## BookFile Errors

Make sure the path exists:

```bash
ls -lh /path/to/book.bin
```

The book must be a Polyglot `.bin` book. If the engine rejects it, verify that
your Maia wrapper supports the `BookFile` UCI option.

## PGN Looks Different After Takeback

Taken-back moves are kept as alternate PGN lines. New moves after the takeback
become the main line.

Example:

```pgn
1. d4 ( 1. e4 e5 ) 1... d5
```

Here `d4 d5` is the game continuation. `e4 e5` is the taken-back line.

## Ctrl-C And PGN Output

If you stop with `Ctrl-C`, the CLI prints the current PGN when at least one move
has been played.

If no PGN appears, the internal game had no moves yet.
