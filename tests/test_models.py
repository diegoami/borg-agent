"""models.yaml and its loader (T06): the only model rule here (D7)."""
import json
from pathlib import Path

import pytest
import yaml

from borg_agent import models

ROOT = Path(__file__).resolve().parents[1]

CONFIGURATION = {
    'schema': 'borg-agent/models@1',
    'default_profile': 'house',
    'providers': {
        'house': {'base_url': 'https://house.example/v1', 'api_key_env': 'HOUSE_KEY',
                  'source': 'https://house.example/docs'},
        'other': {'base_url': 'https://other.example/v1', 'api_key_env': 'OTHER_KEY',
                  'source': 'https://other.example/docs'},
    },
    'profiles': {
        'house': {
            'play': {'provider': 'house', 'model': 'small', 'family': 'alpha', 'context_k': 64},
            'consolidate': {'provider': 'house', 'model': 'big', 'family': 'alpha'},
            'review': {'provider': 'other', 'model': 'judge', 'family': 'beta'},
        },
        'away': {
            'play': {'provider': 'other', 'model': 'away-small', 'family': 'beta'},
            'consolidate': {'provider': 'other', 'model': 'away-big', 'family': 'beta'},
            'review': {'provider': 'house', 'model': 'small', 'family': 'alpha'},
        },
    },
    'trial': {
        'play': [{'provider': 'house', 'model': 'small', 'family': 'alpha'}],
    },
}


def configured(tmp_path, change=None, local=None):
    """A root holding a models.yaml, and optionally a models.local.yaml."""
    data = json.loads(json.dumps(CONFIGURATION))
    if change:
        change(data)
    (tmp_path / models.MODELS_FILE).write_text(yaml.safe_dump(data, sort_keys=False))
    if local is not None:
        (tmp_path / models.LOCAL_FILE).write_text(yaml.safe_dump(local, sort_keys=False))
    return tmp_path


# --- the three ways of choosing a profile -----------------------------------

def test_the_default_profile_is_the_fallback(tmp_path):
    loaded = models.load(configured(tmp_path), environ={})
    assert loaded.profile == 'house'
    assert all(choice.chosen_by == models.BY_PROFILE for choice in loaded.jobs.values())


def test_models_local_yaml_switches_the_profile(tmp_path):
    loaded = models.load(configured(tmp_path, local={'profile': 'away'}), environ={})
    assert loaded.profile == 'away'
    assert loaded['play'].model == 'away-small'
    assert loaded.models_local_sha256 and len(loaded.models_local_sha256) == 64


def test_the_environment_wins_over_both(tmp_path):
    root = configured(tmp_path, local={'profile': 'house'})
    loaded = models.load(root, environ={'BORG_AGENT_PROFILE': 'away'})
    assert loaded.profile == 'away'
    assert all(choice.chosen_by == models.BY_ENVIRONMENT for choice in loaded.jobs.values())


def test_an_unknown_profile_is_refused_by_name(tmp_path):
    with pytest.raises(models.ConfigurationError, match='no profile named'):
        models.load(configured(tmp_path), environ={'BORG_AGENT_PROFILE': 'nowhere'})


# --- job overrides ----------------------------------------------------------

def test_a_single_job_can_be_overridden_locally(tmp_path):
    root = configured(tmp_path, local={
        'play': {'provider': 'other', 'model': 'borrowed', 'family': 'beta', 'context_k': 8}})
    loaded = models.load(root, environ={})
    assert loaded.profile == 'house'
    assert loaded['play'].model == 'borrowed'
    assert loaded['play'].chosen_by == models.BY_LOCAL
    assert loaded['play'].context_k == 8
    # The jobs it does not name keep the profile's models.
    assert loaded['consolidate'].model == 'big'
    assert loaded['consolidate'].chosen_by == models.BY_PROFILE


def test_an_override_is_checked_like_the_file_it_overrides(tmp_path):
    root = configured(tmp_path, local={'play': {'provider': 'other', 'model': 'x'}})
    with pytest.raises(models.ConfigurationError, match='family'):
        models.load(root, environ={})


def test_the_local_file_holds_nothing_but_a_profile_and_jobs(tmp_path):
    root = configured(tmp_path, local={'profile': 'house', 'temperature': 0.7})
    with pytest.raises(models.ConfigurationError, match='job overrides only'):
        models.load(root, environ={})


# --- the rules --------------------------------------------------------------

def test_a_review_may_not_be_of_the_consolidators_family(tmp_path):
    def same_family(data):
        data['profiles']['house']['review'] = {
            'provider': 'house', 'model': 'big', 'family': 'alpha'}
    with pytest.raises(models.ConfigurationError, match='different model family'):
        models.load(configured(tmp_path, same_family), environ={})


def test_an_override_can_break_the_family_rule_and_is_caught(tmp_path):
    # The rule is about what a run will actually do, so it is checked after
    # the overrides, not only against the file.
    root = configured(tmp_path, local={
        'review': {'provider': 'house', 'model': 'big', 'family': 'alpha'}})
    with pytest.raises(models.ConfigurationError, match='different model family'):
        models.load(root, environ={})


def test_an_unknown_provider_is_refused(tmp_path):
    def unknown(data):
        data['profiles']['house']['play']['provider'] = 'ghost'
    with pytest.raises(models.ConfigurationError):
        models.load(configured(tmp_path, unknown), environ={})


def test_a_trial_candidate_with_an_unknown_provider_is_refused(tmp_path):
    def unknown(data):
        data['trial']['play'].append({'provider': 'ghost', 'model': 'x', 'family': 'g'})
    with pytest.raises(models.ConfigurationError, match='trial'):
        models.load(configured(tmp_path, unknown), environ={})


@pytest.mark.parametrize('field', ['api_key', 'key', 'openai_api_key', 'KEY'])
def test_a_field_that_looks_like_a_key_is_refused(tmp_path, field):
    def smuggle(data):
        data['providers']['house'][field] = 'sk-whatever'
    with pytest.raises(models.ConfigurationError, match='environment'):
        models.load(configured(tmp_path, smuggle), environ={})


def test_a_key_in_the_local_file_is_refused_too(tmp_path):
    root = configured(tmp_path, local={'profile': 'house', 'api_key': 'sk-whatever'})
    with pytest.raises(models.ConfigurationError, match='environment'):
        models.load(root, environ={})


def test_api_key_env_is_the_one_key_shaped_field_allowed():
    assert models.key_fields({'api_key_env': 'A'}) == []
    assert models.key_fields({'providers': {'p': {'api_key': 'x'}}}) == ['providers.p.api_key']
    assert models.key_fields([{'key': 1}]) == ['[0].key']


# --- the key, and the context size ------------------------------------------

def test_a_missing_key_variable_fails_naming_the_variable_not_its_value(tmp_path):
    loaded = models.load(configured(tmp_path), environ={})
    with pytest.raises(models.ConfigurationError) as raised:
        loaded['play'].key(environ={})
    assert 'HOUSE_KEY' in str(raised.value) and 'play' in str(raised.value)
    assert loaded.missing_keys(environ={}) == ['HOUSE_KEY', 'OTHER_KEY']
    assert loaded.missing_keys(['play'], environ={'HOUSE_KEY': 'x'}) == []


def test_a_key_pasted_as_a_value_is_not_quoted_back(tmp_path):
    """The review's smaller notes.

    `key_fields` refuses a field *named* like a key before any validator runs,
    but a key pasted into `model:` reaches the validator, whose message quotes
    what it saw. Nothing about a misconfiguration is worth printing a
    credential for.
    """
    secret = 'sk-abcdefghijklmnopqrstuvwxyz012345'

    def paste_a_key(data):
        data['profiles']['house']['play']['model'] = {'oops': secret}

    with pytest.raises(models.ConfigurationError) as raised:
        models.load(configured(tmp_path, change=paste_a_key), environ={})
    assert secret not in str(raised.value)
    assert '[removed]' in str(raised.value)


def test_a_file_that_is_not_yaml_says_so_without_quoting_the_line(tmp_path):
    (tmp_path / models.MODELS_FILE).write_text(
        'default_profile: house\nproviders: [unclosed\n  key: sk-abcdefghijklmnopqrst012345\n')
    with pytest.raises(models.ConfigurationError) as raised:
        models.load(tmp_path, environ={})
    assert 'not valid YAML' in str(raised.value)
    assert 'sk-abcdefghijklmnopqrst012345' not in str(raised.value)


def test_the_key_is_read_from_the_environment_when_it_is_needed(tmp_path):
    loaded = models.load(configured(tmp_path), environ={})
    assert loaded['play'].key(environ={'HOUSE_KEY': 'secret'}) == 'secret'


def test_a_job_without_context_k_gets_the_loaders_default(tmp_path):
    loaded = models.load(configured(tmp_path), environ={})
    assert loaded['play'].context_k == 64          # the profile says so
    assert loaded['consolidate'].context_k == models.DEFAULT_CONTEXT_K


# --- what the run record is told ---------------------------------------------

def test_the_record_names_everything_but_the_key(tmp_path):
    loaded = models.load(configured(tmp_path), environ={})
    recorded = loaded.record('play')
    assert recorded == {
        'job': 'play', 'profile': 'house', 'provider': 'house', 'model': 'small',
        'family': 'alpha', 'effort': None, 'chosen_by': 'profile', 'context_k': 64,
        'endpoint_host': 'house.example',
        'models_sha256': loaded.models_sha256, 'models_local_sha256': None,
    }
    # A host, not a URL; a variable's name is not in the record at all.
    assert '/' not in recorded['endpoint_host']
    assert 'HOUSE_KEY' not in json.dumps(recorded)
    assert 'secret' not in json.dumps(recorded)


def test_the_record_fits_the_run_record_schema(tmp_path):
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / 'schemas/run-record@1.json').read_text())
    mind = schema['properties']['mind']
    loaded = models.load(configured(tmp_path), environ={})
    document = {'kind': 'api', **loaded.record('play'),
                'prompt_pack': {'version': 'x', 'sha256': '0' * 64},
                'knowledge_sha256': None,
                'budget': {'model_calls': 10, 'tokens': 1000}}
    errors = sorted(Draft202012Validator({**mind, '$defs': schema['$defs']})
                    .iter_errors(document), key=str)
    assert not errors, [e.message for e in errors]


# --- the repository's own file ----------------------------------------------

def test_the_repositorys_models_file_loads_and_obeys_every_rule():
    loaded = models.load()
    assert loaded.profile in yaml.safe_load((ROOT / models.MODELS_FILE).read_text())['profiles']
    assert set(loaded.jobs) == set(models.JOBS)
    assert loaded['review'].family != loaded['consolidate'].family
    for job in models.JOBS:
        choice = loaded[job]
        assert choice.base_url.startswith('https://')
        assert choice.api_key_env.isupper()


def test_the_repositorys_models_file_validates_against_the_schema():
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / 'schemas/models@1.json').read_text())
    Draft202012Validator.check_schema(schema)
    data = yaml.safe_load((ROOT / models.MODELS_FILE).read_text())
    assert not sorted(Draft202012Validator(schema).iter_errors(data), key=str)


def test_every_trial_candidate_is_a_known_provider_in_the_real_file():
    loaded = models.load()
    known = set(yaml.safe_load((ROOT / models.MODELS_FILE).read_text())['providers'])
    for job, candidates in loaded.trial.items():
        assert candidates, job
        for candidate in candidates:
            assert candidate['provider'] in known
