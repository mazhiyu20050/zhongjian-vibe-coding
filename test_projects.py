import tempfile
from pathlib import Path
import unittest
from conversations import ConversationStore


class ProjectTests(unittest.TestCase):
    def test_project_archive_trash_restore_and_folder_import(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ConversationStore(Path(folder)/'history.sqlite3');source=Path(folder)/'source';source.mkdir()
            p=store.create_project('Imported',str(source));cid=store.append(None,'Keep',{},project_id=p['id'])
            self.assertEqual(store.project_folder(p['id']),source.resolve())
            for status in ('archived','deleted','active'):
                store.project_status(p['id'],status)
                self.assertEqual(next(x for x in store.projects() if x['id']==p['id'])['status'],status)
            self.assertEqual(store.get(cid)['project_id'],p['id'])

    def test_rename_pin_person_and_explorer_snapshot(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            store=ConversationStore(Path(folder)/'history.sqlite3');p=store.create_project('旧名')
            a=store.append(None,'第一条',{},agent_person='王阳明',project_id=p['id'])
            b=store.append(None,'第二条',{})
            store.pin(a,True);store.rename_project(p['id'],'新名')
            rows=store.list();self.assertEqual(rows[0]['id'],a);self.assertEqual(rows[0]['agent_person'],'王阳明')
            dest=store.export_project(p['id']);snapshot=json.loads((dest/'project.json').read_text(encoding='utf-8'))
            self.assertEqual(snapshot['name'],'新名');self.assertEqual(snapshot['conversations'][0]['id'],a)
            store.pin(a,False);self.assertEqual(store.list()[0]['id'],b)
            with self.assertRaises(ValueError):store.export_project('../outside')
            with self.assertRaises(ValueError):store.rename_project(None,'bad')

    def test_create_group_move_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'history.sqlite3';store=ConversationStore(path)
            p=store.create_project('学编程')
            cid=store.append(None,'问题',{'question_title':'学习'},project_id=p['id'])
            self.assertEqual(store.get(cid)['project_id'],p['id'])
            self.assertEqual(store.list()[0]['project_id'],p['id'])
            self.assertEqual(ConversationStore(path).projects()[0]['name'],'学编程')
            store.move(cid,None)
            self.assertIsNone(store.get(cid)['project_id'])
            store.move(cid,p['id'])
            store.append(cid,'继续',{},project_id=None)
            self.assertEqual(store.get(cid)['project_id'],p['id'])

    def test_reject_bad_project_without_losing_conversation(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ConversationStore(Path(folder)/'h.sqlite3')
            cid=store.append(None,'问题',{})
            for name in ('',' '*4,'x'*41,None):
                with self.assertRaises(ValueError):store.create_project(name)
            with self.assertRaises(ValueError):store.move(cid,'missing')
            self.assertIsNone(store.get(cid)['project_id'])


if __name__=='__main__':unittest.main()
