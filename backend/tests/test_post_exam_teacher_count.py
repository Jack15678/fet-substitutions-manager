from io import BytesIO
import os
import sys
import unittest

from openpyxl import Workbook

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rescheduling_service import parse_post_exam_teacher_workbook


class PostExamTeacherCountTests(unittest.TestCase):
    def test_accepts_variable_teacher_count(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["教師", "1 教師甲", "2 教師乙"])
        for time in ("8:25-9:15", "9:15-10:05", "10:25-11:15", "11:15-12:05", "12:25-13:00"):
            sheet.append([time, "", ""])
        content = BytesIO()
        workbook.save(content)

        slots, names = parse_post_exam_teacher_workbook(content.getvalue())

        self.assertEqual(set(names), {"教師甲", "教師乙"})
        self.assertEqual(slots, [])


if __name__ == "__main__":
    unittest.main()
