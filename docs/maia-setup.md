# Maia Setup

`chessnut-maia-cli` does not install Maia itself. It launches a local Maia
engine through the UCI protocol.

The default paths are:

```text
~/chess/maia2-engine/maia2-engine.sh
~/chess/maia3-engine/maia3-engine.sh
```

You can use different paths with `--engine-path`.

## Recommended Local Stacks

Use one of these companion repositories to build a local engine launcher:

- Maia2 local stack: `https://github.com/Dash1971/maia2-local-stack`
- Maia3 local stack: `https://github.com/Dash1971/maia3-local-stack`

Follow the setup instructions in the companion repo first. Then return here and
test the engine launcher.

## Verify Maia2

```bash
test -x ~/chess/maia2-engine/maia2-engine.sh
printf 'uci\nisready\nquit\n' | ~/chess/maia2-engine/maia2-engine.sh
```

Expected result:

- UCI engine identification lines
- `uciok`
- `readyok`

Then run:

```bash
chessnut-maia play --engine maia2 --color white
```

## Verify Maia3

```bash
test -x ~/chess/maia3-engine/maia3-engine.sh
printf 'uci\nisready\nquit\n' | ~/chess/maia3-engine/maia3-engine.sh
```

Expected result:

- UCI engine identification lines
- `uciok`
- `readyok`

Then run:

```bash
chessnut-maia play --engine maia3 --color white
```

## Custom Engine Path

If your launcher is somewhere else:

```bash
chessnut-maia play \
  --engine maia2 \
  --engine-path /absolute/path/to/maia2-engine.sh \
  --color white
```

The launcher must behave like a normal UCI engine on stdin/stdout.

## Elo

Maia2 and Maia3 expose rating options with slightly different option names
internally. The CLI handles that difference for you.

```bash
chessnut-maia play --engine maia2 --elo 1500 --color white
chessnut-maia play --engine maia3 --elo 1500 --color white
```

## Opening Books

Opening books are optional. When supplied, the file must be a Polyglot `.bin`
book supported by the Maia wrapper.

```bash
chessnut-maia play \
  --engine maia2 \
  --book-file ~/chess/books/lichess_1500_all.bin \
  --color black
```

If the engine rejects the book option, first verify that the same launcher
accepts `setoption name BookFile value /path/to/book.bin` in a direct UCI smoke
test.

## HumanTime

Some Maia wrappers expose a `HumanTime` option. The CLI can pass it through:

```bash
chessnut-maia play --engine maia2 --human-time
chessnut-maia play --engine maia2 --no-human-time
```

If your wrapper does not support `HumanTime`, leave the option unset.
