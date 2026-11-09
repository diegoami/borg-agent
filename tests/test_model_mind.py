"""The model-backed mind and the one at a file (T06), without a provider."""
import json
from pathlib import Path

import pytest

from borg_agent import model_mind, models, prompts, signals

ROOT = Path(__file__).resolve().parents[1]

CHOICE = models.Choice(
    job='play', provider='house', model='small', family='alpha',
    base_url='https://house.example/v1', api_key_env='HOUSE_KEY', context_k=64,
    effort=None, profile='house', chosen_by='profile')
ACTION = {'schema': 'borg-agent/action@1', 'kind': 'primitive',
          'reason': 'Explore what I have not seen.',
          'primitive': {'name': 'explore_floor'}}


def observation(decision=0, turn=1):
    return {
        'schema': 'borg-agent/observation@1', 'run_id': 'test', 'decision': decision,
        'turn': turn,
        'character': {'race': 'Human', 'class': 'Warrior', 'level': 1, 'hp': 18, 'max_hp': 18,
                      'depth': 1, 'gold': 0},
        'map': {'player': {'x': 2, 'y': 1}, 'origin': {'x': 0, 'y': 0},
                'rows': ['#####', '#.@.#', '#####']},
        'monsters': [], 'inventory': [], 'equipment': [], 'messages': [],
        'prompt': {'kind': 'none'},
    }


def answered(*replies, usage=None):
    """A transport that gives these replies in order."""
    queue = list(replies)
    calls = []

    def transport(messages):
        calls.append(messages)
        reply = queue.pop(0) if queue else ''
        return {'choices': [{'message': {'content': reply}}],
                'usage': usage or {'prompt_tokens': 100, 'completion_tokens': 20}}

    transport.calls = calls
    return transport


def api(transport, budget=None, log=None, environ=None):
    return model_mind.ApiMind(
        CHOICE, pack=prompts.load_pack('play-1'), budget=budget or model_mind.Budget(),
        call_log=log, transport=transport, environ=environ or {'HOUSE_KEY': 'sk-not-real'},
        choice_record={'job': 'play', 'provider': 'house', 'model': 'small',
                       'family': 'alpha', 'chosen_by': 'profile', 'profile': 'house',
                       'context_k': 64, 'effort': None,
                       'endpoint_host': 'house.example',
                       'models_sha256': '0' * 64, 'models_local_sha256': None})


# --- reading a reply --------------------------------------------------------

@pytest.mark.parametrize('reply', [
    json.dumps(ACTION),
    'Here is my move:\n```json\n' + json.dumps(ACTION) + '\n```\nI hope that helps.',
    'I will explore. ' + json.dumps(ACTION),
])
def test_an_action_is_found_however_the_model_wraps_it(reply):
    assert model_mind.extract_action(reply) == ACTION


def test_the_first_object_is_taken_when_a_model_answers_twice():
    first = model_mind.extract_action(json.dumps(ACTION) + '\n' + json.dumps({'kind': 'command'}))
    assert first == ACTION


def test_a_reply_with_no_action_is_refused():
    for reply in ('', 'I would rather not', '{not json at all'):
        with pytest.raises(ValueError):
            model_mind.extract_action(reply)


# --- the budget -------------------------------------------------------------

def test_the_budget_counts_calls_and_tokens():
    budget = model_mind.Budget(model_calls=3, tokens=1000)
    budget.spend(100, 20)
    assert budget.used['model_calls'] == 1 and budget.used['tokens'] == 120
    assert budget.record()['allowed'] == {'model_calls': 3, 'tokens': 1000}


def test_a_spent_budget_is_an_outcome_not_a_failure():
    budget = model_mind.Budget(model_calls=1)
    budget.check()
    budget.spend(1, 1)
    with pytest.raises(signals.BudgetSpent) as raised:
        budget.check()
    assert raised.value.allowed['model_calls'] == 1
    assert 'model_calls 1/1' in str(raised.value)


def test_a_run_stops_once_it_has_spent_its_token_budget():
    # The rule is "spend up to the limit, then stop", not "never exceed it":
    # a call's cost is only known after it is made.
    mind = api(answered(json.dumps(ACTION), json.dumps(ACTION), json.dumps(ACTION)),
               budget=model_mind.Budget(tokens=150))
    assert mind.act(observation()) == ACTION                  # 120 tokens, under the limit
    assert mind.act(observation(decision=1)) == ACTION        # 240, over it
    with pytest.raises(signals.BudgetSpent):
        mind.act(observation(decision=2))
    assert mind.budget.used['tokens'] == 240


# --- what the mind does with a reply ----------------------------------------

def test_a_valid_answer_is_the_action():
    mind = api(answered(json.dumps(ACTION)))
    assert mind.act(observation()) == ACTION
    assert mind.decisions == 1 and mind.parse_failures == 0


def test_a_bad_answer_is_corrected_once():
    mind = api(answered('no idea', json.dumps(ACTION)))
    assert mind.act(observation()) == ACTION
    assert mind.parse_failures == 1
    # The correction carries the model's own words back to it.
    second = mind.transport.calls[1]
    assert second[-1]['content'] == model_mind.CORRECTION
    assert second[-2] == {'role': 'assistant', 'content': 'no idea'}


def test_two_bad_answers_stop_the_agent_rather_than_guessing():
    mind = api(answered('no', 'still no'))
    with pytest.raises(signals.CannotAct, match='did not answer with a valid action'):
        mind.act(observation())
    assert mind.parse_failures == 2


def test_an_action_that_breaks_the_schema_counts_as_a_parse_failure():
    # Direction 5 is not a direction; action@1 refuses it, so the mind must too.
    bad = {'schema': 'borg-agent/action@1', 'kind': 'command', 'reason': 'go nowhere',
           'command': {'name': 'walk', 'direction': 5}}
    mind = api(answered(json.dumps(bad), json.dumps(ACTION)))
    assert mind.act(observation()) == ACTION
    assert mind.parse_failures == 1


# --- the call log (R2.1) ----------------------------------------------------

def test_every_call_is_logged_with_what_r2_1_asks_for(tmp_path):
    log = model_mind.CallLog(tmp_path / 'calls.jsonl')
    mind = api(answered(json.dumps(ACTION)), log=log)
    mind.act(observation(decision=7, turn=71))
    entries = [json.loads(line) for line in (tmp_path / 'calls.jsonl').read_text().splitlines()]
    assert len(entries) == 1
    entry = entries[0]
    for field in ('observation_sha256', 'prompt_pack', 'prompt_pack_sha256', 'model',
                  'provider', 'family', 'effort', 'reply', 'reason', 'prompt_tokens',
                  'completion_tokens', 'seconds', 'decision', 'turn'):
        assert field in entry, field
    assert entry['decision'] == 7 and entry['turn'] == 71
    assert entry['reason'] == ACTION['reason']
    assert entry['endpoint_host'] == 'house.example'


def test_the_key_never_reaches_the_log(tmp_path):
    log = model_mind.CallLog(tmp_path / 'calls.jsonl')
    mind = api(answered(json.dumps(ACTION)), log=log)
    mind.act(observation())
    text = (tmp_path / 'calls.jsonl').read_text()
    assert 'sk-not-real' not in text and 'HOUSE_KEY' not in text
    assert 'Authorization' not in text and 'Bearer' not in text


def test_a_reply_that_looks_like_a_credential_is_not_logged(tmp_path):
    log = model_mind.CallLog(tmp_path / 'calls.jsonl')
    mind = api(answered('here is a key sk-abcdefghijklmnop ' + json.dumps(ACTION)), log=log)
    mind.act(observation())
    text = (tmp_path / 'calls.jsonl').read_text()
    assert 'sk-abcdefghijklmnop' not in text
    assert 'looked like a credential' in text


def test_a_parse_failure_is_logged_with_its_reason(tmp_path):
    log = model_mind.CallLog(tmp_path / 'calls.jsonl')
    mind = api(answered('nonsense', json.dumps(ACTION)), log=log)
    mind.act(observation())
    entries = [json.loads(line) for line in (tmp_path / 'calls.jsonl').read_text().splitlines()]
    assert len(entries) == 2
    assert entries[0]['parse_problem'] and entries[0]['attempt'] == 1
    assert entries[1]['parse_problem'] is None and entries[1]['attempt'] == 2


# --- what the run record is told ---------------------------------------------

def test_the_mind_record_fits_the_schema_and_carries_no_key():
    from jsonschema import Draft202012Validator

    mind = api(answered(json.dumps(ACTION)))
    mind.act(observation())
    recorded = mind.mind_record
    schema = json.loads((ROOT / 'schemas/run-record@1.json').read_text())
    errors = sorted(Draft202012Validator(
        {**schema['properties']['mind'], '$defs': schema['$defs']}).iter_errors(recorded),
        key=str)
    assert not errors, [e.message for e in errors]
    assert recorded['jobs']['play']['calls'] == 1
    assert recorded['jobs']['play']['prompt_tokens'] == 100
    assert 'sk-not-real' not in json.dumps(recorded)
    assert recorded['prompt_pack']['version'] == 'play-1'


# --- the provider failing ----------------------------------------------------

def test_a_provider_that_cannot_be_reached_is_infrastructure_not_play():
    def broken(messages):
        raise OSError('no route to host')

    mind = model_mind.ApiMind(CHOICE, pack=prompts.load_pack('play-1'),
                              transport=lambda m: broken(m),
                              environ={'HOUSE_KEY': 'x'})
    with pytest.raises(OSError):
        mind.act(observation())        # the fake transport raises directly


def test_a_missing_key_is_refused_before_any_call():
    with pytest.raises(models.ConfigurationError, match='HOUSE_KEY'):
        model_mind.ApiMind(CHOICE, pack=prompts.load_pack('play-1'),
                           transport=answered(json.dumps(ACTION)), environ={})


# --- the mind at a file ------------------------------------------------------

def test_the_external_mind_asks_in_a_file_and_reads_the_answer(tmp_path):
    answer = tmp_path / model_mind.ANSWER_PATTERN.format(decision=0)
    answer.write_text(json.dumps(ACTION))
    mind = model_mind.ExternalMind(tmp_path, pack=prompts.load_pack('play-1'),
                                   timeout=1, poll=0.01, log=lambda *a: None)
    assert mind.act(observation()) == ACTION
    asked = json.loads((tmp_path / model_mind.QUESTION_PATTERN.format(decision=0)).read_text())
    assert asked['observation']['decision'] == 0
    assert [m['role'] for m in asked['prompt']] == ['system', 'user']
    assert asked['answer_to'] == str(answer)


def test_the_external_mind_gives_up_rather_than_waiting_for_ever(tmp_path):
    mind = model_mind.ExternalMind(tmp_path, pack=prompts.load_pack('play-1'),
                                   timeout=0.05, poll=0.01, log=lambda *a: None)
    with pytest.raises(signals.CannotAct, match='no answer'):
        mind.act(observation())
