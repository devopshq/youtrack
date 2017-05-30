import os
import pprint

import pytest
from hamcrest import *
from youtrack.connection import Connection


class TestGetIssues:
    connection = None

    @pytest.fixture(scope='class', autouse=True)
    def init(self):
        server = os.getenv('TEST_SERVER', '')
        user = os.getenv('TEST_USER', '')
        password = os.getenv('TEST_PASSWORD', '')
        TestGetIssues.connection = Connection(server, user, password)
        self.connection = TestGetIssues.connection

    def test_get_issues(self):
        self.connection = TestGetIssues.connection
        project = os.getenv('TEST_PROJECT', '')
        issues = self.connection.get_issues(project, 'for: me #unresolved', 0, 10)
        pprint.PrettyPrinter(indent=0).pprint(issues)
        prev = issues[0]
        for i in range(1, len(issues)):
            assert_that(prev._data, is_not(issues[i]._data))
            prev = issues[i]

    def test_get_issue_attributes(self):
        self.connection = TestGetIssues.connection
        project = os.getenv('TEST_PROJECT', '')
        issues = self.connection.get_issues(project, 'for: me #unresolved', 0, 1)
        pprint.PrettyPrinter(indent=0).pprint(issues)
        if issues:
            issue = issues[0]
            assert_that(issue['id'], is_(instance_of(str)))

    def test_get_issue_attribute_error(self):
        self.connection = TestGetIssues.connection
        project = os.getenv('TEST_PROJECT', '')
        issues = self.connection.get_issues(project, 'for: me #unresolved', 0, 1)
        pprint.PrettyPrinter(indent=0).pprint(issues)
        if issues:
            issue = issues[0]

            with pytest.raises(KeyError) as e_info:
                tmp = issue['wrong_attribute']

            with pytest.raises(AttributeError) as e_info:
                tmp = issue.wrong_attribute

    def test_get_issue_comments(self):
        self.connection = TestGetIssues.connection
        project = os.getenv('TEST_PROJECT', '')
        issues = self.connection.get_issues(project, 'for: me #unresolved', 0, 10)
        pprint.PrettyPrinter(indent=0).pprint(issues)
        count = 0
        for issue in issues:
            comments = issue.get_comments()
            pprint.PrettyPrinter(indent=4).pprint(comments)
            count += len(comments)

        assert_that(count, is_(greater_than(0)))

    def test_get_issue_attachments(self):
        self.connection = TestGetIssues.connection
        project = os.getenv('TEST_PROJECT', '')
        issues = self.connection.get_issues(project, 'for: me #unresolved', 0, 10)
        pprint.PrettyPrinter(indent=0).pprint(issues)
        count = 0
        for issue in issues:
            attachments = issue.get_attachments()
            pprint.PrettyPrinter(indent=4).pprint(attachments)
            count += len(attachments)

        assert_that(count, is_(greater_than(0)))

    def test_get_issue_attachments_content(self):
        self.connection = TestGetIssues.connection
        project = os.getenv('TEST_PROJECT', '')
        issues = self.connection.get_issues(project, 'for: me #unresolved', 0, 10)
        pprint.PrettyPrinter(indent=0).pprint(issues)
        count = 0
        for issue in issues:
            # attachments = issue.get_attachments()
            attachments = self.connection.get_attachments(issue['id'])
            pprint.PrettyPrinter(indent=4).pprint(attachments)
            for attachment in attachments:
                content = attachment.get_content()
                count += content.length

        assert_that(count, is_(greater_than(0)))
