"""The rules a schema cannot express: named true state, and claim promotion."""
import json
from pathlib import Path

import pytest

from borg_agent import checks

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'schemas/examples'


def claim(**changes):
    base = json.loads((EXAMPLES / 'claim/valid-hypothesis-from-one-death.json').read_text())
    base.update(changes)
    return base


# --- R1.1: a true-state field is named as such ------------------------------

def test_an_observation_without_true_state_has_nothing_to_declare():
    assert checks.check_observation({'turn': 1}) == []


def test_true_state_must_name_what_it_carries():
    problems = checks.check_observation(
        {'true_state': {'fields': ['monster_hp'], 'monster_hp': 11, 'monster_sleep': 10}})
    assert problems == ["true_state carries 'monster_sleep' without naming it in fields"]


def test_true_state_must_not_name_what_it_does_not_carry():
    problems = checks.check_observation({'true_state': {'fields': ['monster_hp']}})
    assert problems == ["true_state names 'monster_hp' in fields but does not carry it"]


def test_a_well_formed_true_state_block_passes():
    assert checks.check_observation(
        {'true_state': {'fields': ['monster_hp', 'monster_sleep'],
                        'monster_hp': 11, 'monster_sleep': 10}}) == []


def test_every_observation_example_declares_its_true_state():
    for path in (EXAMPLES / 'observation').glob('valid-*.json'):
        assert checks.check_observation(json.loads(path.read_text())) == [], path.name


# --- R4.3: a model never promotes its own claim ------------------------------

def test_a_model_claim_names_itself():
    problems = checks.check_claim(claim(produced_by={'mind': 'model'}))
    assert any('model' in problem for problem in problems)
    assert any('family' in problem for problem in problems)


def test_a_review_by_the_producers_own_family_does_not_promote():
    # The review the reviewer asked about: same family, agreeing, and so not
    # enough to move a claim past hypothesis.
    problems = checks.check_claim(claim(
        status='corroborated',
        produced_by={'mind': 'model', 'model': 'qwen3.8-max', 'family': 'qwen'},
        reviews=[{'by': 'qwen3.8-flash', 'family': 'qwen', 'verdict': 'agree',
                  'created': '2026-11-09T13:30:00Z'}]))
    assert problems and any("own family" in problem for problem in problems)


def test_a_review_by_another_family_does_promote():
    assert checks.check_claim(claim(
        status='corroborated',
        produced_by={'mind': 'model', 'model': 'qwen3.8-max', 'family': 'qwen'},
        reviews=[{'by': 'glm-5.3', 'family': 'glm', 'verdict': 'agree',
                  'created': '2026-11-09T13:30:00Z'}])) == []


def test_a_disagreeing_review_does_not_promote():
    problems = checks.check_claim(claim(
        status='supported',
        produced_by={'mind': 'model', 'model': 'qwen3.8-max', 'family': 'qwen'},
        reviews=[{'by': 'glm-5.3', 'family': 'glm', 'verdict': 'disagree',
                  'created': '2026-11-09T13:30:00Z'}]))
    assert problems and 'needs counted trials' in problems[0]


def test_counted_trials_promote_without_a_review():
    assert checks.check_claim(claim(
        status='supported',
        basis={'kind': 'quantified', 'trials': 20, 'successes': 3},
        produced_by={'mind': 'probe', 'run_id': 'probe-1'})) == []


def test_a_probe_review_promotes_although_it_has_no_family():
    # The probe names a run this claim's evidence carries, which is what makes
    # it checkable (milestone 3 review, finding 10).
    assert checks.check_claim(claim(
        status='corroborated',
        produced_by={'mind': 'model', 'model': 'qwen3.8-max', 'family': 'qwen'},
        evidence=[{'kind': 'run', 'run_id': 'probe-20261109-floating-eye', 'seed': 7,
                   'turn': 100, 'note': 'the probe itself'}],
        reviews=[{'by': 'probe-20261109-floating-eye', 'family': None, 'verdict': 'agree',
                  'created': '2026-11-09T13:30:00Z'}])) == []


def test_an_invented_probe_review_does_not_promote():
    """Milestone 3 review, finding 10.

    A review with no family is a probe, and nothing checked that the probe
    existed: `{'verdict': 'agree', 'family': None}` was enough to promote a
    claim. Mode C (T22) rests on this rule, so it is closed before T22 lands.
    """
    problems = checks.check_claim(claim(
        status='corroborated',
        produced_by={'mind': 'model', 'model': 'qwen3.8-max', 'family': 'qwen'},
        reviews=[{'by': 'probe-that-never-ran', 'family': None, 'verdict': 'agree',
                  'created': '2026-11-09T13:30:00Z'}]))
    assert problems and 'names no run' in problems[-1]


def test_a_model_does_not_call_its_own_claim_documented():
    problems = checks.check_claim(claim(
        status='documented', basis={'kind': 'manual', 'reference': 'docs/command.rst'},
        produced_by={'mind': 'model', 'model': 'qwen3.8-max', 'family': 'qwen'}))
    assert problems and 'documented' in problems[0]
    # The same claim, read by a person or written by the harness, is fine.
    assert checks.check_claim(claim(
        status='documented', basis={'kind': 'manual', 'reference': 'docs/command.rst'},
        produced_by={'mind': 'harness'})) == []


def test_a_model_cannot_promote_its_own_claim_by_itself():
    problems = checks.check_claim(claim(
        status='supported',
        produced_by={'mind': 'model', 'model': 'qwen3.8-max', 'family': 'qwen'}))
    assert problems and 'R4.3' in problems[0]


def test_more_successes_than_trials_is_refused():
    problems = checks.check_claim(claim(
        basis={'kind': 'quantified', 'trials': 10, 'successes': 11}))
    assert problems == ['a quantified basis claims 11 successes of 10 trials']


def test_every_claim_example_obeys_the_rules_the_schema_cannot_carry():
    for path in (EXAMPLES / 'claim').glob('valid-*.json'):
        assert checks.check_claim(json.loads(path.read_text())) == [], path.name


def test_enforce_raises_with_everything_that_is_wrong():
    with pytest.raises(ValueError, match='names'):
        checks.enforce(checks.check_observation({'true_state': {'fields': ['a']}}),
                       'observation 3')
    checks.enforce([])
