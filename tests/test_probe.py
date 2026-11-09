"""Mode C: one question, answered in counted trials (T22)."""
import json
import os
from pathlib import Path

import pytest

from borg_agent import build, checks, knowledge, probe, signals

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / 'probes/floating-eye-melee.yaml'


def definition(**changes):
    document = probe.load(REAL)
    document.update(changes)
    return document


def observation(decision=0, turn=101, monsters=(), prompt=None, messages=(), depth=1):
    return {
        'schema': 'borg-agent/observation@1', 'run_id': 'probe-test', 'decision': decision,
        'turn': turn,
        'character': {'race': 'Human', 'class': 'Warrior', 'level': 1, 'hp': 20,
                      'max_hp': 20, 'depth': depth, 'gold': 0},
        'map': {'player': {'x': 2, 'y': 1}, 'origin': {'x': 0, 'y': 0},
                'rows': ['#####', '#.@.#', '#####']},
        'monsters': list(monsters), 'inventory': [], 'equipment': [],
        'messages': list(messages), 'prompt': prompt or {'kind': 'none', 'text': ''},
    }


def eye(distance=1):
    return {'letter': 'e', 'name': 'floating eye', 'x': 3, 'y': 1, 'distance': distance,
            'asleep': None, 'health': None}


# --- the probe file ---------------------------------------------------------

def test_the_repositorys_probe_loads_and_obeys_every_rule():
    loaded = probe.load(REAL)
    assert loaded['id'] == 'floating-eye-melee'
    assert loaded['setup']['kind'] == 'intervened'
    assert len(loaded['trials']['seeds']) >= 10


def test_a_probe_can_be_named_rather_than_pathed():
    assert probe.load('floating-eye-melee.yaml')['id'] == 'floating-eye-melee'


def test_a_probe_that_is_not_there_says_so():
    with pytest.raises(probe.ProbeError, match='no probe at'):
        probe.load('probes/there-is-no-such-probe.yaml')


def test_a_setup_step_the_harness_cannot_type_is_refused():
    # The schema's enum catches it first; `probe.STEPS` is the backstop for a
    # step the schema allows and the harness cannot type.
    with pytest.raises(probe.ProbeError, match='make_powerful'):
        probe.validate(definition(setup={'kind': 'intervened',
                                         'steps': [{'step': 'make_powerful'}]}))
    assert 'make_powerful' not in probe.STEPS


def test_a_step_without_its_argument_is_refused():
    with pytest.raises(probe.ProbeError, match="needs 'monster'"):
        probe.validate(definition(setup={'kind': 'intervened', 'steps': [{'step': 'summon'}]}))


def test_a_seed_declared_twice_is_refused():
    with pytest.raises(probe.ProbeError, match='non-unique|declared twice'):
        probe.validate(definition(trials={'seeds': [1, 1, 2], 'cap': 100}))


def test_an_intervened_setup_must_say_what_it_does():
    with pytest.raises(probe.ProbeError, match="'steps' is a required property"):
        probe.validate(definition(setup={'kind': 'intervened'}))


def test_a_natural_setup_builds_nothing():
    with pytest.raises(probe.ProbeError, match='builds nothing'):
        probe.validate(definition(setup={'kind': 'natural',
                                         'steps': [{'step': 'cure_all'}]}))


# --- the keys a step is typed as --------------------------------------------

def test_a_step_is_typed_one_keypress_at_a_time():
    """The game asks questions between the keys, and a key queued behind a
    question is eaten by it, so a step is a list and not a string."""
    assert probe.keys_for({'step': 'depth', 'depth': 1}) == ['\x01j', '1\n']
    assert probe.keys_for({'step': 'summon', 'monster': 'Floating eye'}) == [
        '\x01n', 'Floating eye\n']
    assert probe.keys_for({'step': 'cure_all'}) == ['\x01a']


def test_the_debug_confirmation_is_answered_yes_and_everything_else_no():
    chooser = probe.ProbeChooser(probe.load(REAL), 'action')
    asked = chooser.act(observation(prompt={'kind': 'yes_no',
                                            'text': 'Are you sure you want to use the '
                                                    'debug commands? [y/n]'}))
    assert asked['keys']['keys'] == 'y'
    # A level jump asks "Choose cave profile?"; a probe that chose one would be
    # arranging the dungeon as well as the monster.
    asked = chooser.act(observation(prompt={'kind': 'yes_no',
                                            'text': 'Choose cave profile? [y/n]'}))
    assert asked['keys']['keys'] == 'n'


def test_the_steps_come_out_in_order_then_the_action():
    chooser = probe.ProbeChooser(probe.load(REAL), 'action')
    sent = []
    for decision in range(4):
        answer = chooser.act(observation(decision=decision))
        sent.append(answer['keys']['keys'])
    assert sent == ['\x01j', '1\n', '\x01n', 'Floating eye\n']
    # The situation is not there yet, so it waits rather than acting.
    waiting = chooser.act(observation(decision=4))
    assert waiting['kind'] == 'command' and waiting['command']['name'] == 'stay'
    # And once the eye is adjacent, the arm under test is what it answers.
    acting = chooser.act(observation(decision=5, monsters=[eye()]))
    assert acting['kind'] == 'primitive' and acting['primitive']['name'] == 'fight_nearest'


def test_the_control_arm_answers_with_the_control():
    chooser = probe.ProbeChooser(probe.load(REAL), 'control')
    for decision in range(4):
        chooser.act(observation(decision=decision))
    chooser.act(observation(decision=4, monsters=[eye()]))
    acting = chooser.act(observation(decision=5, monsters=[eye()]))
    assert acting['primitive']['name'] == 'explore_floor'


def test_an_arm_that_does_not_exist_is_refused():
    with pytest.raises(probe.ProbeError, match='no arm'):
        probe.ProbeChooser(probe.load(REAL), 'whatever')


# --- a setup that did not take ----------------------------------------------

def test_a_situation_that_never_came_about_is_not_a_trial():
    """The easiest way to make a probe say what one wants is to count a trial
    whose setup failed as a trial the character survived."""
    chooser = probe.ProbeChooser(probe.load(REAL), 'action')
    for decision in range(4):
        chooser.act(observation(decision=decision))
    with pytest.raises(probe.SetupFailed, match='never came about'):
        for decision in range(4, 4 + probe.SETUP_PATIENCE + 2):
            chooser.act(observation(decision=decision))      # no eye, ever


def test_a_monster_merely_out_of_sight_does_not_end_a_trial():
    # A monster out of sight is not a monster dead -- and the control arm walks
    # away from it on purpose.
    chooser = probe.ProbeChooser(probe.load(REAL), 'action')
    for decision in range(4):
        chooser.act(observation(decision=decision))
    chooser.act(observation(decision=4, monsters=[eye()]))
    still_going = chooser.act(observation(decision=5, monsters=[]))
    assert still_going['kind'] == 'primitive'
    assert chooser.killed is False


def test_the_trial_ends_when_the_game_says_the_monster_is_dead():
    chooser = probe.ProbeChooser(probe.load(REAL), 'action')
    for decision in range(4):
        chooser.act(observation(decision=decision))
    chooser.act(observation(decision=4, monsters=[eye()]))
    with pytest.raises(signals.CannotAct, match='the situation is over'):
        chooser.act(observation(decision=5, monsters=[eye()],
                                messages=['You hit the floating eye.',
                                          'You have slain the floating eye.']))
    assert chooser.killed is True


@pytest.mark.parametrize('message,dead', [
    ('You have slain the floating eye.', True),
    ('The floating eye dies.', True),
    ('You hit the floating eye.', False),
    ('You have slain the rock lizard.', False),
])
def test_what_counts_as_the_monster_dying(message, dead):
    assert probe.killed([message], 'floating eye') is dead


# --- the counts, and the claim ----------------------------------------------

def a_result(action_successes=9, control_successes=9, control_killed=0, setup_failed=0,
             trials=10):
    def arm_trials(arm, successes, killed):
        return [{'seed': 10 + i, 'arm': arm, 'counts': True, 'success': i < successes,
                 'killed_it': i < killed, 'outcome': 'turn_cap' if i < successes else 'death',
                 'cause': None if i < successes else 'a floating eye',
                 'run_id': f'{arm}-seed{10 + i}', 'last_turn': 500 + i}
                for i in range(trials)]
    return {
        'schema': 'borg-agent/probe-result@1', 'probe': 'floating-eye-melee',
        'question': 'Can a level-1 Human Warrior melee an adjacent floating eye and live?',
        'predicate': 'survived', 'intervention': True, 'seeds': list(range(11, 11 + trials)),
        'cap': 1200,
        'arms': {'action': {'trials': trials, 'successes': action_successes, 'deaths': 0,
                            'monster_died': trials},
                 'control': {'trials': trials, 'successes': control_successes, 'deaths': 0,
                             'monster_died': control_killed}},
        'setup_failed': setup_failed,
        'control_isolated_the_action': control_killed == 0,
        'trials': (arm_trials('action', action_successes, trials)
                   + arm_trials('control', control_successes, control_killed)),
    }


def test_the_claim_a_probe_makes_is_quantified_and_the_harness_set_it():
    result = a_result()
    claim = probe.claim_from(result, probe.load(REAL), created='2026-11-09T14:00:00Z')
    assert claim['basis'] == {'kind': 'quantified', 'trials': 10, 'successes': 9,
                              'reference': claim['basis']['reference']}
    assert 'an intervention (D4)' in claim['basis']['reference']
    assert claim['status'] == 'supported'           # one probe; a second corroborates
    assert claim['produced_by'] == {'mind': 'probe', 'run_id': 'floating-eye-melee'}
    # The guard a model cannot pass: nothing here is a model's word.
    assert checks.check_claim(claim) == []
    # The probe's own review names a run the evidence carries, which is what
    # makes it checkable (the milestone 3 review's finding 10).
    assert claim['reviews'][0]['by'] == claim['evidence'][0]['run_id']


def test_the_claim_goes_into_the_store_as_the_harness_wrote_it(tmp_path):
    store = knowledge.Store(root=tmp_path / 'knowledge')
    claim = probe.claim_from(a_result(), probe.load(REAL), created='2026-11-09T14:00:00Z')
    stored = store.add(claim)
    assert stored['status'] == 'supported'          # not lowered: no model wrote this
    assert store.all() == [stored]


def test_a_control_that_killed_it_too_is_said_out_loud():
    """A control arm that ends the situation as well is not a control."""
    honest = probe.claim_from(a_result(control_killed=9), probe.load(REAL),
                              created='2026-11-09T14:00:00Z')
    ruled_out = ' '.join(honest['confidence']['alternatives_ruled_out'])
    assert 'NOT ruled out' in ruled_out and '9 of its 10' in ruled_out
    clean = probe.claim_from(a_result(control_killed=0), probe.load(REAL),
                             created='2026-11-09T14:00:00Z')
    assert 'NOT ruled out' not in ' '.join(clean['confidence']['alternatives_ruled_out'])


def test_a_trial_that_failed_its_setup_is_counted_apart():
    claim = probe.claim_from(a_result(setup_failed=3), probe.load(REAL),
                             created='2026-11-09T14:00:00Z')
    assert 'never reached the situation' in claim['confidence']['rests_on']


def test_a_probe_with_no_counted_trial_answers_nothing():
    with pytest.raises(probe.ProbeError, match='ran no trial that counted'):
        probe.claim_from(a_result(trials=0), probe.load(REAL))


# --- the gate ---------------------------------------------------------------

@pytest.mark.slow
def test_a_probe_runs_end_to_end_and_counts_what_happened(tmp_path):
    """T22's gate: the game's own debug commands build the situation, the arms
    are played on the same seeds, and the counts come out of the runs.

    Three seeds, not the ten the real probe declares, because the gate is about
    the mechanism rather than the answer.
    """
    out = build.prepare(log=lambda *a: None)
    lock = not os.environ.get('BORG_AGENT_NO_LOCK')
    small = definition(trials={'seeds': [11, 12, 13], 'cap': 400})
    result = probe.run(out, small, tmp_path / 'probe', lock=lock, log=lambda *a: None)

    assert result['setup_failed'] == 0, result['trials']
    for arm in ('action', 'control'):
        assert result['arms'][arm]['trials'] == 3, result['arms']
    # The action arm fought the eye: the game reported it dead in every trial.
    assert result['arms']['action']['monster_died'] == 3
    # Every trial is a run of its own, recorded where the result says.
    for trial in result['trials']:
        assert Path(trial['run']).joinpath('observations.jsonl').exists()
        assert trial['last_turn'] >= small['setup']['take_over_at']
    assert json.loads((tmp_path / 'probe/probe-result.json').read_text()) == result

    claim = probe.claim_from(result, small, created='2026-11-09T14:00:00Z')
    assert claim['basis']['trials'] == 3
    assert checks.check_claim(claim) == []
