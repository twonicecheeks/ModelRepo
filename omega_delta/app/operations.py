"""Local process ownership, restorable backups, and bounded background jobs."""
import fcntl
import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from .core import canonical, now


class InstanceLock:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file=self.path.open('a+')
        try: fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.file.close()
            raise ValueError('This OMEGA data folder is already open. Stop the existing server before launching another.') from None
    def close(self):
        fcntl.flock(self.file,fcntl.LOCK_UN);self.file.close()


def restore_database(source,destination):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if destination.exists(): raise ValueError('Restore requires an empty data folder; the existing database will not be overwritten.')
    if not source.is_file(): raise ValueError('Backup file not found.')
    src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
    try:
        if src.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Backup integrity check failed.')
        tables={r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'snapshots','quotes','bets','bet_events','settings','logs'} <= tables: raise ValueError('This is not an OMEGA database backup.')
        if src.execute('PRAGMA user_version').fetchone()[0]>2: raise ValueError('Backup comes from a newer OMEGA release.')
        if src.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('Backup contains broken record references.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        dst=sqlite3.connect(str(destination))
        try: src.backup(dst)
        finally: dst.close()
        os.chmod(destination,0o600)
    finally: src.close()


class Jobs:
    def __init__(self,store):
        self.store=store;self.lock=threading.Lock();self.active=set()
        with store.tx() as c:
            c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,kind TEXT,status TEXT,created_at TEXT,finished_at TEXT,payload TEXT)')
            c.execute("UPDATE jobs SET status='INTERRUPTED',finished_at=?,payload=? WHERE status='RUNNING'",(now(),canonical({'error':'Server stopped before this job completed. Retry explicitly.'})))

    def start(self,kind,action):
        with self.lock:
            if kind in self.active: raise ValueError('This operation is already running. Check Data & provenance.')
            if len(self.active)>=4: raise ValueError('Four jobs are already running. Wait for one to finish.')
            self.active.add(kind)
        jid='job_'+uuid.uuid4().hex[:20]
        with self.store.tx() as c:
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',(jid,kind,'RUNNING',now(),None,'{}'))
        def work():
            try:
                result=action(); status='COMPLETE'
                if isinstance(result,dict) and result.get('status') in {'FAILED','STOPPED'}:
                    status='FAILED'
                    result.setdefault('error','No complete capture was obtained. Inspect the watchlist or capture coverage for source errors.')
            except Exception as error:
                result={'error':f'{type(error).__name__}: {str(error)[:800]}'};status='FAILED'
            try:
                # Publish completion only after every other DB write finishes.
                # Readers may close/backup a test store as soon as it completes.
                self.store.log('JOB_'+kind,status,jid)
                with self.store.tx() as c:
                    c.execute('UPDATE jobs SET status=?,finished_at=?,payload=? WHERE id=?',(status,now(),canonical(result),jid))
            finally:
                with self.lock: self.active.discard(kind)
        threading.Thread(target=work,daemon=True).start()
        return {'job_id':jid,'status':'RUNNING'}

    def get(self,jid):
        with self.store.lock: row=self.store.db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
        if not row: raise ValueError('Job not found.')
        return dict(row,result=json.loads(row['payload']))

    def recent(self):
        with self.store.lock:
            return [dict(r) for r in self.store.db.execute('SELECT id,kind,status,created_at,finished_at FROM jobs ORDER BY rowid DESC LIMIT 12')]
