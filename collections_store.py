"""Local SQLite excerpt bookmarks. No questions, keys or model analyses stored."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

FIELDS = ('passage_id', 'highlight_start', 'highlight_end', 'quote', 'paragraph', 'unit_id',
          'person', 'work', 'volume', 'entry', 'section', 'source_url', 'speaker_note',
          'quality_warning', 'source_sha256')


class CollectionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS collections (
                collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                passage_id TEXT NOT NULL, highlight_start INTEGER NOT NULL,
                highlight_end INTEGER NOT NULL, snapshot TEXT NOT NULL,
                created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(passage_id, highlight_start, highlight_end))''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def item(row):
        return {**json.loads(row['snapshot']), 'collection_id': row['collection_id'],
                'created_at': row['created_at']}

    def add(self, snapshot):
        safe = {k: snapshot[k] for k in FIELDS if k in snapshot}
        args = (safe['passage_id'], safe['highlight_start'], safe['highlight_end'])
        with self.connection() as db:
            # Serialize read-modify-write so duplicate concurrent requests are idempotent.
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM collections WHERE passage_id=? AND highlight_start=? AND highlight_end=?', args).fetchone()
            if old and old['active']:
                return {'created': False, 'item': self.item(old)}
            count = db.execute('SELECT COUNT(*) FROM collections WHERE active=1').fetchone()[0]
            if count >= 500:
                raise OverflowError('collection_limit')
            now = datetime.now(timezone.utc).isoformat()
            payload = json.dumps(safe, ensure_ascii=False)
            if old:
                db.execute('UPDATE collections SET active=1, snapshot=?, created_at=? WHERE collection_id=?',
                           (payload, now, old['collection_id']))
            else:
                db.execute('INSERT INTO collections(passage_id, highlight_start, highlight_end, snapshot, created_at) VALUES(?,?,?,?,?)',
                           (*args, payload, now))
            row = db.execute('SELECT * FROM collections WHERE passage_id=? AND highlight_start=? AND highlight_end=?', args).fetchone()
            return {'created': True, 'item': self.item(row)}

    def list(self):
        with self.connection() as db:
            return [self.item(row) for row in db.execute('SELECT * FROM collections WHERE active=1 ORDER BY created_at DESC, collection_id DESC')]

    def cancel(self, collection_id):
        # Soft cancellation preserves a reversible record; re-saving restores it.
        with self.connection() as db:
            result = db.execute('UPDATE collections SET active=0 WHERE collection_id=? AND active=1', (collection_id,))
            return result.rowcount > 0
