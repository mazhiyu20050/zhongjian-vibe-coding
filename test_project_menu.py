from test_projects import ProjectTests
from conversations import ConversationStore
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

class ProjectMenuTests(unittest.TestCase):
    def test_project_controls(self):
        with TemporaryDirectory() as tmp:
            s=ConversationStore(Path(tmp)/'db')
            a=s.create_project('甲')['id']
            b=s.create_project('乙',tmp)['id']
            c=s.append(None,'问题',{},project_id=b)
            s.manage_project(b,'pinned',True)
            s.manage_project(b,'section','资料')
            self.assertEqual((s.projects()[0]['id'],s.projects()[0]['section']),(b,'资料'))
            self.assertEqual(s.manage_project(b,'archive_chats'),1)
            self.assertTrue(s.get(c)['archived'])
            self.assertEqual(s.projects()[0]['status'],'active')
            s.manage_project(b,'remove')
            self.assertIsNone(s.get(c)['project_id'])
            self.assertFalse(s.get(c)['archived'])
            self.assertTrue(Path(tmp).is_dir())
            self.assertEqual(next(p for p in s.projects() if p['id']==b)['status'],'deleted')
