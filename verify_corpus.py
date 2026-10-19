"""Offline audit: source snapshots, Skill digests and actual quote anchors."""
import argparse
import hashlib
import json
from pathlib import Path
from corpus import ROOT, load_library
from query import make_passages
from thinkers import build_profiles, SPECS
from person_skills import load_skills


def audit():
    rows=load_library();passages=make_passages(rows);profiles=build_profiles(passages);skills=load_skills()
    source_hashes={};people={}
    for row in rows:
        path=Path(row['source_file'])
        resolved=path if path.is_absolute() else ROOT/path
        key=str(resolved)
        if key not in source_hashes:
            source_hashes[key]=hashlib.sha256(resolved.read_bytes()).hexdigest()
        if source_hashes[key]!=row['source_sha256']:raise ValueError('source_hash_mismatch:'+row['id'])
        info=people.setdefault(row['person'],{'units':0,'source_units':0,'concepts':0,'language':set()})
        info['units']+=1;info['source_units']+=row['kind']=='source';info['language'].add(row.get('language','zh'))
    lookup={p['id']:p for p in passages}
    for person,info in people.items():
        if person not in skills or person not in profiles:raise ValueError('person_not_fully_installed:'+person)
        concepts=profiles[person]['concepts'];info['concepts']=len(concepts)
        info['language']=sorted(info['language'])
        if len(concepts)!=len(SPECS[person]):raise ValueError('missing_literal_concept_anchor:'+person)
        for c in concepts:
            a=c['primary_anchor'];p=lookup[a['passage_id']]
            if p['person']!=person or p['text'][a['start']:a['end']]!=a['quote']:raise ValueError('anchor_mismatch')
    return {'people':people,'total_units':len(rows),'total_passages':len(passages),
            'unique_source_snapshots':len(source_hashes),'source_hashes_verified':True,
            'skill_hashes_verified':True,'all_declared_anchors_verified':True,
            'note':'Checks source fidelity and structural availability, not interpretation truth or retrieval relevance.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    result=audit();text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding='utf-8')
    print(text)
