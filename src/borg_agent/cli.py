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
from . import executor as executor_module
from . import mind as mind_module
from . import play as play_module
from . import record as record_module
from . import replay as replay_module

def api_mind(args):
    """The model of the active profile's `play` job (D7), with its budget."""
    from . import model_mind, models as models_module, prompts

    configuration = models_module.load(profile=args.profile)
    choice = configuration['play']
    missing = configuration.missing_keys(['play'])
    if missing:
        raise models_module.ConfigurationError(
            f'the play job needs ${missing[0]}, which is not set')
    pack = prompts.load_pack(args.pack)
    if pack.job != 'play':
        raise prompts.PromptError(f'the pack {pack.version!r} is for the {pack.job} job')
    print(f'play: {choice.provider}/{choice.model} ({choice.family}), profile '
          f'{choice.profile}, chosen by {choice.chosen_by}, pack {pack.version} '
          f'{pack.sha256[:12]}')
    from . import knowledge as knowledge_module

    store = knowledge_module.Store()
    learned = None if args.no_knowledge else (store.for_prompt() or None)
    if learned:
        print(f'carrying {len(learned.splitlines())} claims into the prompt '
              f'(knowledge {store.sha256()[:12]})')
    return model_mind.ApiMind(
        choice, pack=pack,
        budget=model_mind.Budget(model_calls=args.budget_calls, tokens=args.budget_tokens),
        choice_record=configuration.record('play'),
        knowledge=learned, knowledge_sha256=store.sha256() if learned else None,
        timeout=args.model_timeout)


def external_mind(args):
    from . import model_mind

    directory = Path(args.external_dir or (RUNS / 'external'))
    print(f'write answers into {directory}')
    return model_mind.ExternalMind(directory)


MINDS = {'scripted': mind_module.ScriptedMind,
         # The primitives of R2, with a scripted chooser in front (T05).
         'scripted-primitives': lambda: executor_module.ExecutingMind(
             mind_module.PrimitiveMind(), name='scripted-primitives')}
# The minds that need the run's arguments: a model, or a person at a file.
CONFIGURED_MINDS = {'api': api_mind, 'external': external_mind}
ALL_MINDS = sorted({*MINDS, *CONFIGURED_MINDS})


def build_mind(args):
    """The mind a run was asked for."""
    if args.mind in CONFIGURED_MINDS:
        inner = CONFIGURED_MINDS[args.mind](args)
        if args.mind == 'api' and not args.no_executor:
            # A model chooses primitives; the executor runs them (R2).
            return executor_module.ExecutingMind(inner, name=f'api:{args.mind}')
        return inner
    return MINDS[args.mind]()

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
        out, args.seed, args.cap, output, build_mind(args),
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
            out, args.seed, args.cap, base / f'run{attempt}', build_mind(args),
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
        args.run, args.turn, output, build_mind(args), timeout=args.timeout,
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


def cmd_knowledge(args):
    """Read the knowledge base, or regenerate its views (R4.2)."""
    from . import knowledge as knowledge_module

    store = knowledge_module.Store()
    if args.what == 'views':
        written = store.render_views()
        for area, path in sorted(written.items()):
            print(f'{area:12} {path}')
        return 0
    claims = store.all()
    if args.area:
        claims = [claim for claim in claims if claim['area'] == args.area]
    for claim in claims:
        print(f"[{claim['area']} {claim['status']}] {claim['id']}: {claim['statement']}")
    print(f'{len(claims)} claims, knowledge {store.sha256() or "(empty)"}')
    return 0


def cmd_consolidate(args):
    """Turn a run into claims with the consolidate model (mode D)."""
    from . import consolidate as consolidate_module
    from . import knowledge as knowledge_module
    from . import model_mind, models as models_module, prompts

    configuration = models_module.load(profile=args.profile)
    choice = configuration['consolidate']
    missing = configuration.missing_keys(['consolidate'])
    if missing:
        raise models_module.ConfigurationError(
            f'the consolidate job needs ${missing[0]}, which is not set')
    print(f'consolidate: {choice.provider}/{choice.model} ({choice.family}), profile '
          f'{choice.profile}')
    result = consolidate_module.consolidate(
        args.run, choice, store=knowledge_module.Store(),
        pack=prompts.load_pack(args.pack),
        budget=model_mind.Budget(model_calls=args.budget_calls, tokens=args.budget_tokens),
        call_log=model_mind.CallLog(Path(args.run) / 'model-calls.jsonl'),
        timeout=args.timeout)
    return 0 if result['added'] or not result['refused'] else 1


def cmd_post_mortem(args):
    """Mode B: hand over to a mind shortly before a recorded death (R3)."""
    from . import postmortem

    out = build_module.prepare()
    if args.run:
        death = postmortem.death_of(args.run)
        if death is None:
            print(f'{args.run} did not end in a death; mode B needs one')
            return 1
    else:
        found = run_dir(f'death-seed{args.seed}-cap{args.cap}')
        print(f'playing the Borg on seed {args.seed} to find its death...')
        result = postmortem.find_death(out, args.seed, args.cap, found,
                                       timeout=args.timeout,
                                       stall_timeout=args.stall_timeout,
                                       lock=not args.no_lock)
        death = postmortem.death_of(found)
        if death is None:
            print(f'the Borg did not die on seed {args.seed} within {args.cap} turns '
                  f'({result["outcome"]}); try another seed or a higher cap')
            return 1
    print(f'death: {death["cause"]} at turn {death["turn"]} (seed {death["seed"]})')
    output = Path(args.output) if args.output else run_dir(
        f'post-mortem-seed{death["seed"]}-turn{death["turn"]}-{args.mind}')
    result, parent = postmortem.post_mortem(
        out, death, build_mind(args), output, before=args.before, cap=args.cap,
        timeout=args.timeout, stall_timeout=args.stall_timeout, lock=not args.no_lock)
    postmortem.write_record(output, parent)
    print(output)
    return 0 if result['outcome'] in play_module.GOOD_OUTCOMES else 1


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
        p.add_argument('--mind', choices=ALL_MINDS, default='scripted')
        p.add_argument('--profile', help='the models.yaml profile to use (api); '
                                         'otherwise the active one (D7)')
        p.add_argument('--pack', default='play-1', help='the prompt pack (api)')
        p.add_argument('--budget-calls', type=int, default=None,
                       help='stop after this many model calls; the outcome is budget_cap (R2.3)')
        p.add_argument('--budget-tokens', type=int, default=None,
                       help='stop after this many tokens; the outcome is budget_cap')
        p.add_argument('--external-dir', type=Path, help='where the external mind reads answers')
        p.add_argument('--no-executor', action='store_true',
                       help='give the model the game directly, without the primitives')
        p.add_argument('--no-knowledge', action='store_true',
                       help='do not put the knowledge base in the prompt')
        p.add_argument('--model-timeout', type=int, default=240,
                       help='how long to wait for one model call; a provider that goes over '
                            'this ends the run as a harness failure, not as play')
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
    brancher.add_argument('--mind', choices=ALL_MINDS, default='scripted')
    brancher.add_argument('--profile')
    brancher.add_argument('--pack', default='play-1')
    brancher.add_argument('--budget-calls', type=int, default=None)
    brancher.add_argument('--budget-tokens', type=int, default=None)
    brancher.add_argument('--external-dir', type=Path)
    brancher.add_argument('--no-executor', action='store_true')
    brancher.add_argument('--no-knowledge', action='store_true')
    brancher.add_argument('--model-timeout', type=int, default=240)
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

    mortem = sub.add_parser('post-mortem',
                            help="take over shortly before the Borg's death (mode B)")
    mortem.add_argument('--seed', type=int, default=7,
                        help='the seed whose Borg death to work from')
    mortem.add_argument('--run', type=Path,
                        help='a recorded Borg death to use instead of playing one')
    mortem.add_argument('--cap', type=int, default=100000)
    mortem.add_argument('--before', type=int, default=200,
                        help='how many game turns before the death to take over')
    mortem.add_argument('--mind', choices=ALL_MINDS, default='scripted-primitives')
    mortem.add_argument('--profile')
    mortem.add_argument('--pack', default='play-1')
    mortem.add_argument('--budget-calls', type=int, default=None)
    mortem.add_argument('--budget-tokens', type=int, default=None)
    mortem.add_argument('--external-dir', type=Path)
    mortem.add_argument('--no-executor', action='store_true')
    mortem.add_argument('--no-knowledge', action='store_true')
    mortem.add_argument('--model-timeout', type=int, default=240)
    mortem.add_argument('--output', type=Path)
    mortem.add_argument('--timeout', type=int, default=1800)
    mortem.add_argument('--stall-timeout', type=int, default=120)
    mortem.add_argument('--no-lock', action='store_true')
    mortem.set_defaults(func=cmd_post_mortem)

    reader = sub.add_parser('knowledge', help='read the knowledge base or rebuild its views')
    reader.add_argument('what', choices=['list', 'views'], nargs='?', default='list')
    reader.add_argument('--area', help='only this area')
    reader.set_defaults(func=cmd_knowledge)

    consolidator = sub.add_parser('consolidate', help='turn a run into claims (mode D)')
    consolidator.add_argument('--run', type=Path, required=True)
    consolidator.add_argument('--profile')
    consolidator.add_argument('--pack', default='consolidate-1')
    consolidator.add_argument('--budget-calls', type=int, default=2)
    consolidator.add_argument('--budget-tokens', type=int, default=None)
    consolidator.add_argument('--timeout', type=int, default=420,
                              help='a consolidator reads a whole run; the first real call '
                                   'needed five minutes')
    consolidator.set_defaults(func=cmd_consolidate)

    args = parser.parse_args(argv)
    if args.command in ('play', 'determinism', 'agent', 'agent-determinism') and (
            not 0 <= args.seed <= 0xffffffff or args.cap < 2):
        parser.error('seed must be a uint32 and cap at least 2')
    return args.func(args)
