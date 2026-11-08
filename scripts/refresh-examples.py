#!/usr/bin/env python3
"""Regenerate the run-record examples from real runs.

The examples under `schemas/examples/run-record/` are not written by hand: a
short game is played, recorded, and the record becomes the example, so an
example can never claim something the recorder does not produce. The invalid
ones are the same record with exactly one thing R5 requires taken away.

    python scripts/refresh-examples.py

It plays two 1,000-turn games with the scripted mind (a few seconds) and needs
the pinned build, so run `python -m borg_agent build` first if it is missing.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from borg_agent import agent, build, mind, record, replay  # noqa: E402

DEST = ROOT / 'schemas/examples/run-record'
WORK = ROOT / 'runs/examples'
# A commit and a clean tree, so the examples do not carry this machine's state.
COMMIT = '0fd4af4' + '0' * 33


def tidy(document, run_id):
    document['run_id'] = run_id
    document['engine']['commit'] = COMMIT
    document['engine']['dirty'] = ''
    return document


def main():
    out = build.prepare(log=print)
    shutil.rmtree(WORK, ignore_errors=True)
    played = agent.play_with_mind(out, seed=1, cap=1000, output=WORK / 'play',
                                  mind=mind.ScriptedMind(), timeout=300, stall_timeout=60,
                                  log=print)
    if played['outcome'] not in ('turn_cap', 'death'):
        raise SystemExit(f'the example run ended {played["outcome"]}; look at it first')
    record.write_record(WORK / 'play')
    _result, parent = replay.branch(WORK / 'play', turn=500, output=WORK / 'branch',
                                    new_mind=mind.ScriptedMind(heading=4), log=print)
    record.write_record(WORK / 'branch', mode='post_mortem', parent=parent)

    real = tidy(json.loads((WORK / 'play/run-record.json').read_text()),
                'play-20261108-seed1-cap1000')
    branched = tidy(json.loads((WORK / 'branch/run-record.json').read_text()),
                    'branch-20261108-seed1-turn500')
    # The only invented record: no model has played yet, so its mind block is
    # written here and everything round it comes from the real run.
    api = json.loads(json.dumps(real))
    api.update(run_id='play-20261109-seed1865911738-mage', deterministic=False)
    api['mind'] = {
        'kind': 'api', 'job': 'play', 'profile': 'alibaba', 'provider': 'alibaba',
        'model': 'qwen3.8-flash', 'family': 'qwen', 'effort': None, 'chosen_by': 'profile',
        'context_k': 64,
        'models_sha256': '3bd1d0a6bd67a1f3cf42f12f78d4a3a4b33dd7e2b7ad3e2d1a0b9c8d7e6f5a4b',
        'models_local_sha256': None,
        'endpoint_host': 'token-plan.ap-southeast-1.maas.aliyuncs.com',
        'knowledge_sha256': None,
        'prompt_pack': {'version': 'play-1',
                        'sha256': 'aa11bb22cc33dd44ee55ff6677889900aabbccddeeff00112233445566778899'},
        'budget': {'model_calls': 400, 'tokens': 2000000},
    }
    api['outcome'] = {'kind': 'death', 'cause': 'a floating eye', 'reason': None,
                      'turn': 14310, 'depth': 3, 'max_depth': 3, 'level': 8, 'max_level': 8,
                      'depth_marks': {'0': 1, '1': 981, '2': 5120, '3': 9004}}
    api['usage'] = {'decisions': 212, 'model_calls': 212, 'prompt_tokens': 418233,
                    'completion_tokens': 9902, 'invalid_actions': 3, 'parse_failures': 1,
                    'wall_seconds': 902.4}

    valid = {'valid-scripted-mind-turn-cap.json': real,
             'valid-branch-of-another-run.json': branched,
             'valid-api-mind-death.json': api}
    # Each invalid example drops one thing R5 names, or breaks one rule.
    invalid = {
        'invalid-no-settings.json': (real, lambda r: (r['game'].pop('settings'),
                                                      r['game'].pop('settings_sha256'))),
        'invalid-no-calendar.json': (real, lambda r: r.pop('calendar')),
        'invalid-no-seasonal-flag.json': (real, lambda r: r['calendar'].pop('seasonal')),
        'invalid-no-birth-options.json': (real, lambda r: r['game']['birth'].pop('options')),
        'invalid-no-content-identity.json': (real, lambda r: r['engine'].pop('data_sha256')),
        'invalid-dirty-state-not-stated.json': (real, lambda r: r['engine'].pop('dirty')),
        'invalid-no-birth-input-hash.json': (real, lambda r: r['game'].pop('input_sha256')),
        'invalid-endpoint-host-is-a-url-with-credentials.json': (
            api, lambda r: r['mind'].__setitem__('endpoint_host',
                                                 'https://user:secret@host/v1')),
        'invalid-api-mind-without-its-budget.json': (api, lambda r: r['mind'].pop('budget')),
        'invalid-a-key-in-the-record.json': (
            api, lambda r: r['mind'].__setitem__('api_key',
                                                 'placeholder-not-a-real-credential')),
    }
    for name, document in valid.items():
        record.validate(document)
        (DEST / name).write_text(json.dumps(document, indent=2, sort_keys=True) + '\n')
    for name, (base, change) in invalid.items():
        broken = json.loads(json.dumps(base))
        change(broken)
        (DEST / name).write_text(json.dumps(broken, indent=2, sort_keys=True) + '\n')
    print(f'refreshed {len(valid)} valid and {len(invalid)} invalid examples in {DEST}')


if __name__ == '__main__':
    main()
