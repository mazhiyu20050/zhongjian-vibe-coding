"""Display-only excerpts. Source text and validated offsets remain unchanged."""
from pathlib import Path
import sys
import re
import threading

_local = threading.local()
sys.path.insert(0, str(Path(__file__).resolve().parent / '.local' / 'vendor'))
from opencc import OpenCC

def simplified(text):
    if not hasattr(_local, 'converter'):
        _local.converter = OpenCC('t2s')
    return _local.converter.convert(text or '')


def concise_commentary(text):
    """Remove introductory filler from AI prose, never from source quotations."""
    text = text.strip()
    prefix = r'^(?:你可以这样理解|可以这样理解|我的判断是|我的建议是|简单来说|总的来说|换句话说|我认为|依我看)[：:，,、\s]*'
    while True:
        trimmed = re.sub(prefix, '', text).strip()
        if trimmed == text:
            return text
        text = trimmed

def brief_explanation(text):
    text = concise_commentary(simplified(text))
    text = re.sub(r'^(?:系统解读|简短解读|解释|解读)[：:]\s*', '', text)
    # Keep the clarifying second sentence, rather than cutting away its context.
    return re.sub(r'\s*\n+\s*', ' ', text).strip()


def valid_emphasis(text, fragments):
    if not isinstance(fragments, list):
        return []
    selected = []
    for fragment in fragments:
        if (isinstance(fragment,str) and 2 <= len(fragment) <= 20
                and fragment in text and fragment not in selected):
            selected.append(fragment)
        if len(selected) == 2:
            break
    return selected


def choose_emphasis(text, fragments):
    selected = valid_emphasis(text, fragments)
    if selected:
        return selected
    # A missing decorative field must not suppress the requested visual hierarchy.
    clauses = [s.strip() for s in re.split(r'[，。！？；：\n]', text)]
    candidates = [s for s in clauses if 4 <= len(s) <= 18]
    def score(s):
        return (3 * bool(re.search(r'不等于|不是|不算|不必|不赞成|才是',s))
                + 2 * bool(re.search(r'关键|责任|尽责|应该|先做|判断',s)))
    ranked = sorted(candidates,key=score,reverse=True)
    return ranked[:1]

def brief_reply(text, awaiting_answer=False):
    text = concise_commentary(simplified(text))
    # Preserve quoted example messages as complete units when counting sentences.
    symbols = {'。':'\ue010','！':'\ue011','？':'\ue012','!':'\ue013','?':'\ue014'}
    protected = re.sub(r'“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』|"[^"\n]*"',
                       lambda m: ''.join(symbols.get(c,c) for c in m.group()), text)
    parts = [p.strip() for p in re.split(r'(?<=[。！？!?])\s*|\n+', protected) if p.strip()]
    if awaiting_answer:
        question = next((p for p in reversed(parts) if p.endswith(('？','?'))),None)
        if question:
            parts=[question]
    elif len(parts) > 2:
        # Keep the key point and the final concrete action (or the one follow-up).
        question = next((p for p in reversed(parts) if p.endswith(('？', '?'))), None)
        parts = [parts[0], question if awaiting_answer and question else parts[-1]]
        parts = list(dict.fromkeys(parts))
    result = ''.join(parts)
    for original, marker in symbols.items():
        result = result.replace(marker, original)
    return result

def display_card(card):
    text = card.get('paragraph') or card.get('text', '')
    quote = card.get('quote', '')
    a, b = card.get('highlight_start'), card.get('highlight_end')
    valid = isinstance(a, int) and isinstance(b, int) and 0 <= a < b <= len(text) and text[a:b] == quote
    if valid:
        # The collapsed card is a short doorway, not a full paragraph.
        b = min(b, a + 64)
        quote = text[a:b]
        prefix = ''
        closing = re.match(r'[」』”’）】]{1,4}', text[b:])
        suffix = '…' if b < card['highlight_end'] else (closing.group() if closing else '')
        prefix, quote, suffix = map(simplified, (prefix, quote, suffix))
        excerpt = prefix + quote + suffix
        start, end = len(prefix), len(prefix) + len(quote)
    else:
        excerpt = simplified(text[:64]) + ('…' if len(text) > 64 else '')
        start = end = 0
    is_translation = card.get('language') == 'en' and isinstance(card.get('translation'),str) and bool(card['translation'].strip())
    if is_translation:
        excerpt = simplified(card['translation'].strip())
        start,end = 0,len(excerpt)
    explanation = brief_explanation(card.get('explanation', ''))
    title = card.get('viewpoint_title')
    if not isinstance(title,str) or not 2 <= len(title.strip()) <= 20:
        emphasized = choose_emphasis(explanation, card.get('emphasis',[]))
        title = emphasized[0] if emphasized else '观点与建议'
    return {'person': simplified(card.get('person', '')),
            'work': simplified(card.get('work', '')), 'volume': simplified(card.get('volume', '')),
            'section': simplified(card.get('section', '')), 'entry': card.get('entry'),
            'excerpt': excerpt, 'highlight_start': start, 'highlight_end': end, 'is_translation':is_translation,
            'explanation': explanation,
            'viewpoint_title':simplified(title.strip()),
            'advice_tendency':card.get('advice_tendency'),
            'tendency_reason':simplified(card.get('tendency_reason') or ''),
            'tendency_applicable':bool(card.get('tendency_applicable')),
            'emphasis':choose_emphasis(explanation,[simplified(s) for s in card.get('emphasis',[]) if isinstance(s,str)]
                                     if isinstance(card.get('emphasis'),list) else [])}

def with_display(value):
    if not isinstance(value, dict) or not isinstance(value.get('result'), dict):
        return value
    result = value['result']
    return {**value, 'result': {**result,
        'display_reply': (simplified(result.get('synthesis', '')) if result.get('pending_confirmation') or
                          (result.get('agent_person') and not result.get('clarification', {}).get('awaiting_answer')) else
                          brief_reply(result.get('synthesis', ''), result.get('clarification', {}).get('awaiting_answer', False))),
        'cards': [{**card, 'display': display_card(card)} for card in result.get('cards', [])]}}
