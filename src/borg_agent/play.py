"""Play the instrumented build headless through the test frontend.

This is T01: the stock Borg plays, nothing of this repository decides anything.
The run's evidence is the observer's `trace.txt`, which holds only game facts
(turn, RNG state, character, options, messages) and no wall time or paths, so
two runs of the same seed and cap must produce identical bytes.
"""
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from .build import binary, provenance, sha

# The zoo runner's birth input: splash, first race (Human), first class
# (Warrior), default point buy, then the Borg's activation keys.
BIRTH_INPUT = '''key space
key a
key a
key a
key enter
key enter
key enter
key enter
key space
key C-z
key space
key space
key y
key z
'''
BIRTH_DESCRIPTION = 'Human Warrior; default point buy; normal UI birth'
BORG_CONFIG = 'borg_cheat_death = FALSE\nborg_respawn_winners = FALSE\n'
LOCK_PATH = os.environ.get('BORG_AGENT_LOCK', '/tmp/angband-validation.lock')
FINAL_KINDS = ('death', 'completion', 'turn_cap', 'saved')
# How a run can legitimately end. Hitting a budget or a decision cap is an
# outcome, not a failure (R2.3), and neither is a death; only the harness's own
# troubles are failures.
GOOD_OUTCOMES = ('death', 'completion', 'turn_cap', 'saved',
                 'budget_cap', 'decision_cap', 'agent_stopped')
HARNESS_OUTCOMES = ('stalled', 'wall_timeout', 'crash', 'harness_failure', 'config_error')
# Finding 5 of the milestone-1 review: the game needs none of the owner's keys,
# so it is given an environment built from this list and nothing else.
ENVIRONMENT_ALLOWLIST = ('PATH', 'HOME', 'TERM', 'TZ', 'LANG', 'LC_ALL', 'LC_CTYPE')


def game_environment(**extra):
    """The environment the game process gets: nothing of ours but the game's own.

    A model key in this session's environment has no business in a child that
    never calls a model, nor in the terminal log it writes (RULES 16).
    """
    env = {name: os.environ[name] for name in ENVIRONMENT_ALLOWLIST if name in os.environ}
    env.update(LC_ALL='C.UTF-8', LANG='C.UTF-8')
    env.update({name: str(value) for name, value in extra.items()})
    return env


# The days the game admits seasonal monsters (`get_mon_num` reads the clock),
# so the same seed plays a different game. Found by the milestone-1 review.
SEASONAL_DAYS = ((12, 24), (12, 25), (12, 26))


def seasonal(moment=None):
    """Whether a local date falls in the game's seasonal window."""
    moment = moment or datetime.datetime.now().astimezone()
    return (moment.month, moment.day) in SEASONAL_DAYS


def calendar():
    """When the run happened, as the zoo's runner records it, and whether the
    game's seasonal monsters were available.

    Play is not independent of the date, so a seed reproduces a game only on a
    day of the same kind. A record that does not say when it ran cannot be
    replayed with confidence.
    """
    local = datetime.datetime.now().astimezone()
    return {'utc': local.astimezone(datetime.timezone.utc).isoformat(),
            'local': local.isoformat(),
            'timezone_name': local.tzname(),
            'TZ_environment': os.environ.get('TZ'),
            'seasonal': seasonal(local)}


def lock_holders(path=None, procfs='/proc'):
    """The process ids holding the heavy-run lock, as /proc shows them.

    Best effort and Linux-only: it is used to explain a wait, never to decide
    anything about play.
    """
    path = str(path or LOCK_PATH)
    holders = []
    root = Path(procfs)
    if not root.exists():
        return holders
    for entry in root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            for descriptor in (entry / 'fd').iterdir():
                if os.readlink(descriptor) == path:
                    holders.append(int(entry.name))
                    break
        except OSError:
            continue       # the process went away, or is not ours to look at
    return sorted(holders)


def parents(pid=None, procfs='/proc'):
    """This process's ancestors, closest first."""
    chain = []
    current = pid if pid is not None else os.getppid()
    seen = set()
    while current and current > 1 and current not in seen:
        seen.add(current)
        chain.append(current)
        try:
            stat = (Path(procfs) / str(current) / 'stat').read_text()
            # ... after the comm field, which may itself contain spaces.
            current = int(stat[stat.rindex(')') + 1:].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return chain


def held_by_an_ancestor(path=None, procfs='/proc', pid=None):
    """Whether a process we are a child of already holds the lock.

    `flock /tmp/angband-validation.lock pytest -m slow` is the documented way
    to run heavy work, and the suite's own runs take the same lock. A second
    acquire from inside that process tree can never succeed — the holder is
    waiting for us — so it is skipped: the work is already serialized by the
    ancestor that holds it.
    """
    holders = set(lock_holders(path, procfs))
    return bool(holders & set(parents(pid, procfs)))


@contextlib.contextmanager
def heavy_lock(enabled=True, timeout=600, log=print):
    """Serialize heavy local runs with the owner's other Angband work.

    Skipped when BORG_AGENT_NO_LOCK is set, or when an ancestor process
    already holds the lock. A wait that goes on too long raises instead of
    hanging for ever, and says who is holding it.
    """
    if not enabled or os.environ.get('BORG_AGENT_NO_LOCK'):
        yield None
        return
    if held_by_an_ancestor():
        yield None
        return
    with open(LOCK_PATH, 'a+') as handle:
        waited = 0.0
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if waited >= timeout:
                    raise TimeoutError(
                        f'waited {int(waited)}s for {LOCK_PATH}, held by '
                        f'{lock_holders() or "another process"}. If you are running under an '
                        f'outer `flock` on the same file, that is detected; otherwise stop the '
                        f'holder or set BORG_AGENT_NO_LOCK=1.')
                if waited and not waited % 30:
                    log(f'waiting for {LOCK_PATH}, held by {lock_holders()}')
                time.sleep(0.5)
                waited += 0.5
        try:
            yield handle
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def parse_states(text):
    states = []
    for line in text.splitlines(keepends=True):
        if line.endswith('\n') and line.startswith('STATE '):
            parts = line.split()
            states.append({'kind': parts[1],
                           **{k: int(v) if len(v) < 20 and v.lstrip('-').isdigit() else v
                              for k, v in (p.split('=', 1) for p in parts[2:])}})
    return states


def classify(code, states, interrupted=None):
    if interrupted:
        return interrupted
    if code is None or code < 0:
        return 'crash'
    if code == 0 and states and states[-1]['kind'] in FINAL_KINDS:
        return states[-1]['kind']
    return 'harness_failure'


def monitor(process, trace_path, wall_limit, stall_limit):
    """Stop a run that hangs or stops advancing.

    This is the zoo runner's rule with one difference, deliberate: the runner
    only watches for a stall once it has seen a turn, so a game that never
    reaches its first state — a birth the input does not answer, for instance —
    runs to the wall limit. Here the stall clock starts with the run, so such a
    game is `stalled` within the stall limit instead of hanging.
    """
    start = changed = time.monotonic()
    last_turn = None
    while process.poll() is None:
        states = (parse_states(trace_path.read_text(encoding='utf-8', errors='replace'))
                  if trace_path.exists() else [])
        current_turn = states[-1]['turn'] if states else None
        now = time.monotonic()
        if current_turn != last_turn:
            last_turn, changed = current_turn, now
        reason = ('stalled' if now - changed >= stall_limit
                  else 'wall_timeout' if now - start >= wall_limit else None)
        if reason:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            return reason
        time.sleep(0.1)
    return None


def play(build_out, seed, cap, output, timeout=600, stall_timeout=60,
         checkpoint_saves=False, lock=True, log=print):
    """Play one game with the stock Borg and write the run's files to `output`."""
    build_out, output = Path(build_out).resolve(), Path(output).resolve()
    manifest = json.loads((build_out / 'build.json').read_text())
    if not manifest.get('complete'):
        raise ValueError(f'{build_out} holds no finished build')
    if sha(binary(build_out)) != manifest['binary_sha256']:
        raise ValueError('binary no longer matches the build manifest')
    for name, digest in manifest['data_sha256'].items():
        if sha(build_out / 'source' / name) != digest:
            raise ValueError(f'game data changed since the build: {name}')
    output.mkdir(parents=True)
    for directory in ('user', 'archive', 'save', 'scores', 'panic'):
        (output / directory).mkdir()
    (output / 'user/borg.txt').write_text(BORG_CONFIG)
    (output / 'input.txt').write_text(BIRTH_INPUT)
    source = build_out / 'source'
    command = [str(binary(build_out)), '-mtest', '-uMeasure']
    command += [f'-d{d}={output / d}' for d in ('user', 'archive', 'save', 'scores', 'panic')]
    command += [f'-d{key}={source / "lib" / directory}'
                for key, directory in (('gamedata', 'gamedata'), ('pref', 'customize'))]
    env = game_environment(BORG_MEASURE_SEED=seed, BORG_MEASURE_CAP=cap,
                           BORG_MEASURE_DIR=output)
    if not checkpoint_saves:
        env['BORG_MEASURE_NO_SAVES'] = '1'
    record = {
        'schema': 'borg-agent/play@1',
        'mind': 'stock-borg',
        'mind_kind': 'stock-borg',
        'seed': seed, 'turn_cap': cap,
        'birth': BIRTH_DESCRIPTION,
        'checkpoint_saves': checkpoint_saves,
        'wall_limit_seconds': timeout, 'stall_limit_seconds': stall_timeout,
        'build_key': manifest['build_key'],
        'binary_sha256': manifest['binary_sha256'],
        'recipe': manifest['recipe'],
        'provenance': provenance(build_out),
        'input_sha256': sha(output / 'input.txt'),
        'configuration_sha256': sha(output / 'user/borg.txt'),
        'command': command, 'cwd': str(source),
        'calendar': calendar(),
        'outcome': 'harness_failure',
    }
    (output / 'result.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    waiting = time.monotonic()
    process = None
    with heavy_lock(lock):
        started = time.monotonic()
        record['lock_wait_seconds'] = round(started - waiting, 3)
        try:
            with (output / 'input.txt').open() as stdin, (output / 'terminal.log').open('w') as terminal:
                process = subprocess.Popen(command, cwd=source, env=env, stdin=stdin,
                                           stdout=terminal, stderr=subprocess.STDOUT)
                interrupted = monitor(process, output / 'trace.txt', timeout, stall_timeout)
                record['exit_code'] = process.returncode
            trace_path = output / 'trace.txt'
            trace = trace_path.read_text() if trace_path.exists() else ''
            states = parse_states(trace)
            record['states'] = states
            record['outcome'] = classify(record.get('exit_code'), states, interrupted)
            record['cause'] = next((line[6:] for line in trace.splitlines()
                                    if line.startswith('CAUSE ')), None)
            record['character'] = next((line[10:] for line in trace.splitlines()
                                        if line.startswith('CHARACTER ')), None)
            record['trace_sha256'] = hashlib.sha256(trace.encode()).hexdigest() if trace else None
            record['final_turn'] = states[-1]['turn'] if states else None
        except (OSError, ValueError) as exc:
            record['error'] = str(exc)
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            record['wall_seconds'] = round(time.monotonic() - started, 3)
            (output / 'result.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    log(json.dumps({k: record.get(k) for k in
                    ('seed', 'outcome', 'final_turn', 'cause', 'wall_seconds', 'trace_sha256')}))
    return record
