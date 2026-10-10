"""Read-only stage-6 input snapshots and dependency freshness, no ranking or network."""
import copy
from pathlib import Path
from jsonschema.exceptions import ValidationError

from runtime import inside, check_schema
from literature_output import load_state, checked, verify_sources, digest
import research_session as rs


def validate_card(card):
    check_schema('research-card.schema.json', card)
    if any(r['answer'] is None for r in card['dialogue']):
        raise ValueError('Three actual answers are required')
    sources = {'initial': card['initial_idea']}
    sources.update({f'answer{r["number"]}': r['answer']['text'] for r in card['dialogue']})
    sources.update({a['id']: a['text'] for a in card['amendments']})
    for entry in card['entries']:
        if entry['origin'] == 'user_explicit' and not entry['source_quotes']:
            raise ValueError('Explicit research goal lacks user provenance')
        if entry['category'] == 'unknown' and entry['origin'] != 'unresolved':
            raise ValueError('Unknown condition cannot become a confirmed requirement')
        if entry['category'] == 'suggestion' and entry['origin'] != 'agent_proposal':
            raise ValueError('Suggestion must remain an Agent proposal')
        for quote in entry['source_quotes']:
            if quote['source_ref'] not in sources or quote['quote'] not in sources[quote['source_ref']]:
                raise ValueError('Goal citation does not match recorded user words')


def capture(root, binding):
    """The caller holds the project lock. Nothing is written to earlier-stage inputs."""
    if set(binding) != {'session_root', 'session_id', 'collection'}:
        raise ValueError('Binding requires session_root, session_id and collection')
    session = rs.load(inside(root, binding['session_root']), binding['session_id'])
    if session['state'] != 'ready' or session['card_stale'] or not session['cards']:
        raise ValueError('Research exploration is unfinished or its card is stale')
    card = copy.deepcopy(session['cards'][-1])
    validate_card(card)
    collection = load_state(inside(root, binding['collection']))
    if not collection['papers']:
        raise ValueError('No reviewed papers in collection')
    papers = {}
    for pid, paper in sorted(collection['papers'].items()):
        checked(paper['record'])
        if paper['record']['paper_id'] != pid:
            raise ValueError('Paper ID and collection key differ')
        verify_sources(Path(root), paper)
        papers[pid] = {'record': copy.deepcopy(paper['record']), 'source_files': copy.deepcopy(paper['source_files'])}
    # Notes, venues and pending edits cannot silently become facts or change scientific ranking.
    return {'binding': copy.deepcopy(binding), 'session_revision': session['revision'],
            'collection_revision': collection['revision'], 'card': card, 'papers': papers,
            'card_digest': digest(card), 'paper_digests': {pid: digest(p) for pid,p in papers.items()}}


def freshness(root, snapshot):
    try:
        current = capture(root, snapshot['binding'])
    except (ValueError, OSError, KeyError, TypeError, ValidationError) as exc:
        return {'current': False, 'goal_changed': True, 'changed_papers': [], 'added_papers': [],
                'removed_papers': [], 'input_error': str(exc)}
    old = snapshot['paper_digests']
    new = current['paper_digests']
    result = {'goal_changed': snapshot['card_digest'] != current['card_digest'],
              'changed_papers': sorted(pid for pid in old.keys() & new.keys() if old[pid] != new[pid]),
              'added_papers': sorted(new.keys() - old.keys()), 'removed_papers': sorted(old.keys() - new.keys()),
              'input_error': None}
    result['current'] = not any(result[k] for k in ('goal_changed','changed_papers','added_papers','removed_papers'))
    return result


def evidence_context(snapshot, paper_id, refs):
    record = snapshot['papers'][paper_id]['record']
    assertions = {a['id']: a for a in record['assertions']}
    evidence = {e['id']: e for e in record['evidence']}
    contexts = []
    for ref in refs:
        a = assertions.get(ref['assertion_id'])
        if a is None or a['review_status'] == 'unreviewed' or a['status'] == 'not_checked':
            raise ValueError('Reference must point to a reviewed assertion in this paper')
        if not set(ref['evidence_ids']).issubset(a['evidence_ids']):
            raise ValueError('Evidence does not belong to the cited assertion')
        if a['status'] == 'supported' and not ref['evidence_ids']:
            raise ValueError('Supported reference requires an evidence location')
        contexts.append({'assertion': a, 'evidence': [evidence[eid] for eid in ref['evidence_ids']]})
    return contexts
