"""Persist three real dialogue rounds and versioned research cards; Agent writes questions."""
import argparse
import copy
import re
from pathlib import Path
from jsonschema.exceptions import ValidationError

from runtime import atomic_text, check_schema, inside, now, read_json, workspace_lock, write_json

def nonblank(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be nonempty text')
    return value

def session_dir(root, sid):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', sid):
        raise ValueError('session_id must contain only letters, digits, _ or -')
    return inside(root, f'sessions/{sid}')

def load(root, sid):
    paths = sorted((session_dir(root, sid) / 'revisions').glob('*.json'))
    if not paths:
        raise ValueError('Session does not exist')
    state = read_json(paths[-1])
    check_schema('research-session.schema.json', state)
    validate_state(state)
    return state

def validate_state(state):
    rounds = state['rounds']
    for number, item in enumerate(rounds, 1):
        expected_basis = 'initial' if number == 1 else f'answer{number-1}'
        if item['number'] != number or item['based_on'] != expected_basis:
            raise ValueError('Invalid dialogue chronology')
        if number < len(rounds) and item['answer'] is None:
            raise ValueError('Later round exists before preceding user answer')
    if not rounds:
        expected_state = 'initial'
    elif rounds[-1]['answer'] is None:
        expected_state = f'round{len(rounds)}_wait'
    else:
        expected_state = 'ready' if len(rounds) == 3 else f'round{len(rounds)}_answered'
    if state['state'] != expected_state:
        raise ValueError('State contradicts saved actual answers')
    sources = user_sources(state)
    refs = [x['user_ref'] for x in sources.values()]
    if len(refs) != len(set(refs)):
        raise ValueError('Duplicate user message provenance')
    for number, amendment in enumerate(state['amendments'], 1):
        if amendment['id'] != f'amendment{number}' or expected_state != 'ready':
            raise ValueError('Invalid amendment chronology')
    for version, card in enumerate(state['cards'], 1):
        if card['version'] != version or card['session_id'] != state['session_id'] or card['purpose'] != state['purpose']:
            raise ValueError('Invalid card version or session provenance')
        if card['dialogue'] != rounds or card['amendments'] != state['amendments'][:len(card['amendments'])]:
            raise ValueError('Card source snapshot contradicts dialogue')
    stale = not state['cards'] or state['cards'][-1]['amendments'] != state['amendments']
    if state['card_stale'] != stale:
        raise ValueError('Invalid card freshness state')

def user_sources(state):
    sources = {'initial': state['initial']}
    for item in state['rounds']:
        if item['answer'] is not None:
            sources[f'answer{item["number"]}'] = item['answer']
    for item in state['amendments']:
        sources[item['id']] = item
    return sources

def export_cards(root, state):
    directory = session_dir(root, state['session_id']) / 'cards'
    for card in state['cards']:
        path = directory / f'v{card["version"]:04d}.json'
        # Cards are immutable; regenerate missing derived exports, never rewrite user edits.
        if not path.exists():
            write_json(path, card)
        md = path.with_suffix('.md')
        if not md.exists():
            origin_labels = {'user_explicit': '用户明确表达', 'agent_proposal': 'Agent 建议', 'unresolved': '尚未明确'}
            category_labels = {'interest': '研究兴趣', 'candidate_direction': '候选方向', 'reading_goal': '阅读目的',
                               'constraint': '资源与条件', 'research_stage': '研究阶段', 'unknown': '待明确问题', 'suggestion': '后续建议'}
            purpose = '合成测试，非真实用户档案' if card['purpose'] == 'synthetic_test' else '实际研究会话'
            lines = [f'# 研究探索卡 v{card["version"]}', '', f'会话：{card["session_id"]}；{purpose}。',
                     '这是当时保存的版本；目标修改后请查看最新探索卡。', '',
                     '本次生成说明：' + card['revision_reason'], '',
                     '## 用户原始想法', '', card['initial_idea'], '', '## 结构化探索条目', '']
            for entry in card['entries']:
                lines += [f'- **{category_labels[entry["category"]]} · {origin_labels[entry["origin"]]}**：{entry["text"]}']
                for citation in entry['source_quotes']:
                    lines.append(f'  - {citation["source_ref"]}：{citation["quote"]}')
            lines += ['', '完整三轮问答、用户修订与出处保存在同版本 JSON 和会话历史中。',
                      '这不是论文事实记录，未知条件不自动变成限制或偏好。', '']
            atomic_text(md, '\n'.join(lines))

def execute(root, sid, action, payload=None):
    payload = payload or {}
    with workspace_lock(root) as root:
        directory = session_dir(root, sid)
        if action == 'init':
            if any((directory / 'revisions').glob('*.json')):
                raise ValueError('Session exists; use show or amend instead of overwriting')
            purpose = payload.get('purpose', 'live')
            state = {'schema_version': '0.2.0', 'session_id': sid, 'revision': 0, 'state': 'initial',
                     'purpose': purpose, 'created_at': now(), 'updated_at': now(),
                     'initial': {'text': nonblank(payload.get('text'), 'initial idea'), 'user_ref': nonblank(payload.get('user_ref'), 'user_ref')},
                     'rounds': [], 'amendments': [], 'cards': [], 'card_stale': True}
        else:
            state = load(root, sid)
            if action == 'show':
                return state
            if action == 'export':
                export_cards(root, state)
                return state
            if 'expected_revision' not in payload or payload['expected_revision'] != state['revision']:
                raise ValueError('Stale or missing expected_revision; read current state before changing it')
            if action == 'ask':
                if state['state'] not in ['initial', 'round1_answered', 'round2_answered']:
                    raise ValueError('Cannot ask another round while waiting or after round 3')
                questions = payload.get('questions')
                if not isinstance(questions, list) or not 1 <= len(questions) <= 2:
                    raise ValueError('Each round requires one or two questions')
                for question in questions:
                    nonblank(question, 'question')
                number = len(state['rounds']) + 1
                based_on = 'initial' if number == 1 else f'answer{number - 1}'
                if payload.get('based_on') != based_on:
                    raise ValueError('Question must cite the latest actual answer, or initial idea for round 1')
                state['rounds'].append({'number': number, 'context': nonblank(payload.get('context'), 'context'),
                                        'questions': questions, 'based_on': based_on, 'asked_at': now(), 'answer': None})
                state['state'] = f'round{number}_wait'
            elif action == 'answer':
                if not state['state'].endswith('_wait'):
                    raise ValueError('No pending question')
                text = nonblank(payload.get('text'), 'actual user answer')
                ref = nonblank(payload.get('user_ref'), 'actual user message reference')
                if ref in {source['user_ref'] for source in user_sources(state).values()}:
                    raise ValueError('User message reference already recorded; duplicate reply rejected')
                item = state['rounds'][-1]
                item['answer'] = {'text': text, 'user_ref': ref}
                state['state'] = 'ready' if item['number'] == 3 else f'round{item["number"]}_answered'
            elif action == 'amend':
                if state['state'] != 'ready':
                    raise ValueError('During the three rounds, include the correction in the current answer; amend is for a ready exploration')
                ref = nonblank(payload.get('user_ref'), 'user_ref')
                if ref in {source['user_ref'] for source in user_sources(state).values()}:
                    raise ValueError('Duplicate user message reference')
                state['amendments'].append({'id': f'amendment{len(state["amendments"])+1}',
                                            'text': nonblank(payload.get('text'), 'correction'), 'user_ref': ref})
                state['card_stale'] = True
            elif action == 'card':
                if state['state'] != 'ready':
                    raise ValueError('All three real rounds must finish before a card is built')
                reason = payload.get('revision_reason', '基于已记录的真实输入生成探索卡。' if state['card_stale'] else None)
                nonblank(reason, 'revision_reason for an existing current card')
                card = {'schema_version': '0.2.0', 'session_id': sid, 'purpose': state['purpose'],
                        'version': len(state['cards']) + 1, 'basis_revision': state['revision'],
                        'initial_idea': state['initial']['text'], 'dialogue': copy.deepcopy(state['rounds']),
                        'amendments': copy.deepcopy(state['amendments']), 'entries': payload.get('entries'),
                        'revision_reason': reason, 'created_at': now()}
                check_schema('research-card.schema.json', card)
                sources = user_sources(state)
                for entry in card['entries']:
                    if entry['origin'] == 'user_explicit' and not entry['source_quotes']:
                        raise ValueError('Explicit user preferences need an actual quoted user source')
                    if entry['category'] == 'unknown' and entry['origin'] != 'unresolved':
                        raise ValueError('Unknown conditions must stay unresolved')
                    if entry['category'] == 'suggestion' and entry['origin'] != 'agent_proposal':
                        raise ValueError('Suggestions must be marked Agent proposals')
                    for citation in entry['source_quotes']:
                        if citation['source_ref'] not in sources or citation['quote'] not in sources[citation['source_ref']]['text']:
                            raise ValueError('Citation must quote an actual recorded user utterance exactly')
                state['cards'].append(card)
                state['card_stale'] = False
            else:
                raise ValueError(f'Unknown action: {action}')
        state['revision'] += 1
        state['updated_at'] = now()
        check_schema('research-session.schema.json', state)
        validate_state(state)
        revision = directory / 'revisions' / f'{state["revision"]:06d}.json'
        if revision.exists():
            raise ValueError('Revision collision; refusing to overwrite')
        write_json(revision, state)
        export_cards(root, state)
        return state

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--session', required=True)
    parser.add_argument('action', choices=['init', 'ask', 'answer', 'card', 'amend', 'show', 'export'])
    parser.add_argument('--input', type=Path, help='UTF-8 JSON payload, never shell-interpolated user prose')
    args = parser.parse_args()
    try:
        state = execute(args.root, args.session, args.action, read_json(args.input) if args.input else {})
        import json
        print(json.dumps(state, ensure_ascii=False, indent=2))
    except (ValueError, OSError, RuntimeError, ValidationError) as exc:
        parser.exit(1, str(exc) + '\n')

if __name__ == '__main__':
    main()
