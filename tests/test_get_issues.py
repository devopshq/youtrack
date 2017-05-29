import os
import pprint

import pytest
from youtrack.connection import Connection


class TestGetIssues:
    connection = None

    @pytest.fixture(scope='class', autouse=True)
    def init(self):
        server = os.getenv('TEST_SERVER', '')
        user = os.getenv('TEST_USER', '')
        password = os.getenv('TEST_PASSWORD', '')
        TestGetIssues.connection = Connection(server, user, password)
        pass

    def test_get_issues(self):
        project = os.getenv('TEST_PROJECT', '')
        issues = TestGetIssues.connection.get_issues(project, 'for: me #unresolved', 0, 10)
        pprint.PrettyPrinter(indent=0).pprint(issues)
        prev = issues[0]
        for i in range(1, len(issues)):
            assert prev._data is not issues[i]._data
            prev = issues[i]

    def test_get_issue_attributes(self):
        project = os.getenv('TEST_PROJECT', '')
        issues = TestGetIssues.connection.get_issues(project, 'for: me #unresolved', 0, 1)
        pprint.PrettyPrinter(indent=0).pprint(issues)
        if issues:
            issue = issues[0]
            assert isinstance(issue['id'], str)

    def test_get_issue_attribute_error(self):
        project = os.getenv('TEST_PROJECT', '')
        issues = TestGetIssues.connection.get_issues(project, 'for: me #unresolved', 0, 1)
        pprint.PrettyPrinter(indent=0).pprint(issues)
        if issues:
            issue = issues[0]

            with pytest.raises(KeyError) as e_info:
                tmp = issue['wrong_attribute']

            with pytest.raises(AttributeError) as e_info:
                tmp = issue.wrong_attribute
