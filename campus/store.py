import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import ROOT


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path=None):
        self.path = path or ROOT / 'private/campus.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL,
                body TEXT NOT NULL, searchable TEXT NOT NULL, fetched_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS source_kind ON documents(source, kind);
            CREATE TABLE IF NOT EXISTS sync_state (source TEXT PRIMARY KEY, body TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, documents, replace=None):
        with self.connect() as db:
            if replace:
                db.execute('DELETE FROM documents WHERE source=? AND kind=?', replace)
            for doc in documents:
                text = '\n'.join(str(doc.get(key) or '') for key in ('title', 'text', 'course', 'publisher')).casefold()
                text += '\n' + '\n'.join(str(c.get('text','')) for c in doc.get('comments',[])).casefold()
                db.execute('INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?)',
                           (doc['id'], doc['source'], doc['kind'], json.dumps(doc, ensure_ascii=False), text, doc['fetchedAt']))

    def get(self, identity):
        with self.connect() as db:
            row = db.execute('SELECT body FROM documents WHERE id=?', (identity,)).fetchone()
        return json.loads(row[0]) if row else None

    def search(self, query, sources, limit, offset=0):
        if not sources:
            return [], 0
        where = 'source IN (' + ','.join('?' for _ in sources) + ')'
        params = list(sources)
        for term in query.casefold().split():
            where += ' AND instr(searchable,?)>0'
            params.append(term)
        with self.connect() as db:
            count = db.execute(f'SELECT count(*) FROM documents WHERE {where}', params).fetchone()[0]
            rows = db.execute(f'SELECT body FROM documents WHERE {where} ORDER BY fetched_at DESC,id LIMIT ? OFFSET ?', params + [limit, offset]).fetchall()
        return [json.loads(row[0]) for row in rows], count

    def state(self, source, value=None):
        with self.connect() as db:
            if value is not None:
                db.execute('INSERT OR REPLACE INTO sync_state VALUES (?,?)', (source, json.dumps(value)))
                return value
            row = db.execute('SELECT body FROM sync_state WHERE source=?', (source,)).fetchone()
        return json.loads(row[0]) if row else None
