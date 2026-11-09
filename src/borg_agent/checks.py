"""The rules a JSON Schema cannot express.

A schema checks shapes. Two of this repository's rules compare one field with
another, which draft 2020-12 cannot do:

- **R1.1**: an observation's `true_state` must *name* every true-state field it
  carries, so a reader never has to guess which values the player could not
  have known;
- **R4.3**: a model never promotes its own claim past `hypothesis`. What moves
  it on is counted trials, a probe, or a review **by a different model
  family** — and "different" is a comparison.

Each function returns a list of problems, empty when there are none, so a
caller can report them all at once. `enforce` raises instead.
"""

PROMOTED = ('supported', 'corroborated', 'refuted')
COUNTED = ('quantified', 'intervened')
# `documented` ranks above `hypothesis` too, and the schema only ties it to the
# `manual` basis: a model asserting "the manual says so" is the same act R4.3
# distrusts, so it is refused here as well (milestone 3 review, finding 10).
MODEL_MAY_NOT_CLAIM = PROMOTED + ('documented',)


def enforce(problems, what='document'):
    if problems:
        raise ValueError(f'{what}: ' + '; '.join(problems))


def check_observation(observation):
    """R1.1: true-state fields are named as such."""
    problems = []
    true_state = observation.get('true_state')
    if true_state is None:
        return problems
    named = set(true_state.get('fields') or ())
    present = set(true_state) - {'fields'}
    for field in sorted(present - named):
        problems.append(f'true_state carries {field!r} without naming it in fields')
    for field in sorted(named - present):
        problems.append(f'true_state names {field!r} in fields but does not carry it')
    return problems


def check_claim(claim):
    """R4, R4.3: the lifecycle rules that compare fields with each other."""
    problems = []
    basis = claim.get('basis') or {}
    produced_by = claim.get('produced_by') or {}
    reviews = claim.get('reviews') or []
    status = claim.get('status')

    if basis.get('kind') == 'quantified':
        trials, successes = basis.get('trials'), basis.get('successes')
        if trials is not None and successes is not None and successes > trials:
            problems.append(f'a quantified basis claims {successes} successes of {trials} trials')

    if produced_by.get('mind') == 'model':
        for field in ('model', 'family'):
            if not produced_by.get(field):
                problems.append(f'a model-produced claim must name its {field} (R4.3)')

    if status in PROMOTED:
        own_family = produced_by.get('family')
        counted = basis.get('kind') in COUNTED
        agreed = [review for review in reviews if review.get('verdict') == 'agree']
        by_another = [review for review in agreed
                      if review.get('family') is None or review.get('family') != own_family]
        if not counted and not by_another:
            problems.append(
                f'status {status!r} needs counted trials, a probe, or an agreeing review by '
                f'another family than {own_family!r} (R4.3)')
        same_family_only = agreed and not by_another
        if same_family_only:
            problems.append(f'every agreeing review is of the producer\'s own family '
                            f'({own_family!r}), which does not promote a claim (R4.3)')
    if status == 'corroborated' and not reviews and basis.get('kind') not in COUNTED:
        problems.append("'corroborated' names the probe or the review that moved it (R4.3)")

    if produced_by.get('mind') == 'model' and status in MODEL_MAY_NOT_CLAIM:
        if status == 'documented':
            problems.append(
                "a model does not give its own claim the status 'documented': the game's manual "
                'says so or it does not, and someone else checks that (R4.3)')

    # A review with no family is a probe (claim@1: `by` is the probe run's id),
    # and nothing checked that the run existed -- so an invented probe review
    # promoted a claim. A probe names a run this claim's own evidence carries.
    # Mode C rests on this (PLAN.md T22).
    runs = {evidence.get('run_id') for evidence in (claim.get('evidence') or [])
            if evidence.get('kind') == 'run'}
    for review in reviews:
        if review.get('family') is None and review.get('by') != 'owner' \
                and review.get('by') not in runs:
            problems.append(
                f'the probe review {review.get("by")!r} names no run in this claim\'s evidence, '
                f'so there is nothing to check it against (R4.3)')
    return problems
