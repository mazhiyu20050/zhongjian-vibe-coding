"""Project-scoped, allowlisted persona Skills; summaries route, bodies explain."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'skills' / 'people'


def load_skills():
    result = {}
    for entry in json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8')):
        path = (ROOT / entry['path']).resolve()
        if not path.is_relative_to(ROOT.resolve()) or path.name != 'SKILL.md':
            raise ValueError('invalid_skill_path')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != entry['sha256'] or entry['person'] in result:
            raise ValueError('invalid_skill_manifest')
        result[entry['person']] = {**entry, 'instructions': raw.decode('utf-8')}
    return result


def catalog(skills, people):
    return [{k: s[k] for k in ('person', 'id', 'version', 'summary')}
            for person, s in skills.items() if person in people]


def identity(skill):
    return {k: skill[k] for k in ('person', 'id', 'version', 'sha256')}
