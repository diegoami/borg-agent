"""The four schemas of T02, the probe of T22, and every example beside them.

Each schema has valid examples that must validate and invalid ones that must
not. The invalid examples carry the rule each breaks in their file name, so a
reader can see what the schema is for without reading the schema.
"""
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / 'schemas'
EXAMPLES = SCHEMAS / 'examples'
NAMES = ('observation', 'action', 'run-record', 'claim', 'probe')
# The zoo's outcome classes (docs/DESIGN.md at the borg-zoo pin), plus this
# repository's own, which R5 names.
ZOO_OUTCOMES = {'death', 'completion', 'turn_cap', 'stalled', 'wall_timeout', 'crash',
                'harness_failure', 'config_error', 'decision_cap'}
# 'saved' is the runner's own, for a run stopped at a save (T08 needs it).
AGENT_OUTCOMES = {'agent_stopped', 'budget_cap', 'saved'}


def load(path):
    return json.loads(path.read_text())


def schema_path(name):
    return SCHEMAS / f'{name}@1.json'


def validator(name):
    schema = load(schema_path(name))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def examples(name, good):
    prefix = 'valid-' if good else 'invalid-'
    return sorted(p for p in (EXAMPLES / name).glob(prefix + '*.json'))


@pytest.mark.parametrize('name', NAMES)
def test_the_schema_itself_is_valid_and_versioned(name):
    schema = load(schema_path(name))
    assert schema['$schema'] == 'https://json-schema.org/draft/2020-12/schema'
    assert schema['$id'].endswith(f'/{name}@1.json')
    assert schema['properties']['schema']['const'] == f'borg-agent/{name}@1'
    assert 'required' in schema and 'schema' in schema['required']
    assert schema['description'] and schema['title']
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize('name', NAMES)
def test_each_schema_has_valid_and_invalid_examples(name):
    assert len(examples(name, True)) >= 1, name
    assert len(examples(name, False)) >= 2, name


@pytest.mark.parametrize('path', [p for name in NAMES for p in examples(name, True)],
                         ids=lambda p: f'{p.parent.name}/{p.name}')
def test_valid_examples_validate(path):
    errors = sorted(validator(path.parent.name).iter_errors(load(path)), key=str)
    assert not errors, [f'{list(e.absolute_path)}: {e.message}' for e in errors]


@pytest.mark.parametrize('path', [p for name in NAMES for p in examples(name, False)],
                         ids=lambda p: f'{p.parent.name}/{p.name}')
def test_invalid_examples_are_rejected(path):
    assert not validator(path.parent.name).is_valid(load(path)), \
        f'{path.name} should break the rule its name describes'


def test_the_outcome_vocabulary_is_the_zoos_plus_budget_cap():
    # R5: the zoo's vocabulary, with borg_stopped renamed agent_stopped.
    kinds = set(load(schema_path('run-record'))['properties']['outcome']
                ['properties']['kind']['enum'])
    assert kinds == ZOO_OUTCOMES | AGENT_OUTCOMES
    assert 'borg_stopped' not in kinds


def test_the_run_record_takes_its_model_from_a_profile():
    # Decision D7: no other way of choosing a model, and never a key.
    mind = load(schema_path('run-record'))['properties']['mind']
    assert set(mind['properties']['chosen_by']['enum']) == {
        'profile', 'local override', 'environment', 'not-applicable'}
    assert mind['additionalProperties'] is False
    assert not [field for field in mind['properties'] if re.search('key', field, re.I)]
    for job in ('play', 'consolidate', 'review'):
        assert job in mind['properties']['job']['enum']


def test_the_observation_names_any_true_state_field():
    # R1.1: a true-state field is named as such, and off by default.
    observation = load(schema_path('observation'))
    true_state = observation['properties']['true_state']
    assert true_state['required'] == ['fields']
    assert 'true_state' not in observation['required']
    # The ordinary monster entry has no room for what the player cannot know.
    monster = observation['properties']['monsters']['items']
    assert monster['additionalProperties'] is False
    assert 'hp' not in monster['properties']


def test_the_claim_follows_the_lifecycle_of_r4():
    claim = load(schema_path('claim'))
    assert set(claim['properties']['status']['enum']) == {
        'unknown', 'documented', 'hypothesis', 'supported', 'corroborated', 'refuted', 'contested'}
    assert set(claim['properties']['area']['enum']) == {
        'monster', 'item', 'spell', 'class', 'race', 'town', 'dungeon', 'mechanic',
        'danger', 'tactic', 'readiness'}
    # Decision D8: the agent may read the game and Borg source, the
    # specification, the deaths and the issues, so each has a basis of its own
    # and a 'static:' basis must name its reference.
    assert set(claim['properties']['basis']['properties']['kind']['enum']) == {
        'manual', 'observed', 'quantified', 'intervened', 'static:game-source',
        'static:borg-source', 'static:borg-spec', 'static:deaths', 'static:issue',
        'static:strategy-manual', 'static:user-manual'}
    assert set(claim['properties']['sources']['items']['enum']) == {
        'manual', 'in-game', 'own-play', 'knowledge-base', 'game-source',
        'borg-source', 'borg-spec', 'deaths', 'issue', 'zoo-results', 'strategy-manual',
        'user-manual'}
    for required in ('evidence', 'confidence', 'phase', 'sources', 'engine'):
        assert required in claim['required']
    assert claim['properties']['evidence']['minItems'] == 1


def test_no_example_carries_a_key_or_a_token():
    for path in EXAMPLES.rglob('*.json'):
        if path.name.startswith('invalid-a-key'):
            continue  # that one exists to be rejected
        text = path.read_text()
        # 'keys' is the raw-keypress escape hatch, not a credential.
        assert not re.search(r'"(?:[\w.]*api[_-]?key[\w.]*|key|secret|password|authorization)"\s*:',
                             text, re.I), path.name
        assert 'sk-' not in text, path.name
