"""Local interests and transparent integer quotas. No query text is persisted."""
from collections import Counter
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

CATALOG = Path(__file__).resolve().parent / 'data' / 'people' / 'catalog.json'
CYCLE = ((2,1,1), (1,2,1), (2,2,0), (1,2,1), (2,1,1))
GROUPS = ('interest', 'recommended', 'similar')
LABELS = {'interest':'你感兴趣', 'recommended':'为你推荐', 'similar':'相似人物', 'explicit':'你指定'}


def people_catalog():
    return json.loads(CATALOG.read_text(encoding='utf-8'))


def make_plan(selected, available, index=0, people=None, explicit=()):
    people = people or people_catalog()
    available = set(available)
    if explicit:
        groups = {p:'explicit' for p in explicit if p in available}
        return {'groups':groups, 'quotas':{'explicit':min(4,len(groups))}, 'mode':'explicit', 'index':index}
    interested = set(selected) & available
    if not interested:
        return {'groups':{p:'recommended' for p in sorted(available)},
                'quotas':{'interest':0,'recommended':min(4,len(available)),'similar':0}, 'mode':'system', 'index':index}
    tags = {p['person']:set(p.get('tags',[])) for p in people}
    def similarity(person):
        own = tags.get(person,set())
        scores = [len(own & tags.get(p,set())) / max(1,len(own | tags.get(p,set()))) for p in interested]
        return max(scores, default=0)
    others = sorted(available-interested, key=lambda p:(-similarity(p),p))
    # Leave room for independent recommendations: similarity is an explained tag overlap, not a fact about personality.
    similar = set(p for p in others[:min(4,max(0,len(others)-1))] if similarity(p)>0)
    groups = {p:('interest' if p in interested else 'similar' if p in similar else 'recommended') for p in sorted(available)}
    capacity = Counter(groups.values())
    quota = dict(zip(GROUPS,CYCLE[index%5]))
    for g in GROUPS:
        quota[g] = min(quota[g], capacity[g])
    while sum(quota.values()) < min(4,len(available)):
        for g in ('recommended','interest','similar'):
            if quota[g] < capacity[g]:
                quota[g] += 1
                break
        else:
            break
    return {'groups':groups, 'quotas':quota, 'mode':'personalized', 'index':index,
            'similarity':{p:round(similarity(p),3) for p in similar},
            'explanation':'相似性依据经整理的思想主题标签；同一人物只属于一组。四卡按五轮累计8/8/4分配，人数或证据不足时据实补位。'}


class RecommendationStore:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS person_preferences (id INTEGER PRIMARY KEY CHECK(id=1), people TEXT NOT NULL, round_index INTEGER NOT NULL DEFAULT 0, counts TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO person_preferences VALUES (1,?,0,?)', ('[]','{}'))

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=5)
        try:
            with db:yield db
        finally:db.close()

    def read(self):
        with self.connect() as db:
            row=db.execute('SELECT people,round_index,counts FROM person_preferences WHERE id=1').fetchone()
        return {'selected':json.loads(row[0]),'round_index':row[1],'counts':json.loads(row[2]),'weights':{'interest':40,'recommended':40,'similar':20}}

    def save(self,people):
        valid={p['person'] for p in people_catalog()}
        if (not isinstance(people,list) or len(people)>20 or any(not isinstance(p,str) or p not in valid for p in people) or len(set(people))!=len(people)):
            raise ValueError('invalid_preferences')
        with self.connect() as db:
            db.execute('UPDATE person_preferences SET people=?,round_index=0,counts=? WHERE id=1',(json.dumps(people,ensure_ascii=False),'{}'))
        return self.read()

    def plan(self,available,explicit=()):
        state=self.read()
        plan=make_plan(state['selected'],available,state['round_index'],explicit=explicit)
        plan['selection_key']=json.dumps(state['selected'],ensure_ascii=False)
        return plan

    def commit(self,plan,cards):
        actual=Counter(plan['groups'].get(c['person'],'recommended') for c in cards)
        result={'mode':plan['mode'],'target':plan['quotas'],'actual':dict(actual),'target_weights':{'interest':40,'recommended':40,'similar':20},'balanced':dict(actual)=={g:n for g,n in plan['quotas'].items() if n}}
        if plan['mode']=='personalized' and cards:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row=db.execute('SELECT round_index,counts,people FROM person_preferences WHERE id=1').fetchone()
                # A preference edit or another completed query invalidates this plan; don't charge a stale cycle.
                if row[0]==plan['index'] and row[2]==plan.get('selection_key'):
                    counts=Counter(json.loads(row[1]));counts.update(actual)
                    db.execute('UPDATE person_preferences SET round_index=round_index+1,counts=? WHERE id=1',(json.dumps(dict(counts)),))
        return result
