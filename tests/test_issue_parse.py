import unittest

from seps.github_client import parse_issue_number_from_create_output


class IssueParseTest(unittest.TestCase):
    def test_url(self) -> None:
        out = parse_issue_number_from_create_output(
            "https://github.com/seps-sol/agent-marketplace/issues/163\n"
        )
        self.assertEqual(out, 163)

    def test_hash_suffix(self) -> None:
        self.assertEqual(parse_issue_number_from_create_output("created issue #42\n"), 42)


if __name__ == "__main__":
    unittest.main()
