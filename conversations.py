"""User-requested local conversation snapshots, separate from diagnostic logs."""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time


class ConversationStore:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,title TEXT NOT NULL,updated_at REAL NOT NULL,session_id TEXT);
                CREATE TABLE IF NOT EXISTS conversation_turns (
                id INTEGER PRIMARY KEY,conversation_id TEXT NOT NULL,question TEXT NOT NULL,
                result TEXT NOT NULL,created_at REAL NOT NULL);''')
            if 'agent_person' not in {r['name'] for r in db.execute('PRAGMA table_info(conversations)')}:
                db.execute('ALTER TABLE conversations ADD COLUMN agent_person TEXT')
            db.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at REAL NOT NULL)')
            for column,definition in [('source_path','TEXT'),('pinned','INTEGER NOT NULL DEFAULT 0'),('section',"TEXT NOT NULL DEFAULT ''"),('status',"TEXT NOT NULL DEFAULT 'active'")]:
                if column not in {r['name'] for r in db.execute('PRAGMA table_info(projects)')}:
                    db.execute('ALTER TABLE projects ADD COLUMN '+column+' '+definition)
            if 'project_id' not in {r['name'] for r in db.execute('PRAGMA table_info(conversations)')}:
                db.execute('ALTER TABLE conversations ADD COLUMN project_id TEXT')
            if 'pinned' not in {r['name'] for r in db.execute('PRAGMA table_info(conversations)')}:
                db.execute('ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0')

            for column,definition in [('section',"TEXT NOT NULL DEFAULT ''"),('unread','INTEGER NOT NULL DEFAULT 0'),('archived','INTEGER NOT NULL DEFAULT 0')]:
                if column not in {r['name'] for r in db.execute('PRAGMA table_info(conversations)')}:
                    db.execute('ALTER TABLE conversations ADD COLUMN '+column+' '+definition)

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=5);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def list(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,title,updated_at,project_id,agent_person,pinned,section,unread,archived FROM conversations ORDER BY pinned DESC,updated_at DESC')]

    def pin(self,cid,pinned):
        if type(pinned) is not bool:raise ValueError('invalid_pin')
        with self.connect() as db:
            if not db.execute('UPDATE conversations SET pinned=? WHERE id=?',(int(pinned),cid)).rowcount:raise ValueError('conversation_not_found')

    def manage(self,cid,field,value):
        if field in ('title','section'):
            if not isinstance(value,str) or len(value.strip())>80 or (field=='title' and not value.strip()):
                raise ValueError('invalid_history_text')
            value=value.strip()
        elif field in ('unread','archived'):
            if type(value) is not bool:raise ValueError('invalid_history_flag')
            value=int(value)
        else:raise ValueError('invalid_history_field')
        if not isinstance(cid,str):raise ValueError('conversation_not_found')
        with self.connect() as db:
            if not db.execute(f'UPDATE conversations SET {field}=? WHERE id=?',(value,cid)).rowcount:
                raise ValueError('conversation_not_found')

    def branch(self,cid):
        if not isinstance(cid,str):raise ValueError('conversation_not_found')
        new_id=secrets.token_hex(12)
        with self.connect() as db:
            row=db.execute('SELECT * FROM conversations WHERE id=?',(cid,)).fetchone()
            if not row:raise ValueError('conversation_not_found')
            db.execute('INSERT INTO conversations (id,title,updated_at,agent_person,project_id,section) VALUES (?,?,?,?,?,?)',
                       (new_id,row['title'][:75]+'（分支）',time.time(),row['agent_person'],row['project_id'],row['section']))
            db.execute('INSERT INTO conversation_turns (conversation_id,question,result,created_at) SELECT ?,question,result,created_at FROM conversation_turns WHERE conversation_id=? ORDER BY id',(new_id,cid))
        return new_id

    def rename_project(self,pid,name):
        self.validate_project(pid)
        if pid is None or not isinstance(name,str) or not 1<=len(name.strip())<=40:raise ValueError('invalid_project_name')
        with self.connect() as db:db.execute('UPDATE projects SET name=? WHERE id=?',(name.strip(),pid))

    def export_project(self,pid):
        """Make a readable snapshot for Explorer, leaving SQLite as source of truth."""
        self.validate_project(pid)
        if pid is None:raise ValueError('invalid_project')
        root=(self.path.parent/'projects').resolve();folder=(root/pid).resolve()
        if folder.parent!=root:raise ValueError('invalid_project')
        folder.mkdir(parents=True,exist_ok=True)
        project=next(p for p in self.projects() if p['id']==pid)
        with self.connect() as db:ids=[r['id'] for r in db.execute('SELECT id FROM conversations WHERE project_id=?',(pid,))]
        snapshot={**project,'conversations':[self.get(cid) for cid in ids]}
        (folder/'project.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
        return folder

    def projects(self):
        with self.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM projects ORDER BY pinned DESC,created_at')]

    def create_project(self,name,source_path=None):
        if not isinstance(name,str) or not 1<=len(name.strip())<=40:raise ValueError('invalid_project_name')
        name=name.strip();pid=secrets.token_hex(12)
        if source_path is not None:
            source_path=str(Path(source_path).resolve())
            if not Path(source_path).is_dir():raise ValueError('source_folder_missing')
        with self.connect() as db:
            db.execute('INSERT INTO projects (id,name,created_at,source_path) VALUES (?,?,?,?)',(pid,name,time.time(),source_path))
        return {'id':pid,'name':name}

    def manage_project(self,pid,action,value=None):
        if not isinstance(pid,str):raise ValueError('invalid_project')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute("SELECT 1 FROM projects WHERE id=? AND status='active'",(pid,)).fetchone():
                raise ValueError('project_not_active')
            if action=='pinned' and type(value) is bool:
                db.execute('UPDATE projects SET pinned=? WHERE id=?',(int(value),pid))
            elif action=='section' and isinstance(value,str) and len(value.strip())<=80:
                db.execute('UPDATE projects SET section=? WHERE id=?',(value.strip(),pid))
            elif action=='archive_chats':
                return db.execute('UPDATE conversations SET archived=1 WHERE project_id=? AND archived=0',(pid,)).rowcount
            elif action=='remove':
                db.execute('UPDATE conversations SET project_id=NULL,archived=0 WHERE project_id=?',(pid,))
                db.execute("UPDATE projects SET status='deleted',pinned=0 WHERE id=?",(pid,))
            else:raise ValueError('invalid_project_action')
        return 0

    def project_status(self,pid,status):
        self.validate_project(pid)
        if pid is None or status not in ('active','archived','deleted'):raise ValueError('invalid_project_status')
        with self.connect() as db:db.execute('UPDATE projects SET status=? WHERE id=?',(status,pid))

    def project_folder(self,pid):
        self.validate_project(pid)
        project=next((p for p in self.projects() if p['id']==pid),None)
        if not project:raise ValueError('project_not_found')
        if project.get('source_path'):
            folder=Path(project['source_path'])
            if not folder.is_dir():raise ValueError('source_folder_missing')
            return folder
        return self.export_project(pid)

    def validate_project(self,pid):
        if pid is None:return
        if not isinstance(pid,str):raise ValueError('invalid_project')
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM projects WHERE id=?',(pid,)).fetchone():raise ValueError('project_not_found')

    def move(self,cid,pid):
        self.validate_project(pid)
        with self.connect() as db:
            if not db.execute('UPDATE conversations SET project_id=? WHERE id=?',(pid,cid)).rowcount:raise ValueError('conversation_not_found')

    def get(self,cid):
        if not isinstance(cid,str) or not re.fullmatch(r'[a-f0-9]{24}',cid):return None
        with self.connect() as db:
            row=db.execute('SELECT * FROM conversations WHERE id=?',(cid,)).fetchone()
            if row is None:return None
            turns=[{'question':r['question'],'result':json.loads(r['result'])} for r in db.execute(
                'SELECT question,result FROM conversation_turns WHERE conversation_id=? ORDER BY id',(cid,))]
            return {**dict(row),'turns':turns}

    def append(self,cid,question,result,session_id=None,agent_person=None,project_id=None):
        self.validate_project(project_id)
        encoded=json.dumps(result,ensure_ascii=False)
        if len(encoded.encode())>2000000:raise ValueError('history_turn_too_large')
        now=time.time()
        with self.connect() as db:
            if cid:
                if not db.execute('SELECT 1 FROM conversations WHERE id=?',(cid,)).fetchone():raise ValueError('conversation_not_found')
                db.execute('UPDATE conversations SET updated_at=?,session_id=? WHERE id=?',(now,session_id,cid))
            else:
                cid=secrets.token_hex(12)
                title=result.get('question_title') or question
                title=re.sub(r'[\r\n\t]+',' ',str(title)).strip()[:24]
                db.execute('INSERT INTO conversations (id,title,updated_at,session_id,agent_person,project_id) VALUES (?,?,?,?,?,?)',(cid,title,now,session_id,agent_person,project_id))
            db.execute('INSERT INTO conversation_turns (conversation_id,question,result,created_at) VALUES (?,?,?,?)',
                       (cid,question,encoded,now))
        return cid
