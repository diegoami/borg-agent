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
    assert milestones == {'1', '2', '3', '4'}, milestones
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
