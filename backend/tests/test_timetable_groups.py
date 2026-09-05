import json
import os
import sys
import unittest
from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault('SECRET_KEY', 'timetable-group-tests-only-secret')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth_utils import get_current_user
from database import _ensure_timetable_version_columns, create_data_tables
from dependencies import get_db
from models import Base, AbsenceCase, Professor, TimetableVersion
from rescheduling_service import get_schedule_revision, version_for_date
from routes.rescheduling import router


class TimetableGroupTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = SimpleNamespace(username='group-test', role='admin', permissions=None)
        self.version = TimetableVersion(
            effective_from=date(2026, 9, 1), effective_to=date(2027, 7, 10),
            class_filename='post.xlsx', teacher_filename='teachers.xlsx',
            effective_ranges_json=json.dumps([
                {'effective_from': '2026-09-01', 'effective_to': '2026-09-30'},
                {'effective_from': '2027-06-21', 'effective_to': '2027-07-10'},
            ]), active=True,
        )
        teacher = Professor(nom='Group Teacher', actiu=True)
        self.db.add_all([self.version, teacher])
        self.db.flush()
        self.db.add(AbsenceCase(professor_id=teacher.id, data=date(2026, 9, 5), periods_json='[1]'))
        self.db.commit()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def test_create_rename_move_and_ungroup_preserve_locked_timetable(self):
        original = self.client.get('/api/timetables').json()[0]
        self.assertTrue(original['locked'])
        self.assertIsNone(original['group_id'])
        revision = get_schedule_revision(self.db)
        group = self.client.post('/api/timetable-groups', json={'name': ' 2026–2027 學年 '}).json()
        self.assertEqual(group['name'], '2026–2027 學年')
        self.assertEqual(self.client.get('/api/timetable-groups').json(), [group])
        path = f'/api/timetables/{self.version.id}/group'
        self.assertEqual(self.client.put(path, json={'group_id': group['id']}).status_code, 200)
        self.assertEqual(self.client.put(f"/api/timetable-groups/{group['id']}", json={'name': '本學年'}).status_code, 200)
        self.db.expire_all()
        moved = self.client.get('/api/timetables').json()[0]
        self.assertEqual(moved.pop('group_id'), group['id'])
        original.pop('group_id')
        self.assertEqual(moved, original)
        self.assertEqual(get_schedule_revision(self.db), revision)
        self.assertEqual(version_for_date(self.db, date(2026, 9, 5)).id, self.version.id)
        self.assertIsNone(version_for_date(self.db, date(2027, 3, 1)))
        self.assertEqual(self.client.get('/api/timetable-groups').json(), [{'id': group['id'], 'name': '本學年'}])
        self.assertEqual(self.client.put(path, json={'group_id': None}).status_code, 200)
        self.db.expire_all()
        self.assertIsNone(self.client.get('/api/timetables').json()[0]['group_id'])

    def test_validation_missing_targets_and_permissions(self):
        group = self.client.post('/api/timetable-groups', json={'name': '本學年'}).json()
        for name in ('', '   ', 'x' * 81):
            self.assertEqual(self.client.post('/api/timetable-groups', json={'name': name}).status_code, 422)
        self.assertEqual(self.client.post('/api/timetable-groups', json={'name': ' 本學年 '}).status_code, 409)
        other = self.client.post('/api/timetable-groups', json={'name': '舊學年'}).json()
        self.assertEqual(self.client.put(f"/api/timetable-groups/{other['id']}", json={'name': '本學年'}).status_code, 409)
        path = f'/api/timetables/{self.version.id}/group'
        for payload, status in (({}, 422), ({'group_id': 0}, 422), ({'group_id': 9999}, 404)):
            self.assertEqual(self.client.put(path, json=payload).status_code, status)
        self.assertEqual(self.client.put('/api/timetables/9999/group', json={'group_id': group['id']}).status_code, 404)
        self.assertEqual(self.client.put('/api/timetable-groups/9999', json={'name': '名稱'}).status_code, 404)
        self.assertIsNone(self.client.get('/api/timetables').json()[0]['group_id'])
        self.user.role = 'user'
        self.user.permissions = json.dumps(['timetable.upload'])
        self.assertEqual(self.client.get('/api/timetable-groups').status_code, 200)
        self.assertEqual(self.client.post('/api/timetable-groups', json={'name': '禁止'}).status_code, 403)
        self.assertEqual(self.client.put(f"/api/timetable-groups/{group['id']}", json={'name': '禁止'}).status_code, 403)
        self.assertEqual(self.client.put(path, json={'group_id': group['id']}).status_code, 403)
        self.user.permissions = '[]'
        self.assertEqual(self.client.get('/api/timetable-groups').status_code, 403)

    def test_existing_database_migration_keeps_versions_ungrouped(self):
        legacy = create_engine('sqlite://')
        try:
            with legacy.begin() as conn:
                conn.exec_driver_sql('CREATE TABLE timetable_versions (id INTEGER PRIMARY KEY, effective_from DATE)')
                conn.exec_driver_sql("INSERT INTO timetable_versions VALUES (1, '2026-09-01')")
            create_data_tables(legacy)
            _ensure_timetable_version_columns(legacy)
            _ensure_timetable_version_columns(legacy)
            with legacy.connect() as conn:
                self.assertEqual(conn.exec_driver_sql('SELECT id, effective_from, group_id FROM timetable_versions').one(), (1, '2026-09-01', None))
                self.assertEqual(conn.exec_driver_sql('SELECT COUNT(*) FROM timetable_groups').scalar(), 0)
        finally:
            legacy.dispose()


if __name__ == '__main__':
    unittest.main()
