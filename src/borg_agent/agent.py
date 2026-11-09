"""Play the pinned game with a mind in place of the Borg's thinking (T03).

The bridge (bridge/agent-bridge.c) writes one observation to a pipe and waits
for one action, so the game waits for the agent and no game time passes while
the mind decides (R1.3). This module owns the other end: it validates what
crosses the pipes against the schemas, turns an action into the bridge's wire
line, and records the action stream so the run can be replayed without the
mind.
"""
import hashlib
import json
import os
import select
import subprocess
import time
from pathlib import Path

from . import checks, play, signals
from .build import binary, provenance, sha

OBS_FIFO = 'observations.fifo'
ACT_FIFO = 'actions.fifo'
ACTION_LOG = 'actions.jsonl'
OBSERVATION_LOG = 'observations.jsonl'
JOURNAL_LOG = 'decisions.jsonl'
# What apply_action in the bridge can translate. Anything else is a mistake
# here, not at run time, so it raises before a key is sent.
WIRE_COMMANDS = {
    'walk': {'direction': 'dir'},
    'alter': {'direction': 'dir'},
    'stay': {},
    'pickup': {},
    'escape': {},
    'go_down': {},
    'go_up': {},
    'rest': {'mode': 'mode', 'count': 'count'},
    'answer': {'answer': 'text'},
    'read': {'item': 'item'},
    'quaff': {'item': 'item'},
    'buy': {'item': 'item', 'count': 'count'},
    'sell': {'item': 'item', 'count': 'count'},
}
SAFE = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.,:/')


def escape(value):
    """Percent-escape a wire token, so a line never breaks on a space."""
    return ''.join(c if c in SAFE else ''.join(f'%{b:02x}' for b in c.encode())
                   for c in str(value))


def wire(action):
    """One action as the bridge's line. The bridge turns it into keys."""
    kind = action['kind']
    if kind == 'keys':
        return 'keys ' + escape(action['keys']['keys'])
    if kind != 'command':
        raise ValueError(f'the bridge has no translation for a {kind} action yet (T05)')
    command = action['command']
    name = command['name']
    if name not in WIRE_COMMANDS:
        raise ValueError(f'the bridge has no key translation for the command {name!r}')
    fields = [name]
    for field, value in sorted(command.items()):
        if field == 'name':
            continue
        if field not in WIRE_COMMANDS[name]:
            raise ValueError(f'the command {name!r} takes no {field!r}')
        fields.append(f'{WIRE_COMMANDS[name][field]}={escape(value)}')
    return 'command ' + ' '.join(fields)


class Validator:
    """Checks observations and actions against the schemas of T02."""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.checked = 0
        if enabled:
            from jsonschema import Draft202012Validator
            root = Path(__file__).resolve().parents[2] / 'schemas'
            self.schemas = {
                name: Draft202012Validator(json.loads((root / f'{name}@1.json').read_text()))
                for name in ('observation', 'action')
            }

    def check(self, name, document, where):
        if not self.enabled:
            return
        errors = sorted(self.schemas[name].iter_errors(document), key=str)
        if errors:
            raise ValueError(f'{where}: ' + '; '.join(
                f'{list(e.absolute_path)}: {e.message}' for e in errors[:3]))
        if name == 'observation':
            # R1.1's naming rule, which the schema cannot express.
            checks.enforce(checks.check_observation(document), where)
        self.checked += 1


def drain_journal_into(mind, journal_log):
    """Write what the mind has to say beyond the command it produced.

    A mind that chooses primitives records what it chose, why, and why the
    last primitive stopped (R2). Everything else keeps no journal.
    """
    drain = getattr(mind, 'drain_journal', None)
    if not drain:
        return 0
    written = 0
    for entry in drain():
        journal_log.write(json.dumps(entry, sort_keys=True) + '\n')
        written += 1
    if written:
        journal_log.flush()
    return written


def open_pipes(obs_path, act_path, process, deadline):
    """The handshake, bounded in time.

    The order is forced by what a FIFO does. The bridge opens the observation
    pipe for writing (which needs a reader) and then the action pipe for
    reading (which needs a writer), so this side opens the read end first and
    then waits for the write end to be accepted. Waiting for the bridge's
    first observation instead would deadlock: it cannot write one until its
    own action pipe is open.

    Both waits are bounded, and the child is watched while we wait: a game
    that dies before the bridge opens its end — a bad build, a birth the input
    does not answer — must not leave this blocked on a pipe that will never
    have a writer, holding the heavy-run lock for ever.
    """
    read_fd = os.open(obs_path, os.O_RDONLY | os.O_NONBLOCK)
    while True:
        try:
            # ENXIO until the bridge has opened the action pipe for reading.
            write_fd = os.open(act_path, os.O_WRONLY | os.O_NONBLOCK)
            break
        except OSError:
            if process.poll() is not None:
                os.close(read_fd)
                return None, None, (f'the game exited before it opened the pipes '
                                    f'(code {process.returncode})')
            if time.monotonic() >= deadline:
                os.close(read_fd)
                return None, None, 'the game never opened the action pipe'
            time.sleep(0.01)
    os.set_blocking(read_fd, True)
    os.set_blocking(write_fd, True)
    return os.fdopen(read_fd, 'r'), os.fdopen(write_fd, 'w'), None


def read_line(stream, deadline, stall_deadline):
    """A line from the bridge, or None when it is time to stop."""
    while True:
        now = time.monotonic()
        remaining = min(deadline, stall_deadline) - now
        if remaining <= 0:
            return None
        ready, _, _ = select.select([stream], [], [], remaining)
        if not ready:
            return None
        line = stream.readline()
        if line == '':
            return ''  # the game closed the pipe: it has finished
        return line


# A game that answers but never advances is stalled, however fast it answers.
# The turn cap cannot catch that on its own: entering and leaving a shop, or
# walking into a wall, costs no game time at all.
DEFAULT_TURN_STALL_DECISIONS = 500


def play_with_mind(build_out, seed, cap, output, mind, timeout=900, stall_timeout=120,
                   decision_cap=100000, turn_stall_decisions=DEFAULT_TURN_STALL_DECISIONS,
                   checkpoint_saves=False, from_turn=None, validate=True, lock=True,
                   log=print):
    """Play one game with `mind` deciding, and record everything it decided."""
    build_out, output = Path(build_out).resolve(), Path(output).resolve()
    manifest = json.loads((build_out / 'build.json').read_text())
    if not manifest.get('complete'):
        raise ValueError(f'{build_out} holds no finished build')
    if sha(binary(build_out)) != manifest['binary_sha256']:
        raise ValueError('binary no longer matches the build manifest')
    output.mkdir(parents=True)
    for directory in ('user', 'archive', 'save', 'scores', 'panic'):
        (output / directory).mkdir()
    (output / 'user/borg.txt').write_text(play.BORG_CONFIG)
    (output / 'input.txt').write_text(play.BIRTH_INPUT)
    obs_path, act_path = output / OBS_FIFO, output / ACT_FIFO
    os.mkfifo(obs_path)
    os.mkfifo(act_path)
    source = build_out / 'source'
    run_id = output.name
    command = [str(binary(build_out)), '-mtest', '-uMeasure']
    command += [f'-d{d}={output / d}' for d in ('user', 'archive', 'save', 'scores', 'panic')]
    command += [f'-d{key}={source / "lib" / directory}'
                for key, directory in (('gamedata', 'gamedata'), ('pref', 'customize'))]
    env = play.game_environment(
        BORG_MEASURE_SEED=seed, BORG_MEASURE_CAP=cap, BORG_MEASURE_DIR=output,
        BORG_AGENT_OBS=obs_path, BORG_AGENT_ACT=act_path, BORG_AGENT_RUN_ID=run_id)
    if not checkpoint_saves:
        env['BORG_MEASURE_NO_SAVES'] = '1'
    if from_turn:
        # Mode B: the Borg plays the prefix and this mind takes over at that
        # turn, so the handshake may be a long way off.
        env['BORG_AGENT_FROM_TURN'] = str(from_turn)
    validator = Validator(validate)
    # A mind that calls a model writes its calls beside the run (R2.1), and a
    # mind that does not has no attribute for it.
    if getattr(mind, 'call_log', 'absent') is None:
        from .model_mind import CallLog

        mind.call_log = CallLog(output / 'model-calls.jsonl')
    record = {
        'schema': 'borg-agent/play@1',
        'mind': mind.name,
        'mind_kind': getattr(mind, 'kind', 'scripted'),
        'run_id': run_id,
        'seed': seed, 'turn_cap': cap, 'decision_cap': decision_cap,
        'birth': play.BIRTH_DESCRIPTION,
        'checkpoint_saves': checkpoint_saves,
        'from_turn': from_turn,
        'wall_limit_seconds': timeout, 'stall_limit_seconds': stall_timeout,
        'turn_stall_decisions': turn_stall_decisions,
        'build_key': manifest['build_key'],
        'binary_sha256': manifest['binary_sha256'],
        'recipe': manifest['recipe'],
        'provenance': provenance(build_out),
        'input_sha256': sha(output / 'input.txt'),
        'configuration_sha256': sha(output / 'user/borg.txt'),
        'schemas_validated': validate,
        'command': command, 'cwd': str(source),
        'calendar': play.calendar(),
        'outcome': 'harness_failure',
    }
    (output / 'result.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    waiting = time.monotonic()
    process = None
    interrupted = None
    decisions = 0
    journal_entries = 0
    with play.heavy_lock(lock):
        started = time.monotonic()
        record['lock_wait_seconds'] = round(started - waiting, 3)
        try:
            with (output / 'input.txt').open() as stdin, (output / 'terminal.log').open('w') as terminal:
                process = subprocess.Popen(command, cwd=source, env=env, stdin=stdin,
                                           stdout=terminal, stderr=subprocess.STDOUT)
                deadline = started + timeout
                observations, actions, trouble = open_pipes(obs_path, act_path, process, deadline)
                if trouble:
                    record['error'] = trouble
                with (observations or open(os.devnull)) as observations, \
                        (actions or open(os.devnull, 'w')) as actions, \
                        (output / ACTION_LOG).open('w') as action_log, \
                        (output / OBSERVATION_LOG).open('w') as observation_log, \
                        (output / JOURNAL_LOG).open('w') as journal_log:
                    last_turn = None
                    decisions_at_this_turn = 0
                    stall_deadline = time.monotonic() + stall_timeout
                    while not trouble:
                        line = read_line(observations, deadline, stall_deadline)
                        if line is None:
                            interrupted = ('wall_timeout' if time.monotonic() >= deadline
                                           else 'stalled')
                            break
                        if line == '':
                            break
                        observation = json.loads(line)
                        validator.check('observation', observation,
                                        f'observation {observation.get("decision")}')
                        observation_log.write(line)
                        # Progress in the game is its own question: a turn
                        # that never moves is a stall whatever the clock says.
                        if observation['turn'] != last_turn:
                            last_turn = observation['turn']
                            decisions_at_this_turn = 0
                        else:
                            decisions_at_this_turn += 1
                            if decisions_at_this_turn >= turn_stall_decisions:
                                interrupted = 'stalled'
                                record['error'] = (
                                    f'{decisions_at_this_turn} decisions at turn '
                                    f'{last_turn} without the game advancing')
                                break
                        try:
                            action = mind.act(observation)
                        except signals.CannotAct as exc:
                            # The agent gave up; that is an outcome (R5). The
                            # stops that led to it are the most interesting
                            # lines in the journal, so they are written before
                            # the run ends.
                            interrupted = 'agent_stopped'
                            record['error'] = str(exc)
                            journal_entries += drain_journal_into(mind, journal_log)
                            break
                        except signals.BudgetSpent as exc:
                            # What the run was allowed, spent. An outcome
                            # (R2.3), not a failure.
                            interrupted = 'budget_cap'
                            record['error'] = str(exc)
                            record['budget'] = exc.allowed
                            journal_entries += drain_journal_into(mind, journal_log)
                            break
                        except signals.ModelFailed as exc:
                            # The provider, not the game: infrastructure.
                            interrupted = 'harness_failure'
                            record['error'] = str(exc)
                            journal_entries += drain_journal_into(mind, journal_log)
                            break
                        except signals.StreamEnded as exc:
                            # A replay reached the end of what was recorded.
                            # The run it came from was ended by the harness, so
                            # this is where the recording stops (R2.3).
                            interrupted = 'agent_stopped'
                            record['error'] = str(exc)
                            record['stream_ended'] = {'decisions': exc.decisions,
                                                      'turn': exc.turn}
                            journal_entries += drain_journal_into(mind, journal_log)
                            break
                        validator.check('action', action, f'action {decisions}')
                        action_log.write(json.dumps(action, sort_keys=True) + '\n')
                        journal_entries += drain_journal_into(mind, journal_log)
                        actions.write(wire(action) + '\n')
                        actions.flush()
                        # The stall limit is on the *game's* answer, so the
                        # clock starts when the action goes out, not when the
                        # last observation came in. Model latency must never
                        # become an outcome (R1.3), and the mind has just had
                        # all the time it wanted.
                        stall_deadline = time.monotonic() + stall_timeout
                        decisions += 1
                        if decisions >= decision_cap:
                            interrupted = 'decision_cap'
                            break
                if interrupted:
                    process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                record['exit_code'] = process.returncode
            trace_path = output / 'trace.txt'
            trace = trace_path.read_text() if trace_path.exists() else ''
            states = play.parse_states(trace)
            record['states'] = states
            record['outcome'] = play.classify(record.get('exit_code'), states, interrupted)
            record['cause'] = next((l[6:] for l in trace.splitlines() if l.startswith('CAUSE ')), None)
            record['character'] = next((l[10:] for l in trace.splitlines()
                                        if l.startswith('CHARACTER ')), None)
            record['trace_sha256'] = hashlib.sha256(trace.encode()).hexdigest() if trace else None
            record['final_turn'] = states[-1]['turn'] if states else None
            record['action_stream'] = {
                'count': decisions,
                'sha256': sha(output / ACTION_LOG),
                'schema': 'borg-agent/action@1',
                'path': ACTION_LOG,
            }
            record['observations'] = {'count': decisions, 'sha256': sha(output / OBSERVATION_LOG),
                                      'path': OBSERVATION_LOG}
            if journal_entries:
                record['journal'] = {'count': journal_entries,
                                     'sha256': sha(output / JOURNAL_LOG),
                                     'path': JOURNAL_LOG}
            # What the model cost, and what it was told (R2.1, R2.3).
            call_log = getattr(mind, 'call_log', None)
            if call_log is not None and call_log.count:
                record['model_calls'] = {'count': call_log.count,
                                         'sha256': call_log.sha256(),
                                         'path': 'model-calls.jsonl'}
            budget = getattr(mind, 'budget', None)
            if budget is not None:
                record['usage'] = budget.record()
            if getattr(mind, 'parse_failures', None) is not None:
                record['parse_failures'] = mind.parse_failures
            if getattr(mind, 'mind_record', None):
                record['mind_record'] = mind.mind_record
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            record['error'] = f'{type(exc).__name__}: {exc}'
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            record['wall_seconds'] = round(time.monotonic() - started, 3)
            record['decisions'] = decisions
            (output / 'result.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    log(json.dumps({k: record.get(k) for k in
                    ('run_id', 'outcome', 'final_turn', 'decisions', 'cause', 'error',
                     'wall_seconds', 'lock_wait_seconds')}))
    return record
