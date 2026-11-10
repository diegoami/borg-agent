"""Keeps the pins, the plan and the docs consistent, so a new session can trust them."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUSES = ('todo', 'in progress', 'in review', 'done')


def plan_rows():
    rows = []
    for line in (ROOT / 'PLAN.md').read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) == 6 and re.fullmatch(r'T\d\d', cells[0]):
            rows.append(cells)
    return rows


def milestone_rows():
    rows = []
    for line in (ROOT / 'PLAN.md').read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) == 4 and re.fullmatch(r'\*\*\d\..*', cells[0]):
            rows.append(cells)
    return rows


def test_pins_are_full_commits():
    data = json.loads((ROOT / 'pins.json').read_text())
    assert data['schema'] == 'borg-agent/pins@1'
    for name, pin in data['pins'].items():
        assert re.fullmatch(r'diegoami/[\w.-]+', pin['repository']), name
        assert re.fullmatch(r'[0-9a-f]{40}', pin['commit']), name
        assert pin['role'], name
    manual = data['manual']
    assert manual['pin'] in data['pins']
    assert manual['paths'] and not any('hacking' in p or 'gamedata' in p for p in manual['paths'])


def test_plan_status_table():
    rows = plan_rows()
    ids = [r[0] for r in rows]
    assert ids == sorted(set(ids)) and ids, ids
    for task, _title, _milestone, needs, _cloud, status in rows:
        assert status.split(' (')[0] in STATUSES, (task, status)
        for need in re.findall(r'T\d\d', needs):
            assert need in ids and need < task, (task, need)
        assert f'### {task}.' in (ROOT / 'PLAN.md').read_text(), task


def test_every_task_belongs_to_a_milestone():
    milestones = {row[0].strip('*').split('.')[0] for row in milestone_rows()}
    assert milestones == {'1', '2', '3', '4', '5'}, milestones
    for task, _title, milestone, _needs, _cloud, _status in plan_rows():
        assert milestone in milestones, (task, milestone)


def test_a_task_does_not_need_a_later_milestones_work():
    # A milestone has to be reviewable on its own, so nothing in it may depend
    # on work that only arrives afterwards.
    milestone_of = {row[0]: int(row[2]) for row in plan_rows()}
    for task, _title, milestone, needs, _cloud, _status in plan_rows():
        for need in re.findall(r'T\d\d', needs):
            assert milestone_of[need] <= int(milestone), (task, need)


def test_the_milestone_process_is_written_down():
    plan = (ROOT / 'PLAN.md').read_text()
    rules = (ROOT / 'RULES.md').read_text()
    # The review PR's base is what makes its diff the milestone's work.
    assert '--base reviewed' in plan
    assert 'reviewed' in rules and 'milestone' in rules.lower()


def test_mode_c_comes_before_the_trial():
    """Decision D11, 2026-11-09: milestone 4 begins with a probe, not with T09.

    The order lives in the milestone table's task cell, because that is what a
    session reads to pick up its next task (AGENTS.md).
    """
    # The order runs across the milestone rows in the table's own order, since
    # the trial moved to a later milestone when the play redesign went in
    # front of it.
    order = [task for row in milestone_rows() for task in re.findall(r'T\d\d', row[2])]
    assert 'T22' in order
    # The trial left the milestone tables with the owner's pivot of 2026-11-09
    # (no more playing). While it is listed anywhere, the probe comes first.
    if 'T09' in order:
        assert order.index('T22') < order.index('T09'), order
    assert 'D11' in (ROOT / 'docs/REQUIREMENTS.md').read_text()


def test_the_zoo_contract_maps_onto_the_zoos_own_cell():
    """T11: every cell field docs/ZOO-IMPORT.md promises to fill is a field the
    zoo's own `summarise` writes, at the pin we read it at.

    The contract is for someone else's repository, so drift there is invisible
    from here unless something checks it.
    """
    import re

    from borg_agent import pins

    harness = pins.show('borg-zoo', 'zoo/harness.py').decode()
    cell = harness[harness.index("'schema': 'borg-zoo/cell@1'"):]
    cell = cell[:cell.index('\n    }')]
    theirs = set(re.findall(r"'([a-z_0-9]+)':", cell))
    # The zoo spreads the cell's own keys in with `**cell`, which names the
    # specimen, the seed and the profile; those are the suite's, not summarise's.
    theirs |= {'seed', 'specimen', 'profile', 'play_sha256', 'trace_sha256',
               'binary_sha256', 'config_sha256', 'profile_sha256', 'runner_sha256'}

    contract = (ROOT / 'docs/ZOO-IMPORT.md').read_text()
    table = contract[contract.index('## Mapping a record onto'):]
    table = table[:table.index('\n## ')]
    promised = set(re.findall(r'^\| `([a-z_0-9]+)`', table, re.M))
    assert promised, 'the mapping table has no cell fields'
    assert promised <= theirs, sorted(promised - theirs)


def test_local_links_resolve():
    for doc in [ROOT / 'README.md', ROOT / 'AGENTS.md', ROOT / 'RULES.md', ROOT / 'PLAN.md',
                *sorted((ROOT / 'docs').glob('*.md'))]:
        for target in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)', doc.read_text()):
            if '://' in target:
                continue
            assert (doc.parent / target).exists(), f'{doc.name} links to missing {target}'


def test_session_start_hook_runs_setup():
    settings = json.loads((ROOT / '.claude/settings.json').read_text())
    commands = [h['command'] for entry in settings['hooks']['SessionStart'] for h in entry['hooks']]
    assert any('scripts/setup.sh' in c for c in commands)
    assert (ROOT / 'scripts/setup.sh').stat().st_mode & 0o111


def test_the_agents_sources_are_pinned_and_readable():
    """Decision D8: what the playing agent may read, each at a fixed commit."""
    from borg_agent import pins

    data = json.loads((ROOT / 'pins.json').read_text())
    sources = data['sources']
    assert sources['manual']['required'] is True
    for name, source in sources.items():
        if name == 'note' or 'unpinned' in source:
            assert name == 'note' or source['unpinned'], name
            continue
        assert source['pin'] in data['pins'], name
        assert source['paths'], name
    # The spec is the one source outside better-borg-c, so check it is really
    # there at its pin rather than only named.
    spec = sources['borg_spec']
    text = pins.show(spec['pin'], pins.pin(spec['pin'])['path']).decode()
    assert 'Borg' in text and len(text) > 10000
    # The deaths are read at the better-borg-c pin, not from its moving main.
    listing = pins.git('better-borg-c', 'ls-tree', '--name-only',
                       data['pins']['better-borg-c']['commit'] + ':docs/deaths').decode()
    assert 'index.json' in listing and 'D0001' in listing


def test_the_manual_is_still_the_manual():
    # D8 opened what the agent may read; the manual list is still the manual,
    # so a prompt pack can require it without pulling in developer pages.
    manual = json.loads((ROOT / 'pins.json').read_text())['manual']
    assert all(p.startswith(('docs/', 'lib/help')) for p in manual['paths'])
    assert not any('hacking' in p or 'gamedata' in p for p in manual['paths'])


def test_the_rust_remake_is_pinned_and_readable():
    """The Borg reborn, at a fixed commit, so a claim can cite it."""
    from borg_agent import pins

    data = json.loads((ROOT / 'pins.json').read_text())
    assert data['sources']['rust_remake']['pin'] == 'borg-rs'
    # The same connection the bridge attaches to on the C side, so a claim
    # about the connection carries over.
    borg = pins.show('borg-rs', 'borg-rs/src/borg.rs').decode()
    assert 'inkey_hack' in borg and 'generate_keypress' in borg
    # 59 Borg modules were converted; there are more files than that with the
    # headers, and never fewer.
    modules = pins.git('borg-rs', 'ls-tree', '--name-only',
                       data['pins']['borg-rs']['commit'] + ':borg-rs/src').decode().split()
    assert len([m for m in modules if m.endswith('.rs')]) >= 59, len(modules)


def test_each_pin_says_which_milestone_it_is():
    # A claim has to say which side of the port it is about, so both roles name
    # a milestone. Which number that is changes with every repin -- borg-rs is
    # carrying milestone 8 next -- so this checks that they say it, not what
    # they say.
    data = json.loads((ROOT / 'pins.json').read_text())
    for name in ('better-borg-c', 'borg-rs'):
        assert re.search(r'milestone \d+', data['pins'][name]['role']), name


def test_the_user_manual_rests_on_the_same_game_data():
    """The user manual's tables were extracted from `lib/gamedata/`, so they
    describe the game we play only while that data is the same.

    (This check was written for `docs/strategy/` on the same pin. That source
    moved to the finished manual at the `borg-spec` pin on 2026-11-09; the
    data comparison is still worth keeping, because T20's user manual is still
    read here.)
    """
    from borg_agent import pins

    data = json.loads((ROOT / 'pins.json').read_text())
    assert data['sources']['user_manual'] == {'pin': 'c-borg-reference',
                                              'paths': ['docs/user-manual.md']}
    commit = pins.pin('c-borg-reference')['commit']

    def gamedata(name, at):
        rows = pins.git(name, 'ls-tree', at + ':lib/gamedata').decode().splitlines()
        return {row.split('\t')[1]: row.split()[2] for row in rows}

    assert gamedata('c-borg-reference', commit) == gamedata(
        'better-borg-c', pins.pin('better-borg-c')['commit'])


def test_the_online_command_page_is_read_at_a_pin():
    # readthedocs' "latest" moves with upstream, so the record cites the file
    # it is built from, at a pin.
    from borg_agent import pins

    online = json.loads((ROOT / 'pins.json').read_text())['sources']['manual_online']
    assert online['url'] == 'https://angband.readthedocs.io/en/latest/command.html'
    pinned = online['pinned_as']
    assert pinned['path'] in pins.pins()['manual']['paths']
    assert pinned['pin'] == pins.pins()['manual']['pin']
    assert b'Command Descriptions' in pins.show(pinned['pin'], pinned['path'])


def test_the_user_manual_is_pinned_and_readable():
    """The owner's addition of 2026-11-09: docs/user-manual.md on c-borg-reference."""
    from borg_agent import pins

    data = json.loads((ROOT / 'pins.json').read_text())
    assert data['sources']['user_manual'] == {'pin': 'c-borg-reference',
                                              'paths': ['docs/user-manual.md']}
    text = pins.show('c-borg-reference', 'docs/user-manual.md').decode()
    assert text.startswith('# Angband')
    for heading in ('## 10. Command reference', '## 28. The Borg'):
        assert heading in text, heading
    # Its tables come from lib/gamedata, so it describes the game we play only
    # while the test above finds that data equal to the game pin's.


def test_the_strategy_manual_is_the_finished_one():
    """The owner's source of 2026-11-09: docs/c-manual, not the old index."""
    from borg_agent import pins

    data = json.loads((ROOT / 'pins.json').read_text())
    source = data['sources']['strategy_manual']
    assert source['pin'] == 'borg-spec' and source['paths'] == ['docs/c-manual/']
    commit = data['pins']['borg-spec']['commit']
    entries = pins.git('borg-spec', 'ls-tree', '--name-only',
                       f'{commit}:docs/c-manual').decode().split()
    chapters = sorted(name for name in entries if re.fullmatch(r'\d\d-.*\.md', name))
    assert len(chapters) >= 17, chapters
    # The chapters the old copy's README linked to and did not have.
    assert chapters[0].startswith('00-') and any(c.startswith('15-') for c in chapters)
    # Chapter 15 is the one written for a borg, and it says what it is.
    borg = pins.show('borg-spec', 'docs/c-manual/15-notes-for-the-borg.md', commit).decode()
    assert 'starting policy to be measured' in borg
    appendices = pins.git('borg-spec', 'ls-tree', '--name-only',
                          f'{commit}:docs/c-manual/appendices').decode().split()
    assert len(appendices) >= 10, appendices


def test_moving_the_tracker_pin_did_not_move_the_specification():
    """One pin serves the spec and the manual, which is only honest if the
    spec is the same document at the new commit as at the old one."""
    from borg_agent import pins

    commit = json.loads((ROOT / 'pins.json').read_text())['pins']['borg-spec']['commit']
    PREVIOUS = 'eefc55000dd5d5f43d8f077f6543b4594807ce08'
    for path in ('docs/c-borg/BORG_SPEC.md', 'docs/c-borg/TUNABLE-BORG-PLAN.md'):
        now = pins.git('borg-spec', 'rev-parse', f'{commit}:{path}').decode().strip()
        before = pins.git('borg-spec', 'rev-parse', f'{PREVIOUS}:{path}').decode().strip()
        assert now == before, path
