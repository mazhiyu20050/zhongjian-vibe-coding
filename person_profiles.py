"""Prepare public profile assets separately from review and Skill activation."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import quote, urlencode, urlsplit

from people_discovery import public_json
from prepare_portraits import prepare as prepare_portrait
from presentation import simplified


def clean(value, limit):
    return re.sub(r'\s+', ' ', value).strip()[:limit] if isinstance(value, str) else ''


def stage_profile(person, storage):
    qid = person.get('wikidata_id')
    if person.get('verified_human') is not True or not isinstance(qid, str) or not re.fullmatch(r'Q[1-9][0-9]{0,12}', qid):
        return {}
    directory = Path(storage) / 'person-profiles' / qid
    directory.mkdir(parents=True, exist_ok=True)
    source = 'https://www.wikidata.org/wiki/' + qid
    biography = clean(person.get('description'), 180)
    title = clean(person.get('zh_article'), 200)
    if title:
        try:
            url = 'https://zh.wikipedia.org/w/api.php?' + urlencode({
                'action': 'query', 'prop': 'extracts|pageprops', 'ppprop': 'wikibase_item',
                'titles': title, 'exintro': 1, 'explaintext': 1, 'exchars': 280, 'format': 'json',
            })
            for page in public_json(url, maximum=200000).get('query', {}).get('pages', {}).values():
                text = clean(page.get('extract'), 280)
                if page.get('pageprops', {}).get('wikibase_item') == qid and text:
                    biography = simplified(text)
                    source = 'https://zh.wikipedia.org/wiki/' + quote(page.get('title', title).replace(' ', '_'), safe='')
                    break
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    portrait = None
    if clean(person.get('portrait_file'), 250):
        try:
            _, portrait = prepare_portrait(person, directory)
        except (OSError, ValueError, TypeError, KeyError, StopIteration, AttributeError):
            pass
    data = {'wikidata_id': qid, 'biography': biography, 'biography_url': source,
            'lifespan': clean(person.get('lifespan'), 32), 'portrait': portrait}
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(data, handle, ensure_ascii=False)
        except Exception:
            handle.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(directory / 'profile.json')
    finally:
        temporary.unlink(missing_ok=True)
    return {'biography': biography, 'portrait_ready': bool(portrait)}


def read_profile(storage, qid):
    if not isinstance(qid, str) or not re.fullmatch(r'Q[1-9][0-9]{0,12}', qid):
        return {}
    try:
        path = Path(storage) / 'person-profiles' / qid / 'profile.json'
        if path.stat().st_size > 16000:
            return {}
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('wikidata_id') != qid:
            return {}
        source = urlsplit(clean(data.get('biography_url'), 1000))
        portrait = data.get('portrait')
        if not isinstance(portrait, dict) or not re.fullmatch(r'/portraits/'+qid+r'\.(?:jpg|png|webp)', portrait.get('url','')):
            portrait = None
        else:
            portrait = {'url': '/person-portraits/' + portrait['url'].rsplit('/', 1)[-1],
                        'sha256': clean(portrait.get('sha256'), 64),
                        'source': clean(portrait.get('source'), 500),
                        'artist': clean(portrait.get('artist'), 180),
                        'license': clean(portrait.get('license'), 80)}
        return {'biography': clean(data.get('biography'), 280), 'lifespan': clean(data.get('lifespan'), 32),
                'biography_url': source.geturl() if source.scheme == 'https' and source.netloc in
                {'www.wikidata.org', 'zh.wikipedia.org'} else '', 'portrait': portrait}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def portrait_bytes(storage, name):
    qid = name.split('.',1)[0]
    profile = read_profile(storage, qid)
    metadata = profile.get('portrait')
    if not metadata or metadata['url'] != '/person-portraits/' + name:
        return None
    try:
        path = Path(storage) / 'person-profiles' / qid / name
        if path.stat().st_size > 4000000:
            return None
        raw = path.read_bytes()
        return raw if hashlib.sha256(raw).hexdigest() == metadata['sha256'] else None
    except OSError:
        return None
