"""models.yaml's shape, checked without a YAML parser.

The real loader, its JSON Schema and the run-time rules are T06; `pyyaml` is
not a dependency yet. These checks are the ones that would hurt most if they
were wrong while the file is only read by people: a key in the file, a job
missing, or a reviewer of the consolidator's own family (R4.3).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'models.yaml'
JOBS = ('play', 'consolidate', 'review')
TEXT = MODELS.read_text()
LINES = [line for line in TEXT.splitlines() if line.strip() and not line.lstrip().startswith('#')]


def top_level(key):
    """The lines of one top-level block."""
    out, inside = [], False
    for line in LINES:
        if not line.startswith(' '):
            inside = line.split(':')[0] == key
            continue
        if inside:
            out.append(line)
    return out


def scalar(key):
    return next(line.split(':', 1)[1].strip() for line in LINES
                if not line.startswith(' ') and line.split(':')[0] == key)


def entries(lines):
    """`name: {a: b, c: d}` and `- {a: b}` lines, as (name, mapping) pairs."""
    found = []
    for line in lines:
        match = re.fullmatch(r'\s*(?:(\w+):\s*|- )\{(.*)\}', line)
        if match:
            name, body = match.groups()
            found.append((name, dict(part.split(': ', 1) for part in body.split(', '))))
    return found


def providers():
    names = {}
    current = None
    for line in top_level('providers'):
        if re.fullmatch(r'  (\w+):', line):
            current = line.strip().rstrip(':')
            names[current] = {}
        elif current and ':' in line:
            field, value = line.strip().split(':', 1)
            names[current][field] = value.strip()
    return names


def profiles():
    found, current = {}, None
    for line in top_level('profiles'):
        if re.fullmatch(r'  (\w+):', line):
            current = line.strip().rstrip(':')
            found[current] = {}
        elif current:
            for name, mapping in entries([line]):
                found[current][name] = mapping
    return found


def test_the_schema_and_default_profile():
    assert scalar('schema') == 'borg-agent/models@1'
    assert scalar('default_profile') in profiles()


def test_every_provider_names_a_key_variable_and_cites_its_source():
    for name, provider in providers().items():
        assert provider['base_url'].startswith('https://'), name
        assert re.fullmatch(r'[A-Z][A-Z0-9_]*', provider['api_key_env']), name
        assert provider['source'].startswith('https://'), name


def test_every_profile_has_every_job_with_a_known_provider():
    known = set(providers())
    assert profiles()
    for name, jobs in profiles().items():
        assert tuple(jobs) == JOBS, (name, tuple(jobs))
        for job, settings in jobs.items():
            assert settings['provider'] in known, (name, job)
            assert settings['model'] and settings['family'], (name, job)
            if 'context_k' in settings:
                assert int(settings['context_k']) > 0, (name, job)


def test_a_review_is_a_different_family_from_the_consolidator():
    # Requirements R4.3: a model never reviews its own family's claims.
    for name, jobs in profiles().items():
        assert jobs['review']['family'] != jobs['consolidate']['family'], name


def test_the_trial_lists_known_providers_per_job():
    candidates = entries(top_level('trial'))
    assert candidates
    known = set(providers())
    for _name, candidate in candidates:
        assert candidate['provider'] in known, candidate
        assert candidate['model'] and candidate['family'], candidate


def test_the_file_holds_no_key():
    for line in LINES:
        for field in re.findall(r'(\w*key\w*)\s*:', line, flags=re.IGNORECASE):
            assert field == 'api_key_env', line
    # No long opaque token anywhere, whatever it is called.
    assert not re.search(r'\b[A-Za-z0-9_-]{32,}\b', TEXT.replace('nemotron-3-ultra-550b-a55b', '')), TEXT


def test_the_local_override_is_ignored_by_git():
    # It holds the owner's chosen profile on their machine; it is never committed.
    assert 'models.local.yaml' in (ROOT / '.gitignore').read_text().split()


def test_the_trial_can_always_pair_a_reviewer_of_another_family():
    # Review finding 8: T09 must never pair a consolidator with a reviewer of
    # its own family (R4.3), so for every consolidate candidate there has to be
    # a review candidate of a different family.
    candidates = {}
    for job in ('consolidate', 'review'):
        block, inside = [], False
        for line in top_level('trial'):
            if re.fullmatch(r'  (\w+):', line):
                inside = line.strip().rstrip(':') == job
                continue
            if inside:
                block.append(line)
        candidates[job] = [mapping for _name, mapping in entries(block)]
    assert candidates['consolidate'] and candidates['review']
    reviewer_families = {c['family'] for c in candidates['review']}
    for consolidator in candidates['consolidate']:
        others = reviewer_families - {consolidator['family']}
        assert others, (consolidator, reviewer_families)


def test_every_job_has_trial_candidates():
    for job in ('play', 'consolidate', 'review'):
        block, inside = [], False
        for line in top_level('trial'):
            if re.fullmatch(r'  (\w+):', line):
                inside = line.strip().rstrip(':') == job
                continue
            if inside:
                block.append(line)
        assert entries(block), job
