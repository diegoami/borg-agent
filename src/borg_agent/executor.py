"""The executor: scripted primitives that run until something changes (R2).

A primitive is mechanical. It paths, it steps, it rests, it reads, it buys —
and it **holds no tactics, no thresholds and no valuations** (R2,
docs/SOURCES.md). It does not decide that a monster is too dangerous, that
hit points are low, or that an item is worth buying; it runs until something
changes and then says why it stopped. Choosing the next primitive, and the
thresholds a primitive should respect, are the mind's.

Each primitive answers one observation at a time with one command, because
that is what the bridge asks for. `Executor` keeps the current primitive, and
`ExecutingMind` puts a chooser — a model later, a scripted mind in tests — in
front of it.
"""
from collections import deque

from .mind import DIRECTIONS, ORDER, action
from .signals import CannotAct

# Terrain a step can land on, as the player's map draws it. A shop entrance
# (a digit) is walkable only as a destination, since stepping on it enters the
# shop. A known trap is not pathed through: walking round it is mechanical,
# and if there is no way round, the mind is told `no_path` and decides.
FLOOR = set(".<>'")
TRAP = '^'
DOOR = '+'
SHOP = set('12345678')
STAIRS = {'down': '>', 'up': '<'}
# A primitive never runs for ever; the mind may ask for less.
DEFAULT_MAX_DECISIONS = 400
# Why a primitive stopped. Every one of these is a change in the game or a
# limit the mind asked for -- never a judgement about what to do next.
STOPS = (
    'arrived', 'no_path', 'blocked', 'explored', 'no_target', 'target_gone',
    'healed', 'interrupted', 'changed_level', 'no_stairs_known', 'fled',
    'no_escape', 'read', 'none_unknown', 'bought', 'not_in_shop', 'unreachable',
    'missing_item', 'refused', 'new_monster', 'prompt', 'hp_below',
    'decision_limit', 'done',
    # T29, the caster's own stops.
    'no_such_spell', 'cannot_cast', 'studied', 'nothing_to_study',
)


def glyph_at(observation, x, y):
    """What the player knows is at (x, y), or None outside the known window."""
    known = observation['map']
    origin = known.get('origin', {'x': 0, 'y': 0})
    row, column = y - origin['y'], x - origin['x']
    if row < 0 or row >= len(known['rows']):
        return None
    line = known['rows'][row]
    return line[column] if 0 <= column < len(line) else None


def monsters_at(observation):
    return {(m['x'], m['y']) for m in observation['monsters']}


def walkable(glyph):
    return glyph in FLOOR


def path(observation, targets, through_doors=True):
    """The shortest known path from the player to the nearest of `targets`.

    Breadth-first over what the player knows, so it is deterministic and
    depends on nothing but the observation. Returns the list of steps as
    (x, y), target last, or None when there is no known way.
    """
    start = (observation['map']['player']['x'], observation['map']['player']['y'])
    targets = {tuple(t) for t in targets}
    if start in targets:
        return []
    blocked = monsters_at(observation)
    seen = {start}
    queue = deque([(start, [])])
    while queue:
        (x, y), steps = queue.popleft()
        for direction in ORDER:
            dx, dy = DIRECTIONS[direction]
            nxt = (x + dx, y + dy)
            if nxt in seen:
                continue
            seen.add(nxt)
            glyph = glyph_at(observation, *nxt)
            if glyph is None:
                continue
            if nxt in targets:
                return steps + [nxt]
            if nxt in blocked:
                continue
            if walkable(glyph) or (through_doors and glyph == DOOR):
                queue.append((nxt, steps + [nxt]))
    return None


def direction_towards(observation, square):
    """The number-pad direction of an adjacent square, or None."""
    player = observation['map']['player']
    dx, dy = square[0] - player['x'], square[1] - player['y']
    for direction, delta in DIRECTIONS.items():
        if delta == (dx, dy):
            return direction
    return None


def step_command(observation, square, reason):
    """One step onto an adjacent square: open a door, or walk."""
    direction = direction_towards(observation, square)
    if direction is None:
        return None
    glyph = glyph_at(observation, *square)
    name = 'alter' if glyph == DOOR else 'walk'
    return action('command', reason, command={'name': name, 'direction': direction})


class Primitive:
    """One primitive. `step` answers an observation, or stops and says why."""

    name = 'primitive'
    # Primitives that are not about fighting stop when a monster the player
    # could not see before comes into view: that is a change, not a judgement.
    stops_on_new_monster = True

    def __init__(self, **settings):
        self.settings = settings
        self.max_decisions = settings.get('max_decisions', DEFAULT_MAX_DECISIONS)
        self.stop_if_hp_below = settings.get('stop_if_hp_below')
        self.decisions = 0
        self.started = None       # the first observation it saw
        self.stop = None          # why it stopped, once it has

    # --- the shared checks ---------------------------------------------------

    def common_stop(self, observation):
        character = observation['character']
        if (observation.get('prompt') or {}).get('kind', 'none') != 'none':
            return 'prompt'
        if self.started is None:
            return None
        if character['depth'] != self.started['character']['depth']:
            return 'changed_level'
        if self.stop_if_hp_below is not None and character['hp'] < self.stop_if_hp_below:
            return 'hp_below'
        if self.decisions >= self.max_decisions:
            return 'decision_limit'
        if self.stops_on_new_monster:
            before = {(m['letter'], m['x'], m['y']) for m in self.started['monsters']}
            now = {(m['letter'], m['x'], m['y']) for m in observation['monsters']}
            if now - before and len(observation['monsters']) > len(self.started['monsters']):
                return 'new_monster'
        return None

    def step(self, observation):
        """(action, stop) — exactly one of them is set."""
        if self.started is None:
            self.started = observation
        stop = self.common_stop(observation)
        if stop:
            self.stop = stop
            return None, stop
        result, stop = self.act(observation)
        if stop:
            self.stop = stop
            return None, stop
        self.decisions += 1
        return result, None

    def act(self, observation):
        raise NotImplementedError


class WalkTo(Primitive):
    """Walk to a square the player knows, by the shortest known path."""

    name = 'walk_to'

    def act(self, observation):
        target = (self.settings['target']['x'], self.settings['target']['y'])
        player = observation['map']['player']
        if (player['x'], player['y']) == target:
            return None, 'arrived'
        steps = path(observation, [target])
        if steps is None:
            return None, 'no_path'
        if not steps:
            return None, 'arrived'
        command = step_command(observation, steps[0], f'Walk towards {target}.')
        # `blocked` is defensive: the first step of a path is always adjacent,
        # so a command is always built. Kept so a future pathing change cannot
        # return no action at all.
        return (command, None) if command else (None, 'blocked')


class ExploreFloor(Primitive):
    """Walk to the nearest known square that borders somewhere unknown."""

    name = 'explore_floor'

    def frontier(self, observation):
        found = []
        known = observation['map']
        origin = known.get('origin', {'x': 0, 'y': 0})
        for row, line in enumerate(known['rows']):
            for column, glyph in enumerate(line):
                if not walkable(glyph):
                    continue
                x, y = column + origin['x'], row + origin['y']
                for dx, dy in DIRECTIONS.values():
                    neighbour = glyph_at(observation, x + dx, y + dy)
                    if neighbour is None or neighbour == ' ':
                        found.append((x, y))
                        break
        return found

    def act(self, observation):
        player = observation['map']['player']
        frontier = [square for square in self.frontier(observation)
                    if square != (player['x'], player['y'])]
        if not frontier:
            return None, 'explored'
        steps = path(observation, frontier)
        if steps is None:
            # There is somewhere unseen, but no known way to it: a different
            # situation from a floor with nothing left, and the mind may want
            # to dig, search or leave (finding of the milestone 2 review).
            return None, 'unreachable'
        if not steps:
            return None, 'arrived'
        command = step_command(observation, steps[0], 'Explore towards the unknown.')
        return (command, None) if command else (None, 'blocked')


class FightNearest(Primitive):
    """Attack the nearest monster the player can see, until it is gone.

    It makes no judgement about whether fighting is wise. A mind that wants a
    limit says so with `stop_if_hp_below`.
    """

    name = 'fight_nearest'
    stops_on_new_monster = False

    def act(self, observation):
        monsters = observation['monsters']
        if not monsters:
            return None, 'no_target'
        player = observation['map']['player']
        target = min(monsters, key=lambda m: (max(abs(m['x'] - player['x']),
                                                  abs(m['y'] - player['y'])),
                                              m['y'], m['x']))
        square = (target['x'], target['y'])
        direction = direction_towards(observation, square)
        if direction is not None:
            return action('command', f"Attack the {target['name'] or target['letter']}.",
                          command={'name': 'alter', 'direction': direction}), None
        steps = path(observation, [square])
        if steps is None:
            return None, 'no_path'
        command = step_command(observation, steps[0], 'Close on the nearest monster.')
        return (command, None) if command else (None, 'blocked')


class CastAtNearest(Primitive):
    """Cast one named spell at the nearest visible monster, until it is gone.

    The spell is the mind's choice, by the book and letter the observation's
    `spells` gives it: this holds no opinion about which spell is good, only
    about repeating the one it was told (T29). It stops when nothing is
    visible, when the spell is not castable (no mana, or too low a level), or
    when the mind's own limits say so.
    """

    name = 'cast_at_nearest'
    stops_on_new_monster = False

    def __init__(self, book=None, spell=None, **settings):
        super().__init__(**settings)
        self.book = book
        self.spell = spell

    def act(self, observation):
        if not self.book or not self.spell:
            return None, 'refused'
        known = [s for s in observation.get('spells') or ()
                 if s['book'] == self.book and s['letter'] == self.spell]
        if not known:
            return None, 'no_such_spell'
        if not known[0]['castable']:
            # The game's own judgement: unlearned, too low a level, or not
            # enough mana for it right now.
            return None, 'cannot_cast'
        monsters = observation['monsters']
        if not monsters:
            return None, 'no_target'
        player = observation['map']['player']
        target = min(monsters, key=lambda m: (max(abs(m['x'] - player['x']),
                                                  abs(m['y'] - player['y'])),
                                              m['y'], m['x']))
        return action('command',
                      f"Cast {known[0]['name']} at the "
                      f"{target['name'] or target['letter']}.",
                      command={'name': 'cast', 'book': self.book, 'spell': self.spell,
                               'target': {'x': target['x'], 'y': target['y']}}), None


class StudyASpell(Primitive):
    """Learn one spell the game says may be learned, and stop.

    Which spell is the mind's choice when it names one; with none named it
    takes the first the game offers, which is the order the book itself lists.
    A character with nothing to learn stops at once (T29).
    """

    name = 'study_a_spell'

    def __init__(self, book=None, spell=None, **settings):
        super().__init__(**settings)
        self.book = book
        self.spell = spell
        self.asked = False

    def act(self, observation):
        if self.asked:
            # One study per primitive: the game either learned it or said why,
            # and either way the mind should look at the result.
            return None, 'studied'
        if not (observation.get('character') or {}).get('new_spells'):
            return None, 'nothing_to_study'
        offered = [s for s in observation.get('spells') or () if s['studyable']
                   and (self.book is None or s['book'] == self.book)
                   and (self.spell is None or s['letter'] == self.spell)]
        if not offered:
            return None, 'nothing_to_study'
        chosen = offered[0]
        self.asked = True
        return action('command', f"Learn {chosen['name']}.",
                      command={'name': 'study', 'book': chosen['book'],
                               'spell': chosen['letter']}), None


class RestUntilHealed(Primitive):
    """Rest until the character is whole again, or something interrupts."""

    name = 'rest_until_healed'

    def act(self, observation):
        character = observation['character']
        if character['hp'] >= character['max_hp']:
            return None, 'healed'
        if self.decisions and observation['monsters']:
            return None, 'interrupted'
        return action('command', 'Rest until healed.',
                      command={'name': 'rest', 'mode': 'full'}), None


class TakeStairs(Primitive):
    """Walk to the nearest staircase the player knows, and use it."""

    name = 'take_stairs'

    def act(self, observation):
        glyph = STAIRS[self.settings.get('direction', 'down')]
        player = observation['map']['player']
        if glyph_at(observation, player['x'], player['y']) == glyph:
            command = 'go_down' if glyph == '>' else 'go_up'
            return action('command', f'Take the {glyph} staircase.',
                          command={'name': command}), None
        squares = squares_with(observation, glyph)
        if not squares:
            return None, 'no_stairs_known'
        steps = path(observation, squares)
        if steps is None:
            return None, 'no_stairs_known'
        command = step_command(observation, steps[0], 'Walk to the staircase.')
        return (command, None) if command else (None, 'blocked')


class Flee(Primitive):
    """Leave by the nearest staircase, or by reading a Phase Door scroll."""

    name = 'flee'
    stops_on_new_monster = False

    def act(self, observation):
        if self.settings.get('by') == 'phase_door':
            item = find_item(observation, 'Phase Door')
            if item is None:
                return None, 'no_escape'
            return action('command', 'Phase Door away.',
                          command={'name': 'read', 'item': item['label']}), None
        player = observation['map']['player']
        here = glyph_at(observation, player['x'], player['y'])
        if here in ('<', '>'):
            return action('command', 'Flee by the staircase underfoot.',
                          command={'name': 'go_down' if here == '>' else 'go_up'}), None
        squares = squares_with(observation, '>') + squares_with(observation, '<')
        if not squares:
            return None, 'no_escape'
        steps = path(observation, squares)
        if steps is None:
            return None, 'no_escape'
        command = step_command(observation, steps[0], 'Run for the stairs.')
        return (command, None) if command else (None, 'blocked')


class ReadUnknownScroll(Primitive):
    """Read a scroll the player has not identified yet."""

    name = 'read_unknown_scroll'

    def act(self, observation):
        if self.decisions:
            return None, 'read'
        item = next((i for i in observation['inventory'] if 'Scroll titled' in i['description']),
                    None)
        if item is None:
            return None, 'none_unknown'
        return action('command', f"Read the unknown scroll {item['label']}.",
                      command={'name': 'read', 'item': item['label']}), None


class ShopList(Primitive):
    """Buy or sell the labels on a list, in order, while in a shop."""

    name = 'shop_list'

    def __init__(self, **settings):
        super().__init__(**settings)
        self.done = 0

    def act(self, observation):
        shop = observation.get('shop')
        if not shop:
            return None, 'not_in_shop'
        wanted = self.settings['list']
        if self.done >= len(wanted):
            return None, 'bought'
        entry = wanted[self.done]
        self.done += 1
        side = entry.get('side', 'buy')
        stock = shop['stock'] if side == 'buy' else observation['inventory']
        if not any(item['label'] == entry['label'] for item in stock):
            return None, 'missing_item'
        if any('not have enough' in message for message in observation['messages']):
            return None, 'refused'
        return action('command', f"{side.title()} {entry['count']} of {entry['label']}.",
                      command={'name': 'buy' if side == 'buy' else 'sell',
                               'item': entry['label'], 'count': entry['count']}), None


def squares_with(observation, glyph):
    """Every known square showing a glyph, nearest first by reading order."""
    known = observation['map']
    origin = known.get('origin', {'x': 0, 'y': 0})
    return [(column + origin['x'], row + origin['y'])
            for row, line in enumerate(known['rows'])
            for column, seen in enumerate(line) if seen == glyph]


def find_item(observation, text):
    return next((i for i in observation['inventory'] if text in i['description']), None)


PRIMITIVES = {p.name: p for p in (WalkTo, ExploreFloor, FightNearest, RestUntilHealed,
                                  TakeStairs, Flee, ReadUnknownScroll, ShopList,
                                  CastAtNearest, StudyASpell)}
assert set(PRIMITIVES) == {
    'walk_to', 'explore_floor', 'fight_nearest', 'rest_until_healed', 'take_stairs',
    'flee', 'read_unknown_scroll', 'shop_list',
    # T29: the two a caster cannot play without. R2's eight were written for a
    # Warrior, and a Mage that cannot cast or study is not a Mage.
    'cast_at_nearest', 'study_a_spell'}, 'the primitives of R2, and T29\'s two'


def make(primitive):
    """Build a primitive from the `primitive` block of an action@1 action."""
    settings = {k: v for k, v in primitive.items() if k != 'name'}
    try:
        return PRIMITIVES[primitive['name']](**settings)
    except KeyError:
        raise ValueError(f'no such primitive: {primitive["name"]!r}')


class ExecutingMind:
    """A chooser of primitives, with the executor running them.

    The chooser — a model (T06) or a scripted mind — answers with a primitive,
    or with a single command when it wants one. The executor turns a primitive
    into commands until it stops, and the chooser is asked again with the stop
    reason in hand, which is what R2 means by "asked when the executor stops".
    """

    def __init__(self, chooser, name=None):
        self.chooser = chooser
        self.name = name or getattr(chooser, 'name', 'executing')
        # The record's vocabulary follows the chooser: the executor itself
        # decides nothing.
        self.kind = getattr(chooser, 'kind', 'scripted')
        self.current = None
        self.last_stop = None
        self.stops = []
        self.chosen = []
        # What to write to the run's journal: the chooser's own decisions and
        # the stop reasons the primitives report. Without these a record
        # cannot say why the agent stopped exploring at a turn, which is what
        # R2 has primitives report stops for.
        self.journal = []

    def choose(self, observation):
        asked = dict(observation)
        if self.last_stop:
            asked['last_stop'] = self.last_stop
        answer = self.chooser.act(asked)
        self.chosen.append(answer)
        self.journal.append({
            'kind': 'choice',
            'turn': observation['turn'],
            'decision': observation['decision'],
            'chooser': getattr(self.chooser, 'name', 'unknown'),
            'after_stop': self.last_stop,
            'chose': (answer['primitive']['name'] if answer['kind'] == 'primitive'
                      else answer.get('command', {}).get('name', answer['kind'])),
            'answer': answer,
        })
        if answer['kind'] == 'primitive':
            self.current = make(answer['primitive'])
            self.last_stop = None
            return None
        self.current = None
        return answer

    # How many primitives may stop without acting before the agent gives up.
    PATIENCE = 6

    def drain_journal(self):
        """The journal entries since the last call, for the run to write out.

        The chooser's own entries come first: a model's calls belong to the
        decision it was asked about.
        """
        drain = getattr(self.chooser, 'drain_journal', None)
        entries = (drain() if drain else []) + self.journal
        self.journal = []
        return entries

    # The executor decides nothing, so for everything a run needs to know
    # about the mind -- the call log, the budget, what to record -- it is
    # transparent and the chooser answers.
    @property
    def call_log(self):
        """The chooser's call log, or None when it keeps none."""
        return getattr(self.chooser, 'call_log', None)

    @call_log.setter
    def call_log(self, value):
        # A chooser that does not call a model has nowhere to put one, and
        # setting it here would only hide that.
        if hasattr(self.chooser, 'call_log'):
            self.chooser.call_log = value

    @property
    def budget(self):
        return getattr(self.chooser, 'budget', None)

    @property
    def parse_failures(self):
        return getattr(self.chooser, 'parse_failures', None)

    @property
    def mind_record(self):
        return getattr(self.chooser, 'mind_record', None)

    def act(self, observation):
        for _ in range(self.PATIENCE):   # a stop may follow a choice at once
            if self.current is None:
                command = self.choose(observation)
                if command is not None:
                    return command
            result, stop = self.current.step(observation)
            if result is not None:
                return result
            self.last_stop = stop
            entry = {'primitive': self.current.name, 'stop': stop,
                     'turn': observation['turn'],
                     'decisions': self.current.decisions}
            self.stops.append(entry)
            self.journal.append({'kind': 'stop', 'decision': observation['decision'], **entry})
            self.current = None
        # Every primitive the chooser offered stopped without acting. That is
        # the agent giving up, not the harness failing, so it is the outcome
        # `agent_stopped` with this reason (R5).
        raise CannotAct(f'no primitive could act at turn {observation["turn"]}; '
                        f'last stops: {self.stops[-self.PATIENCE:]}')
