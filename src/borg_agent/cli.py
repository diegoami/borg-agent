"""The command line: build the pinned game, play it, and check determinism."""
import argparse
import json
import shutil
import time
from pathlib import Path

from . import build as build_module
from . import play as play_module

RUNS = build_module.pins.ROOT / 'runs'


def run_dir(name):
    path = RUNS / name
    if path.exists():
        shutil.rmtree(path)
    return path


def cmd_build(args):
    out = build_module.prepare(args.output, force=args.force)
    print(build_module.binary(out))
    return 0


def cmd_play(args):
    out = build_module.prepare()
    output = Path(args.output) if args.output else run_dir(f'seed{args.seed}-cap{args.cap}-{time.time_ns()}')
    record = play_module.play(out, args.seed, args.cap, output,
                              timeout=args.timeout, stall_timeout=args.stall_timeout,
                              checkpoint_saves=args.checkpoint_saves, lock=not args.no_lock)
    print(output)
    return 0 if record['outcome'] in play_module.GOOD_OUTCOMES else 1


def cmd_determinism(args):
    """T01's gate: two runs of one seed must give byte-identical traces."""
    out = build_module.prepare()
    base = Path(args.output) if args.output else run_dir(f'determinism-seed{args.seed}-cap{args.cap}')
    traces, records = [], []
    for attempt in (1, 2):
        record = play_module.play(out, args.seed, args.cap, base / f'run{attempt}',
                                  timeout=args.timeout, stall_timeout=args.stall_timeout,
                                  checkpoint_saves=False, lock=not args.no_lock)
        records.append(record)
        traces.append((base / f'run{attempt}/trace.txt').read_bytes())
    identical = traces[0] == traces[1] and bool(traces[0])
    verdict = {
        'seed': args.seed, 'turn_cap': args.cap,
        'build_key': records[0]['build_key'],
        'outcomes': [r['outcome'] for r in records],
        'trace_sha256': [r.get('trace_sha256') for r in records],
        'trace_bytes': [len(t) for t in traces],
        'identical': identical,
    }
    if not identical:
        left, right = (t.decode(errors='replace').splitlines() for t in traces)
        verdict['first_difference'] = next(
            ({'line': i + 1, 'run1': a, 'run2': b}
             for i, (a, b) in enumerate(zip(left, right)) if a != b),
            {'line': min(len(left), len(right)) + 1, 'run1': None, 'run2': None})
    (base / 'determinism.json').write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
    print(json.dumps(verdict, indent=2, sort_keys=True))
    print(base)
    ok = identical and all(r['outcome'] in play_module.GOOD_OUTCOMES for r in records)
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog='borg-agent', description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    builder = sub.add_parser('build', help='build the pinned instrumented game (cached by recipe)')
    builder.add_argument('--output', type=Path, help='build directory; default build/<recipe hash>')
    builder.add_argument('--force', action='store_true', help='rebuild even if the cached build matches')
    builder.set_defaults(func=cmd_build)

    for name, handler, help_text in (('play', cmd_play, 'play one game with the stock Borg'),
                                     ('determinism', cmd_determinism, 'play one seed twice and compare traces')):
        p = sub.add_parser(name, help=help_text)
        p.add_argument('--seed', type=int, required=True)
        p.add_argument('--cap', type=int, required=True, help='game-turn cap (10 game turns is one player turn)')
        p.add_argument('--output', type=Path)
        p.add_argument('--timeout', type=int, default=900)
        p.add_argument('--stall-timeout', type=int, default=60)
        p.add_argument('--no-lock', action='store_true', help='skip /tmp/angband-validation.lock')
        if name == 'play':
            p.add_argument('--checkpoint-saves', action='store_true',
                           help='write the runner\'s periodic saves (off by default)')
        p.set_defaults(func=handler)

    args = parser.parse_args(argv)
    if args.command in ('play', 'determinism') and (not 0 <= args.seed <= 0xffffffff or args.cap < 2):
        parser.error('seed must be a uint32 and cap at least 2')
    return args.func(args)
