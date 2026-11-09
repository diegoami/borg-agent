"""Mode C: one question, answered in counted trials (T22).

A probe is **data**, not code: a file under `probes/` says what is asked, how
the situation is made, what action is tried, what the control is, which seeds
are declared, and what counts as a success. Running it plays one trial per
seed per arm and counts them. The result is `quantified N of M`, and the
**harness** writes it — a model may propose a probe and never score one (R4.3,
RULES 13).

Two kinds of setup, and the record says which:

- `natural`: the situation is found in deterministic play. Nothing is
  tampered with, so such a run counts in survival figures.
- `intervened`: the situation is built with the game's **own debug commands**,
  driven as keys through the bridge's escape hatch (R1.2) — `^A`, the
  command's own letter, and the answer to its prompt, exactly as a person
  would type them. Nothing is added to the game or the Borg (RULES 9). Such
  runs are marked interventions and never count in survival figures (D4).

A trial that the setup did not reach is `setup_failed` and counted apart. It
is never counted as a trial the character survived: that would be the easiest
way to make a probe say what one wants.
"""
import json
from pathlib import Path

from . import agent, executor, mind as mind_module, pins, signals

SCHEMA = 'borg-agent/probe@1'
PROBES = pins.ROOT / 'probes'
RESULTS = 'results'
# How many decisions a step may wait for the game to show what it promised.
SETUP_PATIENCE = 8
# The debug commands this harness knows how to drive, with the key the game's
# own debug table gives them (`cmd_debug*` in src/ui-game.c at the game pin).
STEPS = {
    'summon': {'key': 'n', 'prompt': 'Summon which monster?', 'argument': 'monster'},
    'depth': {'key': 'j', 'prompt': 'Jump to level', 'argument': 'depth'},
    'cure_all': {'key': 'a', 'prompt': None, 'argument': None},
    'detect_monsters': {'key': 'u', 'prompt': None, 'argument': None},
}
DEBUG_PREFIX = '\x01'
# The game asks once per character before it allows a debug command, and the
# answer is on the record: it sets NOSCORE_WIZARD (src/wiz-debug.c).
DEBUG_CONFIRMATION = 'debug commands'
PREDICATES = ('survived', 'killed_it_and_lived')
ARMS = ('action', 'control')
TRIAL_OVER = 'the situation is over: nothing of the probe is left to do'


class ProbeError(ValueError):
    """A probe cannot be run, or cannot be read, and why."""


class SetupFailed(Exception):
    """The situation the probe asked for never came about.

    Not a trial: a trial whose setup did not happen says nothing about the
    question, and counting it as a survival would be a lie with a number on
    it.
    """


# --- the probe file ---------------------------------------------------------

def load(path):
    """Read a probe definition and refuse it if it cannot be run."""
    import yaml

    from jsonschema import Draft202012Validator, FormatChecker

    path = Path(path)
    if not path.exists():
        candidate = PROBES / path.name
        if not candidate.exists():
            raise ProbeError(f'no probe at {path}')
        path = candidate
    text = path.read_text()
    document = yaml.safe_load(text) if path.suffix in ('.yaml', '.yml') else json.loads(text)
    return validate(document)


def validate(document):
    """Against `probe@1`, then the rules a schema cannot express."""
    from jsonschema import Draft202012Validator, FormatChecker

    if not isinstance(document, dict):
        raise ProbeError('a probe is a mapping')
    schema = json.loads((pins.ROOT / 'schemas' / 'probe@1.json').read_text())
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker())
                    .iter_errors(document), key=str)
    if errors:
        raise ProbeError('; '.join(f'{list(e.absolute_path)}: {e.message}' for e in errors[:4]))
    for step in document['setup'].get('steps') or ():
        if step['step'] not in STEPS:
            raise ProbeError(f'no setup step {step["step"]!r}; the steps are '
                             f'{sorted(STEPS)}')
        argument = STEPS[step['step']]['argument']
        if argument and step.get(argument) in (None, ''):
            raise ProbeError(f'the step {step["step"]!r} needs {argument!r}')
    seeds = document['trials']['seeds']
    if len(set(seeds)) != len(seeds):
        raise ProbeError('a seed is declared twice; the trials would not be independent')
    if document['setup']['kind'] == 'intervened' and not document['setup'].get('steps'):
        raise ProbeError('an intervened setup needs the steps that build the situation')
    if document['setup']['kind'] == 'natural' and document['setup'].get('steps'):
        raise ProbeError('a natural setup builds nothing: it finds the situation in play')
    return document


def keys_for(step):
    """The keys a setup step is typed as, in the order a person types them.

    One string per keypress the game answers: the debug prefix with the
    command's own letter, then the answer to its prompt. They cannot be sent as
    one string, because the game asks questions in between -- the debug
    confirmation on the first command of a character, and whatever the command
    itself asks ("Choose cave profile?" after a level jump) -- and a key queued
    behind a question is eaten by it.
    """
    known = STEPS[step['step']]
    argument = known['argument'] and str(step[known['argument']])
    keys = [DEBUG_PREFIX + known['key']]
    if argument:
        keys.append(f'{argument}\n')
    return keys


# --- one trial --------------------------------------------------------------

class ProbeChooser:
    """Builds the situation, checks it came about, then tries one arm of it.

    It holds no tactics and no thresholds: the setup is the probe's, the action
    is the probe's, and this only sequences them (R2, docs/SOURCES.md).
    """

    kind = 'probe'

    def __init__(self, probe, arm):
        if arm not in ARMS:
            raise ProbeError(f'no arm {arm!r}; the arms are {ARMS}')
        self.probe = probe
        self.arm = arm
        self.name = f'probe:{probe["id"]}:{arm}'
        self.steps = list(probe['setup'].get('steps') or ())
        self.pending = []
        self.answered = []
        self.done = []
        self.waited = 0
        self.ready = False
        self.monster = _expected_monster(probe)
        self.acted = 0
        self.saw_the_monster = False
        self.killed = False

    # --- what the setup promised --------------------------------------------

    def situation_is_there(self, observation):
        expect = self.probe['setup'].get('expect') or {}
        wanted = expect.get('monster_adjacent')
        if wanted:
            return any(_is(monster, wanted) and (monster.get('distance') or 99) <= 1
                       for monster in observation.get('monsters') or ())
        depth = expect.get('depth')
        if depth is not None:
            return (observation.get('character') or {}).get('depth') == depth
        return True                      # a probe that promises nothing is ready at once

    def setting_up(self):
        return bool(self.steps or self.pending) or not self.ready

    def act(self, observation):
        prompt = observation.get('prompt') or {}
        text = prompt.get('text') or ''
        # The game asks once per character before allowing a debug command, and
        # the answer is on the record: it sets NOSCORE_WIZARD.
        if DEBUG_CONFIRMATION in text:
            self.answered.append('the debug confirmation')
            return mind_module.action('keys', 'yes: this probe is an intervention (D4)',
                                      keys={'keys': 'y', 'why': 'the game asks before it '
                                                               'allows a debug command'})
        # Anything else the game asks while the situation is being built gets
        # the plain answer: no. A level jump asks "Choose cave profile?", and a
        # probe that chose one would be arranging the dungeon as well as the
        # monster.
        if self.setting_up() and prompt.get('kind') == 'yes_no':
            self.answered.append(text.strip()[:60])
            return mind_module.action('keys', 'no: the probe arranges nothing it did not say',
                                      keys={'keys': 'n',
                                            'why': 'a question the setup did not ask for'})
        if self.pending or self.steps:
            if not self.pending:
                step = self.steps.pop(0)
                self.done.append(step)
                self.pending = keys_for(step)
            keys = self.pending.pop(0)
            return mind_module.action(
                'keys', f'set up: {self.done[-1]["step"]}',
                keys={'keys': keys,
                      'why': "the game's own debug command, typed as a person types it"})
        if not self.ready:
            if self.situation_is_there(observation):
                self.ready = True
            else:
                self.waited += 1
                if self.waited > SETUP_PATIENCE:
                    raise SetupFailed(
                        f'the situation never came about after {self.waited} decisions: '
                        f'{json.dumps(self.probe["setup"].get("expect") or {})}')
                return mind_module.action('command', 'wait for the situation to settle',
                                          command={'name': 'stay'})
        if self.monster:
            if any(_is(monster, self.monster) for monster in observation.get('monsters') or ()):
                self.saw_the_monster = True
            if killed(observation.get('messages') or (), self.monster):
                # Dead, and the character is alive to see it: this trial has
                # answered the question. Absence alone proves nothing -- a
                # monster out of sight is not a monster dead, and the control
                # arm walks away from it on purpose.
                self.killed = True
                raise signals.CannotAct(TRIAL_OVER)
        self.acted += 1
        return _arm_action(self.probe, self.arm)


def _expected_monster(probe):
    return ((probe['setup'].get('expect') or {}).get('monster_adjacent')
            or next((step.get('monster') for step in probe['setup'].get('steps') or ()
                     if step['step'] == 'summon'), None))


def _is(monster, name):
    return (monster.get('name') or '').lower() == str(name).lower()


# How the game says a monster is dead (`mon-utils.c` at the game pin).
DEATHS = ('you have slain', 'you have killed', 'you have destroyed', 'dies.', 'is destroyed')


def killed(messages, monster):
    """Did the game report this monster's death in these messages?"""
    name = str(monster).lower()
    for message in messages:
        line = str(message).lower()
        if name in line and any(word in line for word in DEATHS):
            return True
    return False


def _arm_action(probe, arm):
    asked = probe[arm]
    reason = f'{arm} under test: {probe["id"]}'
    if 'primitive' in asked:
        return mind_module.action('primitive', reason,
                                  primitive=dict(asked['primitive']))
    return mind_module.action('command', reason, command=dict(asked['command']))


def trial(build_out, probe, seed, arm, output, timeout=900, stall_timeout=120, lock=True,
          log=print):
    """One seed, one arm. An ordinary run: recorded, and replayable (R5)."""
    chooser = ProbeChooser(probe, arm)
    playing = executor.ExecutingMind(chooser, name=chooser.name)
    setup = probe['setup']
    try:
        result = agent.play_with_mind(
            build_out, seed=seed, cap=probe['trials']['cap'], output=output, mind=playing,
            from_turn=setup.get('take_over_at'), timeout=timeout, stall_timeout=stall_timeout,
            lock=lock, log=lambda *a: None)
    except SetupFailed as problem:
        log(json.dumps({'seed': seed, 'arm': arm, 'trial': 'setup_failed',
                        'why': str(problem)}))
        return {'seed': seed, 'arm': arm, 'setup': 'failed', 'why': str(problem),
                'counts': False, 'success': None}
    judged = judge(probe, result, output)
    log(json.dumps({'seed': seed, 'arm': arm, 'outcome': result['outcome'],
                    'turn': judged['last_turn'], 'killed_it': judged['killed_it'],
                    'success': judged['success']}))
    return {'seed': seed, 'arm': arm, 'setup': 'done', 'counts': True,
            'run': str(output), 'run_id': result.get('run_id') or Path(output).name,
            'outcome': result['outcome'], 'cause': result.get('cause'),
            'final_turn': result.get('final_turn'), 'decisions': result.get('decisions'),
            'setup_answered': getattr(chooser, 'answered', []),
            **judged}


def judge(probe, result, output):
    """Did this trial succeed, by the probe's own predicate?

    Both predicates are decided from what the run wrote, never from the mind's
    own account of it.
    """
    predicate = probe['success']
    alive = result['outcome'] != 'death'
    monster = _expected_monster(probe)
    seen = read_observations(output, monster)
    judged = {'predicate': predicate, 'last_turn': seen['last_turn'],
              'killed_it': seen['killed']}
    if predicate == 'survived':
        return {**judged, 'success': alive}
    return {**judged, 'success': bool(alive and seen['killed'])}


def read_observations(output, monster):
    """The turn the trial really reached, and whether the monster died.

    `final_turn` in a run's result is the last *sampled* state (the observer
    writes one every hundred Borg decisions), so a short trial can report turn
    1 for a game that reached turn 109. The observations are what the agent
    actually saw.
    """
    path = Path(output) / agent.OBSERVATION_LOG
    last_turn, died, saw = 0, False, False
    if not path.exists():
        return {'last_turn': 0, 'killed': False, 'saw_it': False}
    with path.open() as lines:
        for line in lines:
            if not line.strip():
                continue
            observation = json.loads(line)
            last_turn = observation.get('turn') or last_turn
            if monster:
                if any(_is(seen, monster) for seen in observation.get('monsters') or ()):
                    saw = True
                if killed(observation.get('messages') or (), monster):
                    died = True
    return {'last_turn': last_turn, 'killed': died, 'saw_it': saw}


# --- the probe --------------------------------------------------------------

def run(build_out, probe, output, arms=ARMS, timeout=900, stall_timeout=120, lock=True,
        log=print):
    """Every declared seed, every arm. The counts are the answer."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    trials = []
    for seed in probe['trials']['seeds']:
        for arm in arms:
            trials.append(trial(build_out, probe, seed, arm, output / f'{arm}-seed{seed}',
                                timeout=timeout, stall_timeout=stall_timeout, lock=lock,
                                log=log))
    counted = {arm: [t for t in trials if t['arm'] == arm and t['counts']] for arm in arms}
    failed = [t for t in trials if not t['counts']]
    if not any(counted.values()):
        raise ProbeError(
            f'every trial failed its setup, so the probe answers nothing: '
            f'{failed[0]["why"] if failed else "no trials ran"}')
    isolated = (not result_arms_overlap(counted)) if counted else True
    result = {
        'schema': 'borg-agent/probe-result@1',
        'probe': probe['id'],
        'question': probe['question'],
        'predicate': probe['success'],
        'intervention': probe['setup']['kind'] == 'intervened',
        'seeds': list(probe['trials']['seeds']),
        'cap': probe['trials']['cap'],
        'arms': {arm: {'trials': len(counted[arm]),
                       'successes': len([t for t in counted[arm] if t['success']]),
                       'deaths': len([t for t in counted[arm] if t['outcome'] == 'death']),
                       # How often the monster died in this arm. In the control
                       # arm it should be none: if the control killed it too,
                       # the arms did not differ in the way the probe meant and
                       # the result says so rather than claiming a comparison.
                       'monster_died': len([t for t in counted[arm] if t.get('killed_it')])}
                 for arm in arms},
        'setup_failed': len(failed),
        # True when the control really was a control: the monster the probe
        # summoned survived the control arm. False means the two arms both
        # ended the situation, so the counts compare less than they look.
        'control_isolated_the_action': isolated,
        'trials': trials,
    }
    (output / 'probe-result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    log(json.dumps({'probe': probe['id'],
                    **{arm: f'{result["arms"][arm]["successes"]} of '
                            f'{result["arms"][arm]["trials"]}' for arm in arms},
                    'setup_failed': result['setup_failed']}))
    return result


def result_arms_overlap(counted):
    """Did the control arm end the situation as well as the action arm?"""
    return any(trial.get('killed_it') for trial in counted.get('control') or ())


def claim_from(result, probe, claim_id=None, statement=None, created=None):
    """The claim a probe result makes, with the status the harness sets.

    A probe is the one promoter of a claim that is not another model (R4.3), so
    this is where `quantified N of M` is written — never by a model, which may
    propose a probe and never score one. One probe gives `supported`;
    `corroborated` waits for a second probe on fresh seeds.
    """
    from datetime import datetime, timezone

    arm = result['arms']['action']
    if not arm['trials']:
        raise ProbeError('the action arm ran no trial that counted')
    created = created or datetime.now(timezone.utc).isoformat(timespec='seconds')
    trials = [t for t in result['trials'] if t['arm'] == 'action' and t['counts']]
    return {
        'schema': 'borg-agent/claim@1',
        'id': claim_id or f'{probe["id"]}-probe',
        'statement': statement or probe.get('statement') or probe['question'],
        'area': probe['area'],
        'scope': dict(probe['scope']),
        'status': 'supported',
        'basis': {
            'kind': 'quantified',
            'trials': arm['trials'],
            'successes': arm['successes'],
            'reference': f'probe {probe["id"]}, seeds {result["seeds"]}, '
                         f'cap {result["cap"]}'
                         + (', an intervention (D4)' if result['intervention'] else ''),
        },
        'evidence': [{'kind': 'run', 'run_id': t['run_id'], 'seed': t['seed'],
                      'turn': t.get('last_turn') or 0,
                      'note': f'{t["outcome"]}'
                              + (f': {t["cause"]}' if t.get('cause') else '')}
                     for t in trials],
        'confidence': {
            'rests_on': f'{arm["successes"]} of {arm["trials"]} counted trials of probe '
                        f'{probe["id"]}, the control arm '
                        f'{result["arms"]["control"]["successes"]} of '
                        f'{result["arms"]["control"]["trials"]}'
                        + (f'; {result["setup_failed"]} trials never reached the situation '
                           f'and are not counted' if result['setup_failed'] else ''),
            'alternatives_ruled_out': [
                'A different situation: every trial checked that the situation the probe '
                'asked for was there before the action was tried.',
            ] + ([
                'The action not mattering: the same seeds were played with the control '
                'action, which left the monster alive.',
            ] if result.get('control_isolated_the_action') else [
                'NOT ruled out: the control arm ended the situation too (the monster died '
                'in %d of its %d trials), so these counts do not separate the action from '
                'simply being there.' % (result['arms']['control']['monster_died'],
                                         result['arms']['control']['trials']),
            ]),
        },
        'produced_by': {'mind': 'probe', 'run_id': probe['id']},
        'reviews': [{'by': trials[0]['run_id'], 'family': None, 'verdict': 'agree',
                     'created': created,
                     'note': f'counted by the probe itself: {arm["successes"]} of '
                             f'{arm["trials"]}'}],
        'created': created,
        'phase': 1,
        'sources': ['own-play'],
        'engine': 'c-4.2.6',
    }
