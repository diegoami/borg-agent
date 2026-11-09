"""The minds that are not scripted: a person at a file, and a model (T06).

Both answer the same question as the scripted mind — one action, with a
one-line reason — and both are asked through the same prompt pack, so what
a model was told is recorded and can be cited.

Nothing here ever logs a key, a request header or a URL with credentials
(RULES 16). The key is read from the environment when a call is made, and the
record carries the provider's host and the name of the variable's *job*, not
the variable.
"""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import checks, prompts, signals

CALL_LOG = 'model-calls.jsonl'
ANSWER_PATTERN = 'answer-{decision}.json'
QUESTION_PATTERN = 'question-{decision}.json'
# Two tries at a valid answer, then the agent stops and says so.
TRIES = 2
CORRECTION = ('Your last answer could not be read as one action. Answer with exactly one JSON '
              'object and nothing else, in the shape the system message gives.')


def extract_action(text):
    """The first JSON object in a reply, as an action.

    A model that wraps its answer in prose or a fenced block is still
    answering; a model that answers twice is not, and the first object is
    taken.
    """
    if not text:
        raise ValueError('the reply was empty')
    start = text.find('{')
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for index in range(start, len(text)):
            character = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif character == '\\':
                    escaped = True
                elif character == '"':
                    in_string = False
                continue
            if character == '"':
                in_string = True
            elif character == '{':
                depth += 1
            elif character == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:index + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find('{', start + 1)
    raise ValueError('the reply held no JSON object')


class Budget:
    """What a run is allowed to spend on a model (R2.3)."""

    def __init__(self, model_calls=None, tokens=None):
        self.allowed = {'model_calls': model_calls, 'tokens': tokens}
        self.used = {'model_calls': 0, 'tokens': 0, 'prompt_tokens': 0, 'completion_tokens': 0}

    def check(self):
        for name, limit in self.allowed.items():
            if limit is not None and self.used.get(name, 0) >= limit:
                raise signals.BudgetSpent(self.used, self.allowed)

    def spend(self, prompt_tokens=0, completion_tokens=0):
        self.used['model_calls'] += 1
        self.used['prompt_tokens'] += prompt_tokens
        self.used['completion_tokens'] += completion_tokens
        self.used['tokens'] += prompt_tokens + completion_tokens

    def record(self):
        return {'allowed': dict(self.allowed), 'used': dict(self.used)}


class CallLog:
    """Every model call, as R2.1 asks: what was asked, what came back, what it cost."""

    def __init__(self, path):
        self.path = Path(path)
        self.count = 0

    def write(self, entry):
        # A model's words may hold anything, and they reach more fields than
        # the reply: `reason` and `note` are pulled out of the same answer. So
        # every field that looks like a credential is removed, not only the
        # reply (milestone 3 review, finding 3 -- redacting `reply` alone left
        # a key in `reason` in the log).
        entry = _redacted(entry)
        with self.path.open('a') as log:
            log.write(json.dumps(entry, sort_keys=True) + '\n')
        self.count += 1

    def sha256(self):
        from .build import sha

        return sha(self.path) if self.path.exists() else None


REMOVED = '[removed: it looked like a credential]'


def _redacted(value, name=''):
    """The same document with every credential-shaped part replaced.

    A log entry is scanned the way a record is (`record.secrets_in`), but a
    record is refused while a log is written: the call has already happened and
    the rest of the entry is the evidence R2.1 asks for. So each offending
    part is replaced where it stands, and the entry says so.
    """
    from .record import SECRET_NAMES, SECRET_VALUE
    import re

    if name.lower() in SECRET_NAMES:
        return REMOVED
    if isinstance(value, dict):
        return {key: _redacted(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted(item) for item in value]
    if isinstance(value, str) and re.search(SECRET_VALUE, value):
        return REMOVED
    return value


class ChatClient:
    """One OpenAI-compatible chat endpoint, and the key that opens it.

    The key is read once, lives in this object, and leaves it only as an
    Authorization header. Nothing else in the repository sees it.
    """

    def __init__(self, choice, environ=None, timeout=120):
        self.choice = choice
        self.timeout = timeout
        self._key = choice.key(environ)      # fails here, before any play

    def post(self, messages, **options):
        body = json.dumps({
            'model': self.choice.model,
            'messages': messages,
            **({'reasoning_effort': self.choice.effort} if self.choice.effort else {}),
            **options,
        }).encode()
        request = urllib.request.Request(
            self.choice.base_url.rstrip('/') + '/chat/completions', data=body,
            headers={'Content-Type': 'application/json',
                     'Authorization': f'Bearer {self._key}'})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            # The body may explain the refusal; it may also quote the request,
            # so only the status and the first line are kept.
            detail = (error.read(400).decode(errors='replace') or '').splitlines()
            raise signals.ModelFailed(
                f'{self.choice.provider} answered {error.code} '
                f'({detail[0][:160] if detail else "no body"})') from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise signals.ModelFailed(
                f'{self.choice.provider} could not be reached: {type(error).__name__}') from None


def reply_of(answer):
    """The text of a chat answer, and what it cost."""
    choices = answer.get('choices') or []
    reply = (choices[0].get('message') or {}).get('content') or '' if choices else ''
    usage = answer.get('usage') or {}
    return reply, usage


class ExternalMind:
    """A person, or another session, answering from a file.

    Each decision is written to `question-<n>.json` with the prompt the model
    would have been given, and the answer is read from `answer-<n>.json`. For
    debugging a few decisions by hand (R2), and for driving the agent from
    somewhere this repository cannot call.
    """

    name = 'external'
    kind = 'external'

    def __init__(self, directory, pack=None, timeout=600, poll=0.5, log=print):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.pack = pack or prompts.load_pack()
        self.timeout = timeout
        self.poll = poll
        self.log = log
        self.decisions = 0

    def act(self, observation):
        decision = observation['decision']
        question = self.directory / QUESTION_PATTERN.format(decision=decision)
        answer = self.directory / ANSWER_PATTERN.format(decision=decision)
        question.write_text(json.dumps({
            'observation': observation,
            'prompt': prompts.render(self.pack, observation),
            'answer_to': str(answer),
        }, indent=2, sort_keys=True) + '\n')
        self.log(f'waiting for {answer}')
        deadline = time.monotonic() + self.timeout
        while not answer.exists():
            if time.monotonic() >= deadline:
                raise signals.CannotAct(f'no answer in {answer} after {self.timeout}s')
            time.sleep(self.poll)
        self.decisions += 1
        return json.loads(answer.read_text())


class ApiMind:
    """A model over an OpenAI-compatible chat API, from the active profile (D7)."""

    name = 'api'
    kind = 'api'

    def __init__(self, choice, pack=None, budget=None, call_log=None, knowledge=None,
                 timeout=120, environ=None, transport=None, choice_record=None,
                 knowledge_sha256=None):
        self.choice = choice
        # What the loader said about this job, for the record. Passed in so the
        # mind never re-reads the configuration behind the run's back.
        self.choice_record = choice_record or {}
        self.knowledge_sha256 = knowledge_sha256
        self.pack = pack or prompts.load_pack()
        self.budget = budget or Budget()
        self.call_log = call_log
        self.knowledge = knowledge
        self.timeout = timeout
        if transport is None:
            choice.key(environ)              # fails here, before play, if unset
        self.client = None if transport else ChatClient(choice, environ, timeout)
        self.transport = transport or self.client.post
        self.decisions = 0
        self.parse_failures = 0
        self.journal = []

    # --- the call ----------------------------------------------------------

    def act(self, observation):
        decision = observation['decision']
        question = self.directory / QUESTION_PATTERN.format(decision=decision)
        answer = self.directory / ANSWER_PATTERN.format(decision=decision)
        question.write_text(json.dumps({
            'observation': observation,
            'prompt': prompts.render(self.pack, observation),
            'answer_to': str(answer),
        }, indent=2, sort_keys=True) + '\n')
        self.log(f'waiting for {answer}')
        deadline = time.monotonic() + self.timeout
        while not answer.exists():
            if time.monotonic() >= deadline:
                raise signals.CannotAct(f'no answer in {answer} after {self.timeout}s')
            time.sleep(self.poll)
        self.decisions += 1
        return json.loads(answer.read_text())


class ApiMind:
    """A model over an OpenAI-compatible chat API, from the active profile (D7)."""

    name = 'api'
    kind = 'api'

    def __init__(self, choice, pack=None, budget=None, call_log=None, knowledge=None,
                 timeout=120, environ=None, transport=None, choice_record=None,
                 knowledge_sha256=None):
        self.choice = choice
        # What the loader said about this job, for the record. Passed in so the
        # mind never re-reads the configuration behind the run's back.
        self.choice_record = choice_record or {}
        self.knowledge_sha256 = knowledge_sha256
        self.pack = pack or prompts.load_pack()
        self.budget = budget or Budget()
        self.call_log = call_log
        self.knowledge = knowledge
        self.timeout = timeout
        if transport is None:
            choice.key(environ)              # fails here, before play, if unset
        self.client = None if transport else ChatClient(choice, environ, timeout)
        self.transport = transport or self.client.post
        self.decisions = 0
        self.parse_failures = 0
        self.journal = []

    # --- the call ----------------------------------------------------------

    def _post(self, messages):
        """One chat completion. The key is a header and never leaves this method."""
        body = json.dumps({
            'model': self.choice.model,
            'messages': messages,
            **({'reasoning_effort': self.choice.effort} if self.choice.effort else {}),
        }).encode()
        request = urllib.request.Request(
            self.choice.base_url.rstrip('/') + '/chat/completions', data=body,
            headers={'Content-Type': 'application/json',
                     'Authorization': f'Bearer {self._key}'})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            # The body may explain the refusal; it may also quote the request,
            # so only the status and the first line are kept.
            detail = (error.read(400).decode(errors='replace') or '').splitlines()
            raise signals.ModelFailed(
                f'{self.choice.provider} answered {error.code} '
                f'({detail[0][:160] if detail else "no body"})') from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise signals.ModelFailed(
                f'{self.choice.provider} could not be reached: {type(error).__name__}') from None

    def act(self, observation):
        messages = prompts.render(self.pack, observation, knowledge=self.knowledge)
        for attempt in range(1, TRIES + 1):
            self.budget.check()
            started = time.monotonic()
            answer = self.transport(messages)
            elapsed = round(time.monotonic() - started, 3)
            usage = (answer.get('usage') or {})
            self.budget.spend(usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
            reply, _usage = reply_of(answer)
            action, problem = None, None
            try:
                action = extract_action(reply)
                from jsonschema import Draft202012Validator

                schema = json.loads(
                    (prompts.pins.ROOT / 'schemas/action@1.json').read_text())
                errors = sorted(Draft202012Validator(schema).iter_errors(action), key=str)
                if errors:
                    raise ValueError('; '.join(e.message for e in errors[:2]))
            except ValueError as error:
                problem = str(error)
                action = None
                self.parse_failures += 1
            self._log(observation, messages, reply, usage, elapsed, attempt, problem, action)
            if action is not None:
                self.decisions += 1
                return action
            messages = messages + [{'role': 'assistant', 'content': reply},
                                   {'role': 'user', 'content': CORRECTION}]
        raise signals.CannotAct(
            f'{self.choice.model} did not answer with a valid action in {TRIES} tries '
            f'at decision {observation["decision"]}: {problem}')

    def _log(self, observation, messages, reply, usage, elapsed, attempt, problem, action):
        if self.call_log is None:
            return
        from .record import state_hash

        entry = {
            'decision': observation['decision'],
            'turn': observation['turn'],
            'attempt': attempt,
            'observation_sha256': state_hash(observation),
            'prompt_pack': self.pack.version,
            'prompt_pack_sha256': self.pack.sha256,
            'prompt_chars': sum(len(message['content']) for message in messages),
            'job': self.choice.job,
            'provider': self.choice.provider,
            'model': self.choice.model,
            'family': self.choice.family,
            'effort': self.choice.effort,
            'endpoint_host': self.choice.endpoint_host(),
            'reply': reply,
            'reason': (action or {}).get('reason'),
            'note': (action or {}).get('note'),
            'parse_problem': problem,
            'prompt_tokens': usage.get('prompt_tokens'),
            'completion_tokens': usage.get('completion_tokens'),
            'seconds': elapsed,
        }
        self.call_log.write(entry)

    def drain_journal(self):
        entries, self.journal = self.journal, []
        return entries

    @property
    def mind_record(self):
        """What the run record says about this mind (R2.1-R2.4, D7).

        The profile, the provider, the model, the family, how they were
        chosen, the prompt pack, the budget and what each job spent. Never a
        key, a header or a URL.
        """
        return {
            'kind': 'api',
            **{name: value for name, value in self.choice_record.items()},
            'prompt_pack': self.pack.record(),
            'knowledge_sha256': self.knowledge_sha256,
            'budget': dict(self.budget.allowed),
            'jobs': {
                self.choice.job: {
                    'provider': self.choice.provider,
                    'model': self.choice.model,
                    'family': self.choice.family,
                    'chosen_by': self.choice.chosen_by,
                    'profile': self.choice.profile,
                    'effort': self.choice.effort,
                    'context_k': self.choice.context_k,
                    'endpoint_host': self.choice.endpoint_host(),
                    'calls': self.budget.used['model_calls'],
                    'prompt_tokens': self.budget.used['prompt_tokens'],
                    'completion_tokens': self.budget.used['completion_tokens'],
                },
            },
        }
