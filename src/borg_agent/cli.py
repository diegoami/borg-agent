"""The command line: build the pinned game, play it with a mind, and work on the
runs it leaves - record, verify, branch, view, dump and explain (R5).
"""
import argparse
import json
import shutil
import time
from pathlib import Path

from . import agent as agent_module
from . import build as build_module
from . import mind as mind_module
from . import play as play_module
from . import record as record_module
from . import replay as replay_module

MINDS = {'scripted': mind_module.ScriptedMind}

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


def cmd_agent(args):
    """Play with a mind through the bridge (T03)."""
    out = build_module.prepare()
    output = Path(args.output) if args.output else run_dir(
        f'agent-{args.mind}-seed{args.seed}-cap{args.cap}-{time.time_ns()}')
    record = agent_module.play_with_mind(
        out, args.seed, args.cap, output, MINDS[args.mind](),
        timeout=args.timeout, stall_timeout=args.stall_timeout,
        decision_cap=args.decision_cap, validate=not args.no_validate,
        lock=not args.no_lock)
    print(output)
    return 0 if record['outcome'] in play_module.GOOD_OUTCOMES else 1


def cmd_agent_determinism(args):
    """T03's gate: two runs with the same mind must record the same actions."""
    out = build_module.prepare()
    base = Path(args.output) if args.output else run_dir(
        f'agent-determinism-{args.mind}-seed{args.seed}-cap{args.cap}')
    records, streams, traces = [], [], []
    for attempt in (1, 2):
        record = agent_module.play_with_mind(
            out, args.seed, args.cap, base / f'run{attempt}', MINDS[args.mind](),
            timeout=args.timeout, stall_timeout=args.stall_timeout,
            decision_cap=args.decision_cap, validate=not args.no_validate,
            lock=not args.no_lock)
        records.append(record)
        streams.append((base / f'run{attempt}' / agent_module.ACTION_LOG).read_bytes())
        traces.append((base / f'run{attempt}/trace.txt').read_bytes())
    identical = bool(streams[0]) and streams[0] == streams[1] and traces[0] == traces[1]
    verdict = {
        'mind': args.mind, 'seed': args.seed, 'turn_cap': args.cap,
        'build_key': records[0]['build_key'],
        'outcomes': [r['outcome'] for r in records],
        'decisions': [r['decisions'] for r in records],
        'final_turn': [r.get('final_turn') for r in records],
        'action_stream_sha256': [r.get('action_stream', {}).get('sha256') for r in records],
        'trace_sha256': [r.get('trace_sha256') for r in records],
        'identical': identical,
    }
    if not identical:
        left, right = (s.decode(errors='replace').splitlines() for s in streams)
        verdict['first_difference'] = next(
            ({'line': i + 1, 'run1': a, 'run2': b}
             for i, (a, b) in enumerate(zip(left, right)) if a != b),
            {'line': min(len(left), len(right)) + 1})
    (base / 'determinism.json').write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
    print(json.dumps(verdict, indent=2, sort_keys=True))
    print(base)
    ok = identical and all(r['outcome'] in play_module.GOOD_OUTCOMES for r in records)
    return 0 if ok else 1


def cmd_record(args):
    """Write the run record of a finished run (R5)."""
    path = record_module.write_record(args.run, mode=args.mode, intervention=args.intervention)
    print(path)
    return 0


def cmd_verify(args):
    """Replay a run without its mind and confirm it reproduces (R5)."""
    output = Path(args.output) if args.output else run_dir(f'verify-{Path(args.run).name}')
    verdict = replay_module.verify(args.run, output, timeout=args.timeout,
                                  stall_timeout=args.stall_timeout, lock=not args.no_lock)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0 if verdict['verified'] else 1


def cmd_branch(args):
    """Replay to a turn, then play on with another mind (R5, mode B)."""
    output = Path(args.output) if args.output else run_dir(
        f'branch-{Path(args.run).name}-turn{args.turn}-{args.mind}')
    result, parent = replay_module.branch(
        args.run, args.turn, output, MINDS[args.mind](), timeout=args.timeout,
        stall_timeout=args.stall_timeout, lock=not args.no_lock)
    record_module.write_record(output, mode='post_mortem', parent=parent)
    print(output)
    return 0 if result['outcome'] in play_module.GOOD_OUTCOMES else 1


def cmd_view(args):
    """Show the screen at a turn (R5)."""
    index, observation, screen = replay_module.view(args.run, args.turn)
    print(f'decision {observation["decision"]} at turn {observation["turn"]} '
          f'(observation {index})')
    print(screen)
    return 0


def cmd_dump(args):
    """Write the observation at a turn (R5)."""
    _index, observation = replay_module.dump(args.run, args.turn)
    text = json.dumps(observation, indent=2, sort_keys=True) + '\n'
    if args.output:
        Path(args.output).write_text(text)
        print(args.output)
    else:
        print(text, end='')
    return 0


def cmd_explain(args):
    """Show what was decided around a turn, and why (R5)."""
    for line in replay_module.explain(args.run, args.turn, window=args.window):
        mark = '>' if line.pop('current') else ' '
        print(mark, json.dumps(line, sort_keys=True))
    return 0


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

    for name, handler, help_text in (
            ('agent', cmd_agent, 'play with a mind through the bridge'),
            ('agent-determinism', cmd_agent_determinism,
             'play one seed twice with the same mind and compare the action streams')):
        p = sub.add_parser(name, help=help_text)
        p.add_argument('--seed', type=int, required=True)
        p.add_argument('--cap', type=int, required=True, help='game-turn cap')
        p.add_argument('--mind', choices=sorted(MINDS), default='scripted')
        p.add_argument('--output', type=Path)
        p.add_argument('--timeout', type=int, default=900)
        p.add_argument('--stall-timeout', type=int, default=120)
        p.add_argument('--decision-cap', type=int, default=100000,
                       help='stop after this many decisions (outcome decision_cap)')
        p.add_argument('--no-validate', action='store_true',
                       help='skip validating observations and actions against the schemas')
        p.add_argument('--no-lock', action='store_true', help='skip /tmp/angband-validation.lock')
        p.set_defaults(func=handler)

    recorder = sub.add_parser('record', help='write the run record of a finished run')
    recorder.add_argument('--run', type=Path, required=True)
    recorder.add_argument('--mode', default='play',
                          choices=['play', 'post_mortem', 'probe', 'consolidate', 'trial'])
    recorder.add_argument('--intervention', action='store_true',
                          help='the run was set up with debug commands (decision D4)')
    recorder.set_defaults(func=cmd_record)

    verifier = sub.add_parser('verify', help='replay a run without its mind and compare')
    verifier.add_argument('--run', type=Path, required=True)
    verifier.add_argument('--output', type=Path)
    verifier.add_argument('--timeout', type=int, default=900)
    verifier.add_argument('--stall-timeout', type=int, default=120)
    verifier.add_argument('--no-lock', action='store_true')
    verifier.set_defaults(func=cmd_verify)

    brancher = sub.add_parser('branch', help='replay to a turn, then play on with another mind')
    brancher.add_argument('--run', type=Path, required=True)
    brancher.add_argument('--turn', type=int, required=True)
    brancher.add_argument('--mind', choices=sorted(MINDS), default='scripted')
    brancher.add_argument('--output', type=Path)
    brancher.add_argument('--timeout', type=int, default=900)
    brancher.add_argument('--stall-timeout', type=int, default=120)
    brancher.add_argument('--no-lock', action='store_true')
    brancher.set_defaults(func=cmd_branch)

    for name, handler, help_text in (('view', cmd_view, 'show the screen at a turn'),
                                     ('dump', cmd_dump, 'write the observation at a turn'),
                                     ('explain', cmd_explain, 'show what was decided around a turn')):
        reader = sub.add_parser(name, help=help_text)
        reader.add_argument('--run', type=Path, required=True)
        reader.add_argument('--turn', type=int, required=True)
        if name == 'dump':
            reader.add_argument('--output', type=Path)
        if name == 'explain':
            reader.add_argument('--window', type=int, default=3,
                                help='how many decisions either side to show')
        reader.set_defaults(func=handler)

    args = parser.parse_args(argv)
    if args.command in ('play', 'determinism', 'agent', 'agent-determinism') and (
            not 0 <= args.seed <= 0xffffffff or args.cap < 2):
        parser.error('seed must be a uint32 and cap at least 2')
    return args.func(args)
