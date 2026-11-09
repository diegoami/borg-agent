"""Run records: everything needed to replay a run and to judge its evidence (R5).

A record is written from a run directory once the run has finished. It is
immutable (R4.1): a correction is a new record, never an edit. What R5 names is
required by the schema, so a record that validates can actually be replayed —
the pins, the build and its content identity, this repository's commit and
dirty state, the seed, the birth rule and options, the effective settings, the
birth input's hash, the calendar, and the action stream with its hash.
"""
import hashlib
import json
from pathlib import Path

from . import pins
from .build import sha

SCHEMA = 'borg-agent/run-record@1'
# A mind's name is free; its kind is the record's vocabulary (R5).
KINDS = ('stock-borg', 'scripted', 'external', 'api', 'replay')
RECORD_NAME = 'run-record.json'
STATE_HASHES_NAME = 'state-hashes.txt'
ENGINE = 'c-4.2.6'


def required(value, what):
    """Refuse to invent what a record must carry.

    A truncated trace, or a run that died before the observer printed its
    options, is exactly the run where a plausible-looking default would do the
    most harm (finding 4 of the milestone 2 review).
    """
    if not value:
        raise ValueError(f'the run does not say what its {what} were, so no record can be '
                         'written for it; look at the trace')
    return value


def parse_settings(trace, marker):
    """One of the observer's `NAME a=1 b=2` lines, as a dictionary."""
    for line in trace.splitlines():
        if line.startswith(marker + ' '):
            fields = {}
            for part in line[len(marker) + 1:].split():
                if '=' in part:
                    name, value = part.split('=', 1)
                    fields[name] = int(value) if value.lstrip('-').isdigit() else value
            return fields
    return {}


def birth_options(trace):
    """The birth options in effect, which the observer prints with the others."""
    options = parse_settings(trace, 'OPTIONS')
    return {name: value for name, value in options.items() if name.startswith('birth_')}


# Not part of the state: which run this is. Everything else the agent was
# shown is, down to the message order.
NOT_STATE = ('run_id',)


def state_hash(observation):
    """The hash of one state the agent was shown.

    It is taken over the observation in a canonical form, with the run's own
    identity left out, so the same game replayed into another directory gives
    the same hashes. Key order cannot change it either.
    """
    state = {k: v for k, v in observation.items() if k not in NOT_STATE}
    canonical = json.dumps(state, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def state_hashes(observations_path):
    """One hash per observation, in order.

    `verify` compares these decision by decision, which is what R5 means by
    the same state at every observation.
    """
    hashes = []
    with Path(observations_path).open() as lines:
        for line in lines:
            if line.strip():
                hashes.append(state_hash(json.loads(line)))
    return hashes


def write_state_hashes(run_dir):
    run_dir = Path(run_dir)
    observations = run_dir / 'observations.jsonl'
    if not observations.exists():
        return None, []
    hashes = state_hashes(observations)
    (run_dir / STATE_HASHES_NAME).write_text(''.join(h + '\n' for h in hashes))
    return sha(run_dir / STATE_HASHES_NAME), hashes


def depth_marks(states):
    """The first turn at each depth, as the zoo records it."""
    marks = {}
    for state in states:
        depth = str(state.get('depth', 0))
        if depth not in marks:
            marks[depth] = state['turn']
    return marks


def build_record(run_dir, mode='play', parent=None, mind=None, intervention=False):
    """The run record for a finished run directory."""
    run_dir = Path(run_dir)
    result = json.loads((run_dir / 'result.json').read_text())
    recipe = result['recipe']
    trace_path = run_dir / 'trace.txt'
    trace = trace_path.read_text() if trace_path.exists() else ''
    states = result.get('states') or []
    last = states[-1] if states else {}
    provenance = required(result.get('provenance'), 'build and repository state')
    kind = result.get('mind_kind') or result['mind']
    if kind not in KINDS:
        raise ValueError(f'the mind kind {kind!r} is not one of {KINDS}')
    hashes_sha, hashes = write_state_hashes(run_dir)
    stream = result.get('action_stream')

    patch_sha256 = dict(recipe['observer_sha256'])
    patch_sha256.update(recipe.get('bridge_sha256') or {})
    record = {
        'schema': SCHEMA,
        'run_id': result.get('run_id') or run_dir.name,
        'created': result['calendar']['utc'],
        'calendar': result['calendar'],
        'mode': mode,
        'parent': parent,
        # Only a model's choices are non-deterministic (R1.4, R6.3).
        'deterministic': kind in ('stock-borg', 'scripted', 'replay'),
        'intervention': intervention,
        'engine': {
            'name': ENGINE,
            'pins': {name: pin['commit'] for name, pin in pins.pins()['pins'].items()},
            'build_key': result['build_key'],
            'binary_sha256': result['binary_sha256'],
            'patch_sha256': patch_sha256,
            'data_sha256': provenance['data_sha256'],
            'compiler': provenance['compiler'],
            'platform': provenance['platform'],
            'commit': provenance['commit'],
            'dirty': provenance['dirty'],
        },
        'game': {
            'seed': result['seed'],
            'birth': {
                'race': (result.get('character') or ' ').split(' ')[-2:-1][0] if result.get('character') else 'unknown',
                'class': (result.get('character') or ' ').split(' ')[-1],
                'name': (result.get('character') or '').split(' ')[0] or None,
                'rule': 'fixed',
                'options': required(birth_options(trace), 'birth options'),
            },
            'settings': required(parse_settings(trace, 'BORG_OPTIONS'), 'Borg settings'),
            'settings_sha256': result['configuration_sha256'],
            'input_sha256': result['input_sha256'],
            'turn_cap': result['turn_cap'],
            'decision_cap': result.get('decision_cap'),
        },
        'mind': (mind or result.get('mind_record')
                 or {'kind': kind, 'chosen_by': 'not-applicable'}),
        'action_stream': {
            'count': (stream or {}).get('count', 0),
            'sha256': (stream or {}).get('sha256',
                                         hashlib.sha256(b'').hexdigest()),
            'schema': 'borg-agent/action@1',
        },
        'evidence': {k: v for k, v in {
            'trace_sha256': result.get('trace_sha256'),
            'state_hashes_sha256': hashes_sha,
            'observations_sha256': (result.get('observations') or {}).get('sha256'),
            'journal_sha256': (result.get('journal') or {}).get('sha256'),
            'model_calls_sha256': (result.get('model_calls') or {}).get('sha256'),
        }.items() if v},
        'outcome': {
            'kind': result['outcome'],
            'cause': result.get('cause') or None,
            'reason': result.get('error') or None,
            'turn': result.get('final_turn') or last.get('turn', 0),
            'depth': last.get('depth', 0),
            'max_depth': last.get('max_depth', 0),
            'level': last.get('level', 1),
            'max_level': last.get('max_level', 1),
            'depth_marks': depth_marks(states),
        },
        'usage': {
            'decisions': result.get('decisions', last.get('decisions', 0)),
            'wall_seconds': result.get('wall_seconds', 0),
            'model_calls': (result.get('model_calls') or {}).get('count', 0),
            **({'prompt_tokens': (result['usage']['used'].get('prompt_tokens') or 0),
                'completion_tokens': (result['usage']['used'].get('completion_tokens') or 0)}
               if isinstance(result.get('usage'), dict) and 'used' in result['usage'] else {}),
            **({'parse_failures': result['parse_failures']}
               if result.get('parse_failures') is not None else {}),
        },
    }
    if record['outcome']['cause'] in ('', '(alive and well)'):
        record['outcome']['cause'] = None
    return record


# Field names that must never appear in a record, and value shapes that look
# like a credential. The schema forbids unknown fields in the mind block; this
# catches a key that reached any other corner (RULES 16, review finding 5).
SECRET_NAMES = ('api_key', 'apikey', 'key', 'secret', 'password', 'token', 'authorization')
SECRET_VALUE = r'(?i)(sk-[A-Za-z0-9]{8,}|bearer\s+\S+|[A-Za-z0-9_-]{40,}://|://[^/\s]*:[^/@\s]+@)'


def secrets_in(document, path=''):
    """Anything in a record that looks like a credential."""
    import re

    problems = []
    if isinstance(document, dict):
        for name, value in document.items():
            where = f'{path}.{name}' if path else name
            if name.lower() in SECRET_NAMES:
                problems.append(f'{where}: a record never carries a key (RULES 16)')
            problems += secrets_in(value, where)
    elif isinstance(document, list):
        for index, value in enumerate(document):
            problems += secrets_in(value, f'{path}[{index}]')
    elif isinstance(document, str):
        if re.search(SECRET_VALUE, document):
            problems.append(f'{path}: the value looks like a credential (RULES 16)')
    return problems


def validate(record):
    """Against schemas/run-record@1.json; raises with the first problems."""
    from jsonschema import Draft202012Validator, FormatChecker
    schema = json.loads((pins.ROOT / 'schemas' / 'run-record@1.json').read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(record), key=str)
    if errors:
        raise ValueError('; '.join(f'{list(e.absolute_path)}: {e.message}' for e in errors[:4]))
    leaks = secrets_in(record)
    if leaks:
        raise ValueError('; '.join(leaks[:4]))
    return record


def write_record(run_dir, **kwargs):
    """Write the run record beside the run, once. It is never rewritten (R4.1)."""
    run_dir = Path(run_dir)
    path = run_dir / RECORD_NAME
    if path.exists():
        raise ValueError(f'{path} exists; a run record is immutable (R4.1)')
    record = validate(build_record(run_dir, **kwargs))
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return path
