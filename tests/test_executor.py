"""The executor's primitives (T05).

The point of these tests is that the primitives are **mechanical**: they path,
step, rest, read and buy, and they hold no tactics, no thresholds and no
valuations (R2, docs/SOURCES.md). A threshold only exists when the mind asked
for one.
"""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from borg_agent import agent, executor, mind

ROOT = Path(__file__).resolve().parents[1]
ACTION_SCHEMA = Draft202012Validator(json.loads((ROOT / 'schemas/action@1.json').read_text()))


def observation(rows=None, player=(2, 1), hp=18, max_hp=18, depth=1, monsters=(),
                inventory=(), prompt='none', shop=None, messages=(), turn=10, decision=0):
    rows = rows or ['#####',
                    '#.@.#',
                    '#####']
    return {
        'schema': 'borg-agent/observation@1', 'run_id': 'test',
        'decision': decision, 'turn': turn,
        'character': {'race': 'Human', 'class': 'Warrior', 'level': 1,
                      'hp': hp, 'max_hp': max_hp, 'depth': depth, 'gold': 100},
        'map': {'player': {'x': player[0], 'y': player[1]}, 'origin': {'x': 0, 'y': 0},
                'rows': rows},
        'monsters': [dict(letter='r', name='a rat', x=x, y=y) for x, y in monsters],
        'objects': [],
        'inventory': [dict(label=label, description=description, count=1)
                      for label, description in inventory],
        'equipment': [], 'messages': list(messages),
        'shop': shop, 'prompt': {'kind': prompt},
    }


def run(primitive, *observations):
    """Step a primitive through observations: [(action or None, stop)]."""
    return [primitive.step(o) for o in observations]


# --- pathing ----------------------------------------------------------------

def test_the_path_is_the_shortest_known_one():
    rows = ['#######',
            '#.....#',
            '#.@...#',
            '#######']
    steps = executor.path(observation(rows=rows, player=(2, 2)), [(5, 2)])
    assert steps == [(3, 2), (4, 2), (5, 2)]


def test_pathing_goes_round_a_monster_and_through_a_door():
    rows = ['#######',
            '#.@+..#',
            '#.....#',
            '#######']
    through_door = executor.path(observation(rows=rows, player=(2, 1)), [(5, 1)])
    assert through_door[0] == (3, 1)          # the door, which `alter` opens
    with_monster = executor.path(observation(rows=rows, player=(2, 1),
                                             monsters=[(3, 1)]), [(5, 1)])
    assert (3, 1) not in with_monster          # round it, not through it


def test_a_known_trap_is_not_pathed_through():
    rows = ['#####',
            '#.^.#',
            '#####']
    assert executor.path(observation(rows=rows, player=(1, 1)), [(3, 1)]) is None


def test_no_known_way_is_no_path_not_a_guess():
    rows = ['#####',
            '#.@##',
            '#####']
    assert executor.path(observation(rows=rows, player=(2, 1)), [(4, 1)]) is None
    assert executor.path(observation(), [(2, 1)]) == []   # already there


# --- the primitives ---------------------------------------------------------

def test_walk_to_walks_and_arrives():
    primitive = executor.WalkTo(target={'x': 3, 'y': 1})
    first, stop = primitive.step(observation())
    assert stop is None and first['command'] == {'name': 'walk', 'direction': 6}
    ACTION_SCHEMA.validate(first)
    _, stop = primitive.step(observation(player=(3, 1)))
    assert stop == 'arrived'


def test_walk_to_says_no_path_rather_than_wandering():
    primitive = executor.WalkTo(target={'x': 9, 'y': 9})
    assert primitive.step(observation())[1] == 'no_path'


def test_explore_floor_heads_for_the_unknown_and_stops_when_there_is_none():
    rows = ['#####',
            '#.@. ',
            '#####']
    action, stop = executor.ExploreFloor().step(observation(rows=rows))
    assert stop is None and action['command']['name'] == 'walk'
    closed = ['#####',
              '#.@.#',
              '#####']
    assert executor.ExploreFloor().step(observation(rows=closed))[1] == 'explored'


def test_fight_nearest_attacks_what_is_next_to_it():
    action, stop = executor.FightNearest().step(observation(monsters=[(3, 1)]))
    assert stop is None and action['command'] == {'name': 'alter', 'direction': 6}


def test_fight_nearest_closes_on_a_distant_monster_and_stops_when_none_is_left():
    rows = ['#######',
            '#.@..r#',
            '#######']
    action, stop = executor.FightNearest().step(observation(rows=rows, monsters=[(5, 1)]))
    assert stop is None and action['command'] == {'name': 'walk', 'direction': 6}
    assert executor.FightNearest().step(observation())[1] == 'no_target'


def test_rest_until_healed_rests_then_stops():
    primitive = executor.RestUntilHealed()
    action, stop = primitive.step(observation(hp=5))
    assert stop is None and action['command'] == {'name': 'rest', 'mode': 'full'}
    assert primitive.step(observation(hp=18))[1] == 'healed'
    # A monster arriving is reported as the change it is...
    arrived = executor.RestUntilHealed()
    arrived.step(observation(hp=5))
    assert arrived.step(observation(hp=6, monsters=[(3, 1)]))[1] == 'new_monster'
    # ...and a monster that was already there interrupts the rest.
    interrupted = executor.RestUntilHealed()
    interrupted.step(observation(hp=5, monsters=[(3, 1)]))
    assert interrupted.step(observation(hp=6, monsters=[(3, 1)]))[1] == 'interrupted'


def test_take_stairs_uses_the_ones_underfoot_or_walks_to_them():
    on_stairs = ['#####',
                 '#.>.#',
                 '#####']
    action, stop = executor.TakeStairs(direction='down').step(
        observation(rows=on_stairs, player=(2, 1)))
    assert stop is None and action['command'] == {'name': 'go_down'}
    away = ['#######',
            '#.@..>#',
            '#######']
    action, stop = executor.TakeStairs(direction='down').step(observation(rows=away))
    assert stop is None and action['command']['name'] == 'walk'
    assert executor.TakeStairs(direction='down').step(observation())[1] == 'no_stairs_known'


def test_flee_reads_a_phase_door_or_takes_the_stairs():
    scroll = executor.Flee(by='phase_door')
    action, stop = scroll.step(observation(inventory=[('c', 'a Scroll of Phase Door')]))
    assert stop is None and action['command'] == {'name': 'read', 'item': 'c'}
    assert executor.Flee(by='phase_door').step(observation())[1] == 'no_escape'
    stairs = ['#####',
              '#.>.#',
              '#####']
    action, stop = executor.Flee(by='stairs').step(observation(rows=stairs, player=(2, 1)))
    assert stop is None and action['command'] == {'name': 'go_down'}
    assert executor.Flee(by='stairs').step(observation())[1] == 'no_escape'


def test_read_unknown_scroll_reads_one_it_has_not_identified():
    primitive = executor.ReadUnknownScroll()
    action, stop = primitive.step(observation(
        inventory=[('a', 'a Ration of Food'), ('b', 'a Scroll titled "nagkri mun"')]))
    assert stop is None and action['command'] == {'name': 'read', 'item': 'b'}
    assert primitive.step(observation())[1] == 'read'
    known_only = executor.ReadUnknownScroll()
    assert known_only.step(observation(
        inventory=[('a', 'a Scroll of Word of Recall')]))[1] == 'none_unknown'


def test_shop_list_buys_the_labels_in_order():
    shop = {'kind': 'General Store',
            'stock': [{'label': 'a', 'description': 'a Ration of Food', 'count': 4, 'price': 3}]}
    primitive = executor.ShopList(list=[{'label': 'a', 'count': 2, 'side': 'buy'}])
    action, stop = primitive.step(observation(shop=shop))
    assert stop is None
    assert action['command'] == {'name': 'buy', 'item': 'a', 'count': 2}
    assert primitive.step(observation(shop=shop))[1] == 'bought'
    assert executor.ShopList(list=[{'label': 'a', 'count': 1}]).step(
        observation())[1] == 'not_in_shop'
    assert executor.ShopList(list=[{'label': 'z', 'count': 1}]).step(
        observation(shop=shop))[1] == 'missing_item'


# --- what makes a primitive mechanical --------------------------------------

def test_a_primitive_holds_no_threshold_of_its_own():
    # At one hit point, with no limit asked for, it keeps going. The executor
    # has no opinion about danger; that is the mind's (R2).
    primitive = executor.WalkTo(target={'x': 3, 'y': 1})
    action, stop = primitive.step(observation(hp=1, max_hp=18))
    assert stop is None and action is not None


def test_a_threshold_the_mind_asked_for_is_obeyed():
    primitive = executor.WalkTo(target={'x': 3, 'y': 1}, stop_if_hp_below=10)
    primitive.step(observation(hp=18))
    assert primitive.step(observation(hp=9))[1] == 'hp_below'


@pytest.mark.parametrize('change,expected', [
    ({'prompt': 'yes_no'}, 'prompt'),
    ({'depth': 2}, 'changed_level'),
    ({'monsters': [(3, 1)]}, 'new_monster'),
])
def test_a_primitive_stops_when_something_changes(change, expected):
    primitive = executor.ExploreFloor()
    primitive.step(observation(rows=['#####', '#.@. ', '#####']))
    assert primitive.step(observation(rows=['#####', '#.@. ', '#####'], **change))[1] == expected


def test_fighting_does_not_stop_because_another_monster_arrived():
    primitive = executor.FightNearest()
    primitive.step(observation(monsters=[(3, 1)]))
    action, stop = primitive.step(observation(monsters=[(3, 1), (1, 1)]))
    assert stop is None and action is not None


def test_a_primitive_stops_at_the_limit_the_mind_set():
    primitive = executor.ExploreFloor(max_decisions=2)
    rows = ['#####', '#.@. ', '#####']
    assert primitive.step(observation(rows=rows))[0] is not None
    assert primitive.step(observation(rows=rows))[0] is not None
    assert primitive.step(observation(rows=rows))[1] == 'decision_limit'


def test_the_primitives_are_the_ones_r2_names():
    assert set(executor.PRIMITIVES) == {
        'walk_to', 'explore_floor', 'fight_nearest', 'rest_until_healed',
        'take_stairs', 'flee', 'read_unknown_scroll', 'shop_list'}
    # They are also the ones action@1 allows a mind to ask for.
    schema = json.loads((ROOT / 'schemas/action@1.json').read_text())
    allowed = schema['allOf'][0]['then']['properties']['primitive']['properties']['name']['enum']
    assert set(allowed) == set(executor.PRIMITIVES)


def test_every_stop_reason_is_a_declared_one():
    assert len(set(executor.STOPS)) == len(executor.STOPS)
    for name in ('arrived', 'explored', 'no_target', 'healed', 'changed_level',
                 'hp_below', 'decision_limit', 'new_monster', 'prompt'):
        assert name in executor.STOPS


def test_make_builds_a_primitive_from_an_action():
    built = executor.make({'name': 'walk_to', 'target': {'x': 1, 'y': 2}})
    assert isinstance(built, executor.WalkTo)
    with pytest.raises(ValueError):
        executor.make({'name': 'teleport_to_the_end'})


# --- the executor in front of a chooser -------------------------------------

class Chooser:
    """A chooser with a fixed script, to watch what the executor does with it."""

    name = 'test-chooser'
    kind = 'scripted'

    def __init__(self, answers):
        self.answers = list(answers)
        self.seen = []

    def act(self, observation):
        self.seen.append(observation.get('last_stop'))
        return self.answers.pop(0) if self.answers else mind.action(
            'command', 'nothing left to do', command={'name': 'stay'})


def test_the_executor_runs_a_primitive_then_asks_again_with_the_stop():
    chooser = Chooser([
        mind.action('primitive', 'walk there', primitive={'name': 'walk_to',
                                                          'target': {'x': 3, 'y': 1}}),
        mind.action('primitive', 'explore', primitive={'name': 'explore_floor'}),
    ])
    running = executor.ExecutingMind(chooser)
    assert running.act(observation())['command'] == {'name': 'walk', 'direction': 6}
    # Arrived: the primitive stops, and the chooser is asked with the reason.
    closed = observation(player=(3, 1))
    assert running.act(closed)['command'] == {'name': 'stay'}
    assert running.stops[0]['stop'] == 'arrived'
    assert running.stops[1]['stop'] == 'explored'
    assert chooser.seen == [None, 'arrived', 'explored']


def test_a_command_from_the_chooser_passes_straight_through():
    chooser = Chooser([mind.action('command', 'answer the prompt',
                                   command={'name': 'escape'})])
    running = executor.ExecutingMind(chooser)
    assert running.act(observation(prompt='menu'))['command'] == {'name': 'escape'}
    assert running.current is None


def test_an_agent_that_cannot_act_says_so_instead_of_spinning():
    # Every primitive it is given stops at once: that is the agent giving up,
    # which the run records as agent_stopped, not as a harness failure.
    chooser = Chooser([mind.action('primitive', 'walk nowhere',
                                   primitive={'name': 'walk_to',
                                              'target': {'x': 9, 'y': 9}})] * 20)
    running = executor.ExecutingMind(chooser)
    with pytest.raises(executor.CannotAct):
        running.act(observation())
    assert len(running.stops) == executor.ExecutingMind.PATIENCE


def test_everything_the_executor_produces_is_valid_and_translatable():
    cases = [
        (executor.WalkTo(target={'x': 3, 'y': 1}), observation()),
        (executor.ExploreFloor(), observation(rows=['#####', '#.@. ', '#####'])),
        (executor.FightNearest(), observation(monsters=[(3, 1)])),
        (executor.RestUntilHealed(), observation(hp=5)),
        (executor.TakeStairs(direction='down'), observation(rows=['#####', '#.>.#', '#####'],
                                                            player=(2, 1))),
        (executor.Flee(by='phase_door'), observation(inventory=[('c', 'a Scroll of Phase Door')])),
        (executor.ReadUnknownScroll(), observation(inventory=[('b', 'a Scroll titled "xyz"')])),
        (executor.ShopList(list=[{'label': 'a', 'count': 1}]),
         observation(shop={'kind': 'General Store',
                           'stock': [{'label': 'a', 'description': 'a Ration', 'count': 1,
                                      'price': 3}]})),
    ]
    for primitive, state in cases:
        action, stop = primitive.step(state)
        assert action is not None, (primitive.name, stop)
        ACTION_SCHEMA.validate(action)
        assert agent.wire(action)


@pytest.mark.slow
def test_a_primitive_driven_run_is_reproducible_and_verifies(tmp_path):
    """T05's gate: primitives playing a real game, twice, and then replayed."""
    import os

    from borg_agent import build, play, record, replay

    out = build.prepare(log=lambda *a: None)
    lock = not os.environ.get('BORG_AGENT_NO_LOCK')
    streams, records = [], []
    for attempt in (1, 2):
        driver = executor.ExecutingMind(mind.PrimitiveMind(), name='scripted-primitives')
        result = agent.play_with_mind(out, seed=1, cap=10000, output=tmp_path / f'run{attempt}',
                                      mind=driver, timeout=300, stall_timeout=60, lock=lock,
                                      log=lambda *a: None)
        assert result['outcome'] in play.GOOD_OUTCOMES, result
        # The fixture descends, fights and rests, so the gate is not only
        # walking — the review pointed out that it only checked two of them.
        kinds = {stop['primitive'] for stop in driver.stops}
        assert {'explore_floor', 'take_stairs', 'fight_nearest',
                'rest_until_healed'} <= kinds, kinds
        reasons = {stop['stop'] for stop in driver.stops}
        assert {'changed_level', 'no_target', 'healed'} <= reasons, reasons
        # And what it chose, and why, is written down (R2).
        journal = [json.loads(line) for line in
                   (tmp_path / f'run{attempt}' / agent.JOURNAL_LOG).read_text().splitlines()]
        assert {entry['kind'] for entry in journal} == {'choice', 'stop'}
        assert any(entry.get('chose') == 'fight_nearest' for entry in journal)
        assert all(entry['answer']['reason'] for entry in journal if entry['kind'] == 'choice')
        streams.append((tmp_path / f'run{attempt}' / agent.ACTION_LOG).read_bytes())
        records.append(result)
    assert streams[0] and streams[0] == streams[1]
    assert records[0]['action_stream']['sha256'] == records[1]['action_stream']['sha256']
    record.write_record(tmp_path / 'run1')
    verdict = replay.verify(tmp_path / 'run1', tmp_path / 'verified', lock=lock,
                            log=lambda *a: None)
    assert verdict['verified'], verdict


class Shopper:
    """Walks to the General Store and buys one item by its label."""

    name = 'shopper'
    kind = 'scripted'

    def __init__(self, index=1):
        self.index = index
        self.bought = None
        self.walker = mind.ScriptedMind()

    def act(self, observation):
        prompt = (observation.get('prompt') or {'kind': 'none'})['kind']
        if prompt == 'more':
            return mind.action('command', 'Clear the prompt.',
                               command={'name': 'answer', 'answer': '\r'})
        if prompt != 'none':
            return mind.action('command', 'Leave the prompt.', command={'name': 'escape'})
        shop = observation.get('shop')
        if shop and self.bought is None:
            item = shop['stock'][self.index]
            self.bought = item
            return mind.action('primitive', f"Buy {item['label']}.",
                               primitive={'name': 'shop_list',
                                          'list': [{'label': item['label'], 'count': 1,
                                                    'side': 'buy'}]})
        if shop:
            return mind.action('command', 'Leave the shop.', command={'name': 'escape'})
        rows = observation['map']['rows']
        origin = observation['map'].get('origin', {'x': 0, 'y': 0})
        doors = [(x + origin['x'], y + origin['y'])
                 for y, row in enumerate(rows) for x, glyph in enumerate(row) if glyph == '1']
        if doors:
            x, y = doors[0]
            return mind.action('primitive', 'Walk to the General Store.',
                               primitive={'name': 'walk_to', 'target': {'x': x, 'y': y}})
        return self.walker.act(observation)


@pytest.mark.slow
def test_buying_an_item_whose_label_is_not_the_first(tmp_path):
    """The store's labels skip the letters its commands use.

    Buying index 0 proves nothing — every labelling scheme agrees on 'a'. This
    buys index 1, which the store calls 'c' (the review's point (c)).
    """
    import os

    from borg_agent import build, play

    out = build.prepare(log=lambda *a: None)
    shopper = Shopper(index=1)
    driver = executor.ExecutingMind(shopper, name='shopper')
    result = agent.play_with_mind(out, seed=1, cap=6000, output=tmp_path / 'shop',
                                  mind=driver, timeout=300, stall_timeout=60,
                                  decision_cap=400,
                                  lock=not os.environ.get('BORG_AGENT_NO_LOCK'),
                                  log=lambda *a: None)
    assert result['outcome'] in play.GOOD_OUTCOMES, result
    assert shopper.bought, 'the shopper never reached the General Store'
    assert shopper.bought['label'] == 'c', shopper.bought
    observed = [json.loads(line) for line in
                (tmp_path / 'shop' / agent.OBSERVATION_LOG).read_text().splitlines()]
    in_shop = [o for o in observed if o.get('shop')]
    assert in_shop, 'no observation carried a shop'
    assert in_shop[0]['shop']['kind'] == 'General Store'
    before = in_shop[0]['character']['gold']
    after = observed[-1]['character']['gold']
    assert after == before - shopper.bought['price'], (before, after, shopper.bought)
    # The item the store named is the item that arrived.
    description = shopper.bought['description'].split(' {')[0]
    base = description.split(' of ')[-1].split(' (')[0]
    assert any(base.rstrip('s') in item['description']
               for item in observed[-1]['inventory']), observed[-1]['inventory']
