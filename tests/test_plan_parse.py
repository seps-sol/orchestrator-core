import unittest

from seps.plan_parse import parse_plan_directives


class PlanParseTest(unittest.TestCase):
    def test_last_key_wins(self) -> None:
        plan = "Hello\nNEXT_REPO: a\nNEXT_REPO: NONE\n"
        d = parse_plan_directives(plan)
        self.assertEqual(d.get("NEXT_REPO"), "NONE")

    def test_case_insensitive_keys(self) -> None:
        plan = "seps_open_task: yes\nSeps Task Title: Fix escrow\n"
        d = parse_plan_directives(plan)
        self.assertEqual(d.get("SEPS_OPEN_TASK"), "yes")
        self.assertEqual(d.get("SEPS_TASK_TITLE"), "Fix escrow")

    def test_detail_with_colon(self) -> None:
        plan = "SEPS_TASK_DETAIL: see docs: anchor escrow\n"
        d = parse_plan_directives(plan)
        self.assertEqual(d.get("SEPS_TASK_DETAIL"), "see docs: anchor escrow")


if __name__ == "__main__":
    unittest.main()
