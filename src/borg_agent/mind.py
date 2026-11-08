"""Minds: who chooses the next action.

T03 needs only the `scripted` mind of R2, which exists for tests: given the
same observations it always answers the same way, so a run can be repeated
and compared. It is deliberately dull. It carries no tactics, no thresholds
and no valuations — those are the model's job (docs/SOURCES.md), and the
primitives it will choose between are T05.

The model-backed and file-backed minds are T06.
"""

ACTION = 'borg-agent/action@1'
# Glyphs a step can land on. Shop entrances (1-8) are left out: a store screen
# is not handled yet. A closed door ('+') is opened with `alter`, not walked
# into.
PASSABLE = set(".<>'·")
DOOR = '+'
# The number-pad directions, and what they add to (x, y).
DIRECTIONS = {1: (-1, 1), 2: (0, 1), 3: (1, 1), 4: (-1, 0),
              6: (1, 0), 7: (-1, -1), 8: (0, -1), 9: (1, -1)}
# Tried in this order, so the choice never depends on dictionary order.
ORDER = (6, 2, 4, 8, 3, 1, 9, 7)


def action(kind, reason, **payload):
    return {'schema': ACTION, 'kind': kind, 'reason': reason, **payload}


class ScriptedMind:
    """Walks where it can, answers what it must, and never guesses.

    It keeps one piece of state, the direction it is going, so it crosses a
    room instead of jittering on the spot. That state is a function of the
    observations it has seen, so a replay of the same game gives the same
    answers.
    """

    name = 'scripted'
    kind = 'scripted'

    def __init__(self, heading=6):
        self.heading = heading
        self.decisions = 0

    def glyph_at(self, observation, x, y):
        """What the player knows is at (x, y), or None outside the window."""
        map_ = observation['map']
        origin = map_.get('origin', {'x': 0, 'y': 0})
        row = y - origin['y']
        column = x - origin['x']
        if row < 0 or row >= len(map_['rows']):
            return None
        line = map_['rows'][row]
        if column < 0 or column >= len(line):
            return None
        return line[column]

    def occupied(self, observation, x, y):
        return any(m['x'] == x and m['y'] == y for m in observation['monsters'])

    def step(self, observation, direction):
        """(glyph, occupied) one step away in a number-pad direction."""
        dx, dy = DIRECTIONS[direction]
        player = observation['map']['player']
        x, y = player['x'] + dx, player['y'] + dy
        return self.glyph_at(observation, x, y), self.occupied(observation, x, y)

    def act(self, observation):
        self.decisions += 1
        prompt = observation.get('prompt') or {'kind': 'none'}

        # A prompt is answered before anything else: the game is waiting for
        # that answer and no other key will do.
        if prompt['kind'] == 'more':
            return action('command', 'Clear the -more- prompt.', command={'name': 'answer', 'answer': '\r'})
        if prompt['kind'] == 'yes_no':
            return action('command', 'Answer no: this mind never agrees to anything it did not ask for.',
                          command={'name': 'answer', 'answer': 'n'})
        if prompt['kind'] in ('item', 'menu', 'text', 'command'):
            return action('command', 'Leave a prompt this mind does not understand.',
                          command={'name': 'escape'})

        # Standing on a down staircase is reason enough to use it: that way a
        # test run meets the dungeon, not only the town.
        player = observation['map']['player']
        if self.glyph_at(observation, player['x'], player['y']) == '>':
            return action('command', 'Standing on a down staircase: take it.',
                          command={'name': 'go_down'})

        # Keep going the same way while that square can be stepped on.
        for direction in (self.heading,) + ORDER:
            glyph, occupied = self.step(observation, direction)
            if occupied or glyph is None:
                continue
            if glyph in PASSABLE:
                self.heading = direction
                return action('command', f'Step {direction}: the square is known and free.',
                              command={'name': 'walk', 'direction': direction})
            if glyph == DOOR:
                self.heading = direction
                return action('command', f'Open the door {direction}.',
                              command={'name': 'alter', 'direction': direction})
        return action('command', 'Nowhere known to step: stay put.', command={'name': 'stay'})


class PrimitiveMind:
    """A chooser of primitives, for tests (R2's `scripted` mind, one layer up).

    It is a fixture, not a policy: its rules are the shortest ones that
    exercise every primitive deterministically. A mind **may** hold thresholds
    — that is its job — which is why the half-health limit below lives here
    and not in the executor.
    """

    name = 'scripted-primitives'
    kind = 'scripted'

    def __init__(self):
        self.dead_ends = 0

    def act(self, observation):
        prompt = observation.get('prompt') or {'kind': 'none'}
        character = observation['character']
        monsters = observation['monsters']
        player = observation['map']['player']
        last = observation.get('last_stop')

        if prompt['kind'] == 'more':
            return action('command', 'Clear the -more- prompt.',
                          command={'name': 'answer', 'answer': '\r'})
        if prompt['kind'] == 'yes_no':
            return action('command', 'Answer no to a question I did not ask.',
                          command={'name': 'answer', 'answer': 'n'})
        if prompt['kind'] != 'none':
            return action('command', 'Leave a prompt I do not understand.',
                          command={'name': 'escape'})

        adjacent = [m for m in monsters
                    if max(abs(m['x'] - player['x']), abs(m['y'] - player['y'])) <= 1]
        if adjacent:
            self.dead_ends = 0
            return action('primitive', 'Something is next to me; fight it.',
                          primitive={'name': 'fight_nearest',
                                     'stop_if_hp_below': max(1, character['max_hp'] // 2)})
        if character['hp'] < character['max_hp'] and not monsters:
            self.dead_ends = 0
            return action('primitive', 'Hurt and alone; rest.',
                          primitive={'name': 'rest_until_healed'})
        # Exploring the town never ends — its dark edges are always a frontier —
        # so hand back after a while and go down if a staircase is known. The
        # limit and the preference are judgements, which is why they are here.
        if last == 'decision_limit' and squares_with_glyph(observation, '>'):
            self.dead_ends = 0
            return action('primitive', 'Seen enough of this floor; go down.',
                          primitive={'name': 'take_stairs', 'direction': 'down'})
        if last in ('explored', 'no_stairs_known', 'no_path'):
            self.dead_ends += 1
            if self.dead_ends >= 2:
                self.dead_ends = 0
                return action('command', 'Nothing left to do here; wait a turn.',
                              command={'name': 'stay'})
            if last == 'explored':
                return action('primitive', 'This floor is known; go down.',
                              primitive={'name': 'take_stairs', 'direction': 'down'})
            return action('primitive', 'No way down that I know; keep exploring.',
                          primitive={'name': 'explore_floor'})
        self.dead_ends = 0
        return action('primitive', 'Explore what I have not seen.',
                      primitive={'name': 'explore_floor', 'max_decisions': 150})


def squares_with_glyph(observation, glyph):
    """Whether the player's known map shows a glyph anywhere."""
    return any(glyph in row for row in observation['map']['rows'])
