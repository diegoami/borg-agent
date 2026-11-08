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
