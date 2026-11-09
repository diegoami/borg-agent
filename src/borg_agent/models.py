"""Which model does which job: `models.yaml` and the active profile (D7).

This file is the only model rule in the repository. No recommendation
service, no ranking, no fallback chain: a profile names one model per job,
and the active profile is the first of

1. the environment variable `BORG_AGENT_PROFILE`;
2. `profile:` in `models.local.yaml`, which git ignores and which may also
   override single jobs;
3. `default_profile` in `models.yaml`.

Neither file ever holds a key. A provider names the environment variable that
holds its key, and the key is read from the environment when a run needs it —
never logged, never recorded, never put in a URL (RULES 16).
"""
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import pins

JOBS = ('play', 'consolidate', 'review')
MODELS_FILE = 'models.yaml'
LOCAL_FILE = 'models.local.yaml'
SCHEMA_FILE = 'models@1.json'
# What a job may use when its profile does not say (R2.2). Deliberately small:
# a prompt that needs more than this says so in the profile, where the owner
# can see it.
DEFAULT_CONTEXT_K = 32
# How a job's model came to be chosen, for the run record.
BY_ENVIRONMENT = 'environment'
BY_PROFILE = 'profile'
BY_LOCAL = 'local override'
# The one field name that may contain "key": it holds a variable's name.
ALLOWED_KEY_FIELD = 'api_key_env'


class ConfigurationError(ValueError):
    """models.yaml, models.local.yaml or the environment is wrong.

    Always raised before a run starts, so a bad configuration never shows up
    as a strange outcome halfway through a game.
    """


@dataclass(frozen=True)
class Choice:
    """The model one job will use, and where everything about it came from."""

    job: str
    provider: str
    model: str
    family: str
    base_url: str
    api_key_env: str
    context_k: int
    effort: str | None
    profile: str
    chosen_by: str

    def key(self, environ=None):
        """The provider's key, read from the environment when it is needed.

        Fails before play when the variable is unset, naming the variable and
        never its value.
        """
        environ = os.environ if environ is None else environ
        value = environ.get(self.api_key_env)
        if not value:
            raise ConfigurationError(
                f'the {self.job} job uses the {self.provider} provider, whose key comes from '
                f'${self.api_key_env}, and that variable is not set')
        return value

    def endpoint_host(self):
        """The host of the base URL, which is all a record may carry."""
        return self.base_url.split('://', 1)[-1].split('/', 1)[0]


@dataclass(frozen=True)
class Models:
    """The whole configuration, as one run sees it."""

    profile: str
    jobs: dict
    trial: dict
    models_sha256: str
    models_local_sha256: str | None
    paths: dict = field(default_factory=dict)

    def __getitem__(self, job):
        try:
            return self.jobs[job]
        except KeyError:
            raise ConfigurationError(f'no such job: {job!r}; the jobs are {JOBS}') from None

    def record(self, job):
        """What the run record says about this job's model (R2.4, D7).

        The host, never a URL; the variable's name, never the key.
        """
        choice = self[job]
        return {
            'job': choice.job,
            'profile': choice.profile,
            'provider': choice.provider,
            'model': choice.model,
            'family': choice.family,
            'effort': choice.effort,
            'chosen_by': choice.chosen_by,
            'context_k': choice.context_k,
            'endpoint_host': choice.endpoint_host(),
            'models_sha256': self.models_sha256,
            'models_local_sha256': self.models_local_sha256,
        }

    def missing_keys(self, jobs=None, environ=None):
        """The key variables that are not set, for the jobs named."""
        environ = os.environ if environ is None else environ
        missing = []
        for job in jobs or self.jobs:
            choice = self[job]
            if not environ.get(choice.api_key_env):
                missing.append(choice.api_key_env)
        return sorted(set(missing))


def _schema():
    return json.loads((pins.ROOT / 'schemas' / SCHEMA_FILE).read_text())


def _validate(document, schema, where):
    from jsonschema import Draft202012Validator

    errors = sorted(Draft202012Validator(schema).iter_errors(document), key=str)
    if errors:
        raise ConfigurationError(f'{where}: ' + '; '.join(
            f'{list(e.absolute_path)}: {without_credentials(e.message)}' for e in errors[:4]))


def without_credentials(message):
    """A message that quotes a value, with anything key-shaped taken out.

    `key_fields` refuses a field *named* like a key before any validator runs,
    but a key pasted as a value (into `model:`, say) reaches the validator,
    whose message quotes what it saw. Nothing about a misconfiguration is worth
    printing a credential for (review's smaller notes).
    """
    import re

    from .record import SECRET_VALUE

    return re.sub(SECRET_VALUE, '[removed]', str(message))


def key_fields(document, path=''):
    """Field names that contain "key" and are not `api_key_env`.

    A key belongs in the environment, so a field that looks like one is a
    mistake worth refusing rather than ignoring — in either file.
    """
    found = []
    if isinstance(document, dict):
        for name, value in document.items():
            where = f'{path}.{name}' if path else str(name)
            if 'key' in str(name).lower() and name != ALLOWED_KEY_FIELD:
                found.append(where)
            found += key_fields(value, where)
    elif isinstance(document, list):
        for index, value in enumerate(document):
            found += key_fields(value, f'{path}[{index}]')
    return found


def _read(path):
    import yaml

    text = Path(path).read_text()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as problem:
        # The parser quotes the line it choked on, which may be the line a key
        # was pasted into (review's smaller notes).
        raise ConfigurationError(f'{Path(path).name} is not valid YAML: '
                                 f'{without_credentials(problem)[:300]}') from None
    if not isinstance(data, dict):
        raise ConfigurationError(f'{Path(path).name}: expected a mapping at the top level')
    return data, hashlib.sha256(text.encode()).hexdigest()


def load(root=None, environ=None, profile=None):
    """Read the configuration and settle which model does which job.

    `profile` overrides the three ways of choosing one, for tests and for a
    run that is told which profile to use.
    """
    root = Path(root or pins.ROOT)
    environ = os.environ if environ is None else environ
    models_path = root / MODELS_FILE
    local_path = root / LOCAL_FILE

    data, models_sha = _read(models_path)
    # Before anything else, and before any validator can quote a value in an
    # error message: a key has no business in this file.
    smuggled = key_fields(data)
    if smuggled:
        raise ConfigurationError(
            f'{MODELS_FILE} holds {", ".join(smuggled)}; a key lives in the environment, and '
            f'only {ALLOWED_KEY_FIELD} may name one')
    _validate(data, _schema(), MODELS_FILE)

    local, local_sha = ({}, None)
    if local_path.exists():
        local, local_sha = _read(local_path)
        smuggled = key_fields(local)
        if smuggled:
            raise ConfigurationError(
                f'{LOCAL_FILE} holds {", ".join(smuggled)}; a key lives in the environment')
        unknown = set(local) - {'profile', *JOBS}  # checked before the schema, as above
        if unknown:
            raise ConfigurationError(
                f'{LOCAL_FILE} may hold `profile` and job overrides only, not '
                f'{", ".join(sorted(unknown))}')
        job_schema = {**_schema()['$defs']['job'], '$defs': _schema()['$defs']}
        for job in JOBS:
            if job in local:
                _validate(local[job], job_schema, f'{LOCAL_FILE}: {job}')

    # 1. the environment, 2. models.local.yaml, 3. default_profile.
    if profile:
        name, chosen_by = profile, BY_PROFILE
    elif environ.get('BORG_AGENT_PROFILE'):
        name, chosen_by = environ['BORG_AGENT_PROFILE'], BY_ENVIRONMENT
    elif local.get('profile'):
        name, chosen_by = local['profile'], BY_PROFILE
    else:
        name, chosen_by = data['default_profile'], BY_PROFILE
    if name not in data['profiles']:
        raise ConfigurationError(
            f'no profile named {name!r}; {MODELS_FILE} has '
            f'{", ".join(sorted(data["profiles"]))}')

    jobs = {}
    for job in JOBS:
        settings = dict(data['profiles'][name][job])
        how = chosen_by
        if job in local:
            settings = dict(local[job])
            how = BY_LOCAL
        provider = settings['provider']
        if provider not in data['providers']:
            raise ConfigurationError(
                f'the {job} job names the provider {provider!r}, which {MODELS_FILE} does not '
                f'describe')
        described = data['providers'][provider]
        jobs[job] = Choice(
            job=job, provider=provider, model=settings['model'], family=settings['family'],
            base_url=described['base_url'], api_key_env=described['api_key_env'],
            context_k=settings.get('context_k', DEFAULT_CONTEXT_K),
            effort=settings.get('effort'), profile=name, chosen_by=how)

    # R4.3: a review is worth nothing if it comes from the family it reviews.
    if jobs['review'].family == jobs['consolidate'].family:
        raise ConfigurationError(
            f'the review job is {jobs["review"].family!r} and so is the consolidator; a review '
            f'must come from a different model family (R4.3)')

    trial = {}
    for job, candidates in (data.get('trial') or {}).items():
        for candidate in candidates:
            if candidate['provider'] not in data['providers']:
                raise ConfigurationError(
                    f'the trial\'s {job} candidate {candidate["model"]!r} names the provider '
                    f'{candidate["provider"]!r}, which {MODELS_FILE} does not describe')
        trial[job] = [dict(candidate) for candidate in candidates]

    return Models(profile=name, jobs=jobs, trial=trial, models_sha256=models_sha,
                  models_local_sha256=local_sha,
                  paths={'models': str(models_path),
                         'local': str(local_path) if local_sha else None})
