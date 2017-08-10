# -*- coding: utf-8 -*-
import calendar
import time
from datetime import datetime
import httplib2
from xml.dom import minidom
import sys
import youtrack
from xml.dom import Node
import urllib
import urllib.parse
import urllib.request
import urllib.error
from xml.sax.saxutils import escape, quoteattr
import json
import tempfile
import functools
import re
import io


def urlquote(s):
    return urllib.parse.quote(utf8encode(s), safe="")


def utf8encode(source):
    if isinstance(source, str):
        source = source.encode('utf-8')
    return source


def relogin_on_401(f):
    @functools.wraps(f)
    def wrapped(self, *args, **kwargs):
        attempts = 10
        while attempts:
            try:
                return f(self, *args, **kwargs)
            except youtrack.YouTrackException as e:
                if e.response.status not in (401, 403, 500, 504):
                    raise e
                if e.response.status == 504:
                    time.sleep(30)
                else:
                    self._login(*self._credentials)
                attempts -= 1
        return f(self, *args, **kwargs)

    return wrapped


class Connection(object):
    def __init__(self, url, login=None, password=None, proxy_info=None, api_key=None):
        self.http = httplib2.Http(disable_ssl_certificate_validation=True) if proxy_info is None else httplib2.Http(
            proxy_info=proxy_info, disable_ssl_certificate_validation=True)

        # Remove the last character of the url ends with "/"
        if url:
            url = url.rstrip('/')

        self.url = url
        self.base_url = url + "/rest"
        if api_key is None:
            self._credentials = (login, password)
            self._login(*self._credentials)
        else:
            self.headers = {'X-YouTrack-ApiKey': api_key}

    def _login(self, login, password):
        response, content = self.http.request(
            self.base_url + "/user/login?login=" + urllib.parse.quote_plus(login) + "&password=" +
            urllib.parse.quote_plus(password), 'POST',
            headers={'Content-Length': '0', 'Connection': 'keep-alive'})
        if response.status != 200:
            raise youtrack.YouTrackException('/user/login', response, content)
        self.headers = {'Cookie': response['set-cookie'],
                        'Cache-Control': 'no-cache'}

    @relogin_on_401
    def _req(self, method, url, body=None, ignore_status=None, content_type=None, accept_header=None):
        headers = self.headers
        headers = headers.copy()
        if method == 'PUT' or method == 'POST':
            if content_type is None:
                content_type = 'application/xml; charset=UTF-8'
            headers['Content-Type'] = content_type
            headers['Content-Length'] = str(len(body)) if body else '0'

        if accept_header is not None:
            headers['Accept'] = accept_header

        response, content = self.http.request(self.base_url + url, method, headers=headers, body=body)
        content = content.translate(None, '\0'.encode('utf-8'))
        _illegal_unichrs = [(0x00, 0x08), (0x0B, 0x0C), (0x0E, 0x1F),
                            (0x7F, 0x84), (0x86, 0x9F), (0xFDD0, 0xFDDF),
                            (0xFFFE, 0xFFFF)]
        _illegal_ranges = ["%s-%s" % (chr(low), chr(high))
                           for (low, high) in _illegal_unichrs]
        _illegal_xml_chars_re = re.compile('[%s]' % ''.join(_illegal_ranges))
        content = re.sub(_illegal_xml_chars_re, '', content.decode('utf-8')).encode('utf-8')
        if response.status != 200 and response.status != 201 and (ignore_status != response.status):
            raise youtrack.YouTrackException(url, response, content)

        return response, content

    def _req_xml(self, method, url, body=None, ignore_status=None):
        response, content = self._req(method, url, body, ignore_status)
        if 'content-type' in response:
            if (response["content-type"].find('application/xml') != -1 or response["content-type"].find(
                    'text/xml') != -1) and content is not None and content != '':
                try:
                    return minidom.parseString(content)
                except youtrack.YouTrackBroadException:
                    return ""
            elif response['content-type'].find('application/json') != -1 and content is not None and content != '':
                try:
                    return json.loads(content)
                except youtrack.YouTrackBroadException:
                    return ""

        if method == 'PUT' and ('location' in response.keys()):
            return 'Created: ' + response['location']
        else:
            return content

    def _get(self, url):
        return self._req_xml('GET', url)

    def _put(self, url):
        return self._req_xml('PUT', url, '<empty/>\n\n')

    def get_issue(self, _id):
        return youtrack.Issue(self._get("/issue/" + _id), self)

    def create_issue(self, project, assignee, summary, description, priority=None, issue_type=None, subsystem=None,
                     state=None,
                     affects_version=None,
                     fixed_version=None, fixed_in_build=None, permitted_group=None):
        params = {'project': project,
                  'summary': summary}
        if description is not None:
            params['description'] = description
        if assignee is not None:
            params['assignee'] = assignee
        if priority is not None:
            params['priority'] = priority
        if issue_type is not None:
            params['type'] = issue_type
        if subsystem is not None:
            params['subsystem'] = subsystem
        if state is not None:
            params['state'] = state
        if affects_version is not None:
            params['affectsVersion'] = affects_version
        if fixed_version is not None:
            params['fixVersion'] = fixed_version
        if fixed_in_build is not None:
            params['fixedInBuild'] = fixed_in_build
        if permitted_group is not None:
            params['permittedGroup'] = permitted_group

        return self._req('PUT', '/issue', urllib.parse.urlencode(params),
                         content_type='application/x-www-form-urlencoded')

    def delete_issue(self, issue_id):
        return self._req('DELETE', '/issue/%s' % issue_id)

    def get_changes_for_issue(self, issue):
        return [youtrack.IssueChange(change, self) for change in
                self._get("/issue/%s/changes" % issue).getElementsByTagName('change')]

    def get_comments(self, _id):
        response, content = self._req('GET', '/issue/' + _id + '/comment')
        xml = minidom.parseString(content)
        return [youtrack.Comment(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def get_attachments(self, _id):
        response, content = self._req('GET', '/issue/' + _id + '/attachment')
        xml = minidom.parseString(content)
        return [youtrack.Attachment(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def get_attachment_content(self, url):
        f = urllib.request.urlopen(urllib.request.Request(self.url + url, headers=self.headers))
        return f

    def delete_attachment(self, issue_id, attachment_id):
        return self._req('DELETE', '/issue/%s/attachment/%s' % (issue_id, attachment_id))

    def create_attachment_from_attachment(self, issue_id, a):
        content = None
        try:
            content = a.getContent()
            content_length = None
            if 'content-length' in content.headers.dict:
                content_length = int(content.headers.dict['content-length'])
            print('Importing attachment for issue ', issue_id)
            try:
                print('Name: ', utf8encode(a.name))
            except Exception as e:
                print(e)
            try:
                print('Author: ', a.authorLogin)
            except Exception as e:
                print(e)
            return self.import_attachment(issue_id, a.name, content, a.authorLogin,
                                          content_length=content_length,
                                          content_type=content.info().type,
                                          created=a.created if hasattr(a, 'created') else None,
                                          group=utf8encode(a.group) if hasattr(a, 'group') else '')
        except urllib.error.HTTPError as e:
            print("Can't create attachment")
            try:
                err_content = e.read()
                issue_id = issue_id
                attach_name = a.name
                attach_url = a.url
                if isinstance(err_content, str):
                    err_content = err_content.encode('utf-8')
                if isinstance(issue_id, str):
                    issue_id = issue_id.encode('utf-8')
                if isinstance(attach_name, str):
                    attach_name = attach_name.encode('utf-8')
                if isinstance(attach_url, str):
                    attach_url = attach_url.encode('utf-8')
                print("HTTP CODE: ", e.code)
                print("REASON: ", err_content)
                print("IssueId: ", issue_id)
                print("Attachment filename: ", attach_name)
                print("Attachment URL: ", attach_url)
            except youtrack.YouTrackBroadException:
                pass
        except youtrack.YouTrackBroadException as e:
            try:
                print(content.geturl())
                print(content.getcode())
                print(content.info())
            except youtrack.YouTrackBroadException:
                pass
            raise e

    def _process_attachments(self, author_login, content, content_length, content_type, created, group, issue_id, name,
                             url_prefix='/issue/'):
        if content_type is not None:
            content.contentType = content_type
        if content_length is not None:
            content.contentLength = content_length
        elif not isinstance(content, io.IOBase):
            tmp = tempfile.NamedTemporaryFile(mode='w+b')
            tmp.write(content.read())
            tmp.flush()
            tmp.seek(0)
            content = tmp

        # post_data = {'attachment': content}
        post_data = {name: content}
        headers = self.headers.copy()
        # headers['Content-Type'] = contentType
        # name without extension to workaround: http://youtrack.jetbrains.net/issue/JT-6110
        params = {  # 'name': os.path.splitext(name)[0],
            'authorLogin': author_login.encode('utf-8'),
        }
        if group is not None:
            params["group"] = group
        if created is not None:
            params['created'] = created
        else:
            try:
                params['created'] = self.get_issue(issue_id)['created']
            except youtrack.YouTrackException:
                params['created'] = str(calendar.timegm(datetime.now().timetuple()) * 1000)

        url = self.base_url + url_prefix + issue_id + "/attachment?" + urllib.parse.urlencode(params)
        r = urllib.request.Request(url,
                                   headers=headers, data=post_data)
        # r.set_proxy('localhost:8888', 'http')
        try:
            res = urllib.request.urlopen(r)
        except urllib.error.HTTPError as e:
            if e.code == 201:
                return e.msg + ' ' + name
            raise e
        return res

    def create_attachment(self, issue_id, name, content, author_login='', content_type=None, content_length=None,
                          created=None, group=''):
        return self._process_attachments(author_login, content, content_length, content_type, created, group, issue_id,
                                         name)

    def import_attachment(self, issue_id, name, content, author_login, content_type, content_length, created=None,
                          group=''):
        return self._process_attachments(author_login, content, content_length, content_type, created, group, issue_id,
                                         name, '/import/')

    def get_links(self, _id, outward_only=False):
        response, content = self._req('GET', '/issue/' + urlquote(_id) + '/link')
        xml = minidom.parseString(content)
        res = []
        for c in [e for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]:
            link = youtrack.Link(c, self)
            if link.source == _id or not outward_only:
                res.append(link)
        return res

    def get_user(self, login):
        """ http://confluence.jetbrains.net/display/YTD2/GET+user
        """
        return youtrack.User(self._get("/admin/user/" + urlquote(login.encode('utf8'))), self)

    def create_user(self, user):
        """ user from getUser
        """
        # self.createUserDetailed(user.login, user.fullName, user.email, user.jabber)
        self.import_users([user])

    def create_user_detailed(self, login, full_name, email, jabber):
        self.import_users([{'login': login, 'fullName': full_name, 'email': email, 'jabber': jabber}])

    #        return self._put('/admin/user/' + login + '?' +
    #                         'password=' + password +
    #                         '&fullName=' + fullName +
    #                         '&email=' + email +
    #                         '&jabber=' + jabber)

    def import_users(self, users):
        """ Import users, returns import result (http://confluence.jetbrains.net/display/YTD2/Import+Users)
            Example: importUsers([{'login':'vadim', 'fullName':'vadim', 'email':'eee@ss.com', 'jabber':'fff@fff.com'},
                                  {'login':'maxim', 'fullName':'maxim', 'email':'aaa@ss.com', 'jabber':'www@fff.com'}])
        """
        if len(users) <= 0:
            return

        known_attrs = ('login', 'fullName', 'email', 'jabber')

        xml = '<list>\n'
        for u in users:
            xml += '  <user ' + "".join(k + '=' + quoteattr(u[k]) + ' ' for k in u if k in known_attrs) + '/>\n'
        xml += '</list>'
        # TODO: convert response xml into python objects
        if isinstance(xml, str):
            xml = xml.encode('utf-8')
        return self._req_xml('PUT', '/import/users', xml, 400).toxml()

    def import_issues_xml(self, project_id, assignee_group, xml):
        return self._req_xml('PUT', '/import/' + urlquote(project_id) + '/issues?' +
                             urllib.parse.urlencode({'assigneeGroup': assignee_group}),
                             xml, 400).toxml()

    def import_links(self, links):
        """ Import links, returns import result (http://confluence.jetbrains.net/display/YTD2/Import+Links)
            Accepts result of getLinks()
            Example: importLinks([{'login':'vadim', 'fullName':'vadim', 'email':'eee@ss.com', 'jabber':'fff@fff.com'},
                                  {'login':'maxim', 'fullName':'maxim', 'email':'aaa@ss.com', 'jabber':'www@fff.com'}])
        """
        xml = '<list>\n'
        for l in links:
            # ignore typeOutward and typeInward returned by getLinks()
            xml += '  <link ' + "".join(attr + '=' + quoteattr(l[attr]) +
                                        ' ' for attr in l if attr not in ['typeInward', 'typeOutward']) + '/>\n'
        xml += '</list>'
        # TODO: convert response xml into python objects
        res = self._req_xml('PUT', '/import/links', xml, 400)
        return res.toxml() if hasattr(res, "toxml") else res

    def import_issues(self, project_id, assignee_group, issues):
        """ Import issues, returns import result (http://confluence.jetbrains.net/display/YTD2/Import+Issues)
            Accepts return of getIssues()
            Example: importIssues([{'numberInProject':'1', 'summary':'some problem', 'description':'some description',
                                    'priority':'1',
                                    'fixedVersion':['1.0', '2.0'],
                                    'comment':[{'author':'yamaxim', 'text':'comment text', 'created':'1267030230127'}]},
                                   {'numberInProject':'2', 'summary':'some problem', 'description':'some description',
                                    'priority':'1'}])
        """
        if len(issues) <= 0:
            return

        bad_fields = ['id', 'projectShortName', 'votes', 'commentsCount',
                      'historyUpdated', 'updatedByFullName', 'updaterFullName',
                      'reporterFullName', 'links', 'attachments', 'jiraId',
                      'entityId', 'tags', 'sprint']

        tt_settings = self.get_project_time_tracking_settings(project_id)
        if tt_settings and tt_settings['Enabled'] and tt_settings['TimeSpentField']:
            bad_fields.append(tt_settings['TimeSpentField'])

        xml = '<issues>\n'
        issue_records = dict([])

        for issue in issues:
            record = ""
            record += '  <issue>\n'

            comments = None
            if getattr(issue, "getComments", None):
                comments = issue.get_comments()

            for issue_attr in issue:
                attr_value = issue[issue_attr]
                if attr_value is None:
                    continue
                if isinstance(attr_value, str):
                    attr_value = attr_value.encode('utf-8')
                if isinstance(issue_attr, str):
                    issue_attr = issue_attr.encode('utf-8')
                if issue_attr == 'comments':
                    comments = attr_value
                else:
                    # ignore bad fields from getIssue()
                    if issue_attr not in bad_fields:
                        record += '    <field name="' + issue_attr + '">\n'
                        if isinstance(attr_value, list) or getattr(attr_value, '__iter__', False):
                            for v in attr_value:
                                if isinstance(v, str):
                                    v = v.encode('utf-8')
                                record += '      <value>' + escape(v.strip()) + '</value>\n'
                        else:
                            record += '      <value>' + escape(attr_value.strip()) + '</value>\n'
                        record += '    </field>\n'

            if comments:
                for comment in comments:
                    record += '    <comment'
                    for ca in comment:
                        val = comment[ca]
                        if isinstance(ca, str):
                            ca = ca.encode('utf-8')
                        if isinstance(val, str):
                            val = val.encode('utf-8')
                        record += ' ' + ca + '=' + quoteattr(val)
                    record += '/>\n'

            record += '  </issue>\n'
            xml += record
            issue_records[issue.numberInProject] = record

        xml += '</issues>'

        # print xml
        # TODO: convert response xml into python objects

        if isinstance(xml, str):
            xml = xml.encode('utf-8')

        if isinstance(assignee_group, str):
            assignee_group = assignee_group.encode('utf-8')

        url = '/import/' + urlquote(project_id) + '/issues?' + urllib.parse.urlencode({'assigneeGroup': assignee_group})
        if isinstance(url, str):
            url = url.encode('utf-8')
        result = self._req_xml('PUT', url, xml, 400)
        if (result == "") and (len(issues) > 1):
            for issue in issues:
                self.import_issues(project_id, assignee_group, [issue])
        response = ""
        try:
            response = result.toxml().encode('utf-8')
        except youtrack.YouTrackBroadException:
            sys.stderr.write("can't parse response")
            sys.stderr.write("request was")
            sys.stderr.write(xml)
            return response
        item_elements = minidom.parseString(response).getElementsByTagName("item")
        if len(item_elements) != len(issues):
            sys.stderr.write(response)
        else:
            for item in item_elements:
                _id = item.attributes["id"].value
                imported = item.attributes["imported"].value.lower()
                if imported == "true":
                    print("Issue [ %s-%s ] imported successfully" % (project_id, _id))
                else:
                    sys.stderr.write("")
                    sys.stderr.write("Failed to import issue [ %s-%s ]." % (project_id, _id))
                    sys.stderr.write("Reason : ")
                    sys.stderr.write(item.toxml())
                    sys.stderr.write("Request was :")
                    if isinstance(issue_records[_id], str):
                        sys.stderr.write(issue_records[_id].encode('utf-8'))
                    else:
                        sys.stderr.write(issue_records[_id])
                print("")
        return response

    def get_projects(self):
        projects = {}
        for e in self._get("/project/all").documentElement.childNodes:
            projects[e.getAttribute('shortName')] = e.getAttribute('name')
        return projects

    def get_project(self, project_id):
        """ http://confluence.jetbrains.net/display/YTD2/GET+project
        """
        return youtrack.Project(self._get("/admin/project/" + urlquote(project_id)), self)

    def get_project_ids(self):
        response, content = self._req('GET', '/admin/project/')
        xml = minidom.parseString(content)
        return [e.getAttribute('id') for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def get_project_assignee_groups(self, project_id):
        response, content = self._req('GET', '/admin/project/' + urlquote(project_id) + '/assignee/group')
        xml = minidom.parseString(content)
        return [youtrack.Group(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def get_group(self, name):
        return youtrack.Group(self._get("/admin/group/" + urlquote(name.encode('utf-8'))), self)

    def get_groups(self):
        response, content = self._req('GET', '/admin/group')
        xml = minidom.parseString(content)
        return [youtrack.Group(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def delete_group(self, name):
        return self._req('DELETE', "/admin/group/" + urlquote(name.encode('utf-8')))

    def get_user_groups(self, user_name):
        response, content = self._req('GET', '/admin/user/%s/group' % urlquote(user_name.encode('utf-8')))
        xml = minidom.parseString(content)
        return [youtrack.Group(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def set_user_group(self, user_name, group_name):
        if isinstance(user_name, str):
            user_name = user_name.encode('utf-8')
        if isinstance(group_name, str):
            group_name = group_name.encode('utf-8')
        response, content = self._req('POST',
                                      '/admin/user/%s/group/%s' % (urlquote(user_name), urlquote(group_name)),
                                      body='')
        return response

    def create_group(self, group):
        content = self._put(
            '/admin/group/%s?autoJoin=false' % group.name.replace(' ', '%20'))
        return content

    def add_user_role_to_group(self, group, user_role):
        url_group_name = urlquote(utf8encode(group.name))
        url_role_name = urlquote(utf8encode(user_role.name))
        response, content = self._req('PUT', '/admin/group/%s/role/%s' % (url_group_name, url_role_name),
                                      body=user_role.to_xml())
        return content

    def get_role(self, name):
        return youtrack.Role(self._get("/admin/role/" + urlquote(name)), self)

    def get_roles(self):
        response, content = self._req('GET', '/admin/role')
        xml = minidom.parseString(content)
        return [youtrack.Role(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def get_group_roles(self, group_name):
        response, content = self._req('GET', '/admin/group/%s/role' % urlquote(group_name))
        xml = minidom.parseString(content)
        return [youtrack.UserRole(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def create_role(self, role):
        url_role_name = urlquote(utf8encode(role.name))
        url_role_dscr = ''
        if hasattr(role, 'description'):
            url_role_dscr = urlquote(utf8encode(role.description))
        content = self._put('/admin/role/%s?description=%s' % (url_role_name, url_role_dscr))
        return content

    def change_role(self, role, new_name, new_description):
        url_role_name = urlquote(utf8encode(role.name))
        url_new_name = urlquote(utf8encode(new_name))
        url_new_dscr = urlquote(utf8encode(new_description))
        content = self._req('POST',
                            '/admin/role/%s?newName=%s&description=%s' % (url_role_name, url_new_name, url_new_dscr))
        return content

    def add_permission_to_role(self, role, permission):
        url_role_name = urlquote(role.name)
        url_prm_name = urlquote(permission.name)
        content = self._req('POST', '/admin/role/%s/permission/%s' % (url_role_name, url_prm_name))
        return content

    def get_role_permissions(self, role):
        response, content = self._req('GET', '/admin/role/%s/permission' % urlquote(role.name))
        xml = minidom.parseString(content)
        return [youtrack.Permission(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def get_permissions(self):
        response, content = self._req('GET', '/admin/permission')
        xml = minidom.parseString(content)
        return [youtrack.Permission(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def get_subsystem(self, project_id, name):
        response, content = self._req('GET', '/admin/project/' + project_id + '/subsystem/' + urlquote(name))
        xml = minidom.parseString(content)
        return youtrack.Subsystem(xml, self)

    def get_subsystems(self, project_id):
        response, content = self._req('GET', '/admin/project/' + project_id + '/subsystem')
        xml = minidom.parseString(content)
        return [youtrack.Subsystem(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def get_versions(self, project_id):
        response, content = self._req('GET', '/admin/project/' + urlquote(project_id) + '/version?showReleased=true')
        xml = minidom.parseString(content)
        return [self.get_version(project_id, v.getAttribute('name')) for v in
                xml.documentElement.getElementsByTagName('version')]

    def get_version(self, project_id, name):
        return youtrack.Version(
            self._get("/admin/project/" + urlquote(project_id) + "/version/" + urlquote(name)), self)

    def get_builds(self, project_id):
        response, content = self._req('GET', '/admin/project/' + urlquote(project_id) + '/build')
        xml = minidom.parseString(content)
        return [youtrack.Build(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def get_users(self, params=None):
        if params is None:
            params = {}
        users = []
        position = 0
        user_search_params = urllib.parse.urlencode(params)
        while True:
            response, content = self._req('GET', "/admin/user/?start=%s&%s" % (str(position), user_search_params))
            position += 10
            xml = minidom.parseString(content)
            new_users = [youtrack.User(e, self) for e in xml.documentElement.childNodes if
                         e.nodeType == Node.ELEMENT_NODE]
            if not len(new_users):
                return users
            users += new_users

    def get_users_ten(self, start):
        response, content = self._req('GET', "/admin/user/?start=%s" % str(start))
        xml = minidom.parseString(content)
        users = [youtrack.User(e, self) for e in xml.documentElement.childNodes if
                 e.nodeType == Node.ELEMENT_NODE]
        return users

    def delete_user(self, login):
        return self._req('DELETE', "/admin/user/" + urlquote(login.encode('utf-8')))

    # TODO this function is deprecated
    def create_build(self):
        raise NotImplementedError

    # TODO this function is deprecated
    def create_builds(self):
        raise NotImplementedError

    def create_project(self, project):
        return self.create_project_detailed(project.id, project.name, project.description, project.lead)

    def delete_project(self, project_id):
        return self._req('DELETE', "/admin/project/" + urlquote(project_id))

    def create_project_detailed(self, project_id, name, description, project_lead_login, starting_number=1):
        _name = name
        _desc = description
        if isinstance(_name, str):
            _name = _name.encode('utf-8')
        if isinstance(_desc, str):
            _desc = _desc.encode('utf-8')
        return self._put('/admin/project/' + project_id + '?' +
                         urllib.parse.urlencode({'projectName': _name,
                                                 'description': _desc + ' '.encode('utf-8'),
                                                 'projectLeadLogin': project_lead_login,
                                                 'lead': project_lead_login,
                                                 'startingNumber': str(starting_number)}))

    # TODO this function is deprecated
    def create_subsystems(self, project_id, subsystems):
        """ Accepts result of getSubsystems()
        """

        for s in subsystems:
            self.create_subsystem(project_id, s)

    # TODO this function is deprecated
    def create_subsystem(self, project_id, s):
        return self.create_subsystem_detailed(project_id, s.name, s.isDefault,
                                              s.defaultAssignee if s.defaultAssignee != '<no user>' else '')

    # TODO this function is deprecated
    def create_subsystem_detailed(self, project_id, name, is_default, default_assignee_login):
        self._put('/admin/project/' + project_id + '/subsystem/' + urlquote(name.encode('utf-8')) + "?" +
                  urllib.parse.urlencode({'isDefault': str(is_default),
                                          'defaultAssignee': default_assignee_login}))

        return 'Created'

    # TODO this function is deprecated
    def delete_subsystem(self, project_id, name):
        return self._req_xml('DELETE', '/admin/project/' + project_id + '/subsystem/' + urlquote(name.encode('utf-8')),
                             '')

    # TODO this function is deprecated
    def create_versions(self, project_id, versions):
        """ Accepts result of getVersions()
        """

        for v in versions:
            self.create_version(project_id, v)

    # TODO this function is deprecated
    def create_version(self, project_id, v):
        return self.create_version_detailed(project_id, v.name, v.isReleased, v.isArchived, release_date=v.releaseDate,
                                            description=v.description)

    # TODO this function is deprecated
    def create_version_detailed(self, project_id, name, is_released, is_archived, release_date=None, description=''):
        params = {'description': description,
                  'isReleased': str(is_released),
                  'isArchived': str(is_archived)}
        if release_date is not None:
            params['releaseDate'] = str(release_date)
        return self._put(
            '/admin/project/' + urlquote(project_id) + '/version/' + urlquote(name.encode('utf-8')) + "?" +
            urllib.parse.urlencode(params))

    def get_issues(self, project_id, _filter, after, _max, updated_after=None, wikify=None):
        # response, content = self._req('GET', '/project/issues/' + urlquote(projectId) + "?" +
        params = {'after': str(after),
                  'max': str(_max),
                  'filter': _filter}
        if updated_after is not None:
            params['updatedAfter'] = updated_after
        if wikify is not None:
            params['wikifyDescription'] = wikify
        response, content = self._req('GET', '/issue/byproject/' + urlquote(project_id) + "?" +
                                      urllib.parse.urlencode(params))
        xml = minidom.parseString(content)
        return [youtrack.Issue(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def get_number_of_issues(self, _filter='', wait_for_server=True):
        while True:
            url_filter_list = [('filter', _filter)]
            final_url = '/issue/count?' + urllib.parse.urlencode(url_filter_list)
            response, content = self._req('GET', final_url, None, None, None, 'application/json')
            result = eval(content.replace('callback'.encode('utf-8'), ''.encode('utf-8')))
            number_of_issues = result['value']
            if not wait_for_server:
                return number_of_issues
            if number_of_issues != -1:
                break

        time.sleep(5)
        return self.get_number_of_issues(_filter, False)

    def get_all_sprints(self, agile_id):
        response, content = self._req('GET', '/agile/' + agile_id + "/sprints?")
        xml = minidom.parseString(content)
        return [(e.getAttribute('name'), e.getAttribute('start'), e.getAttribute('finish')) for e in
                xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def get_all_issues(self, _filter='', after=0, _max=999999, with_fields=()):
        url_jobby = [('with', field) for field in with_fields] + \
                    [('after', str(after)),
                     ('max', str(_max)),
                     ('filter', _filter)]
        response, content = self._req('GET', '/issue' + "?" +
                                      urllib.parse.urlencode(url_jobby))
        xml = minidom.parseString(content)
        return [youtrack.Issue(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def export_issue_links(self):
        response, content = self._req('GET', '/export/links')
        xml = minidom.parseString(content)
        return [youtrack.Link(e, self) for e in xml.documentElement.childNodes if e.nodeType == Node.ELEMENT_NODE]

    def execute_command(self, issue_id, command, comment=None, group=None, run_as=None, disable_notifications=False):
        if isinstance(command, str):
            command = command.encode('utf-8')
        params = {'command': command}

        if comment is not None:
            params['comment'] = comment

        if group is not None:
            params['group'] = group

        if run_as is not None:
            params['runAs'] = run_as

        if disable_notifications:
            params['disableNotifications'] = disable_notifications

        for p in params:
            if isinstance(params[p], str):
                params[p] = params[p].encode('utf-8')

        self._req('POST', '/issue/' + issue_id + "/execute?" + urllib.parse.urlencode(params), body='')

        return "Command executed"

    def get_custom_field(self, name):
        return youtrack.CustomField(self._get("/admin/customfield/field/" + urlquote(name.encode('utf-8'))), self)

    def get_custom_fields(self):
        response, content = self._req('GET', '/admin/customfield/field')
        xml = minidom.parseString(content)
        return [self.get_custom_field(e.getAttribute('name')) for e in xml.documentElement.childNodes if
                e.nodeType == Node.ELEMENT_NODE]

    def create_custom_field(self, cf):
        params = dict([])
        if hasattr(cf, "defaultBundle"):
            params["defaultBundle"] = cf.defaultBundle
        if hasattr(cf, "attachBundlePolicy"):
            params["attachBundlePolicy"] = cf.attachBundlePolicy
        auto_attached = False
        if hasattr(cf, "autoAttached"):
            auto_attached = cf.autoAttached
        return self.create_custom_field_detailed(cf.name, cf.type, cf.isPrivate, cf.visibleByDefault, auto_attached,
                                                 params)

    def create_custom_field_detailed(self, custom_field_name, type_name, is_private, default_visibility,
                                     auto_attached=False, additional_params=None):
        if additional_params is None:
            additional_params = dict([])
        params = {'type': type_name, 'isPrivate': str(is_private), 'defaultVisibility': str(default_visibility),
                  'autoAttached': str(auto_attached)}
        params.update(additional_params)
        for key in params:
            if isinstance(params[key], str):
                params[key] = params[key].encode('utf-8')

        self._put('/admin/customfield/field/' + urlquote(custom_field_name.encode('utf-8')) + '?' +
                  urllib.parse.urlencode(params), )

        return "Created"

    def create_custom_fields(self, cfs):
        for cf in cfs:
            self.create_custom_field(cf)

    def get_project_custom_field(self, project_id, name):
        if isinstance(name, str):
            name = name.encode('utf8')
        return youtrack.ProjectCustomField(
            self._get("/admin/project/" + urlquote(project_id) + "/customfield/" + urlquote(name)), self)

    def get_project_custom_fields(self, project_id):
        response, content = self._req('GET', '/admin/project/' + urlquote(project_id) + '/customfield')
        xml = minidom.parseString(content)
        return [self.get_project_custom_field(project_id, e.getAttribute('name')) for e in
                xml.getElementsByTagName('projectCustomField')]

    def create_project_custom_field(self, project_id, pcf):
        return self.create_project_custom_field_detailed(project_id, pcf.name, pcf.emptyText, pcf.params)

    def create_project_custom_field_detailed(self, project_id, custom_field_name, empty_field_text, params=None):
        if not len(empty_field_text.strip()):
            empty_field_text = u"No " + custom_field_name
        if isinstance(custom_field_name, str):
            custom_field_name = custom_field_name.encode('utf-8')
        _params = {'emptyFieldText': empty_field_text}
        if params is not None:
            _params.update(params)
        for key in _params:
            if isinstance(_params[key], str):
                _params[key] = _params[key].encode('utf-8')
        return self._put(
            '/admin/project/' + project_id + '/customfield/' + urlquote(custom_field_name) + '?' +
            urllib.parse.urlencode(_params))

    def delete_project_custom_field(self, project_id, pcf_name):
        self._req('DELETE', '/admin/project/' + urlquote(project_id) + "/customfield/" + urlquote(pcf_name))

    def get_issue_link_types(self):
        response, content = self._req('GET', '/admin/issueLinkType')
        xml = minidom.parseString(content)
        return [youtrack.IssueLinkType(e, self) for e in xml.getElementsByTagName('issueLinkType')]

    def create_issue_link_types(self, issue_link_types):
        for ilt in issue_link_types:
            return self.create_issue_link_type(ilt)

    def create_issue_link_type(self, ilt):
        return self.create_issue_link_type_detailed(ilt.name, ilt.outward_name, ilt.inward_name, ilt.directed)

    def create_issue_link_type_detailed(self, name, outward_name, inward_name, directed):
        if isinstance(name, str):
            name = name.encode('utf-8')
        if isinstance(outward_name, str):
            outward_name = outward_name.encode('utf-8')
        if isinstance(inward_name, str):
            inward_name = inward_name.encode('utf-8')
        return self._put('/admin/issueLinkType/' + urlquote(name) + '?' +
                         urllib.parse.urlencode({'outwardName': outward_name,
                                                 'inwardName': inward_name,
                                                 'directed': directed}))

    def get_events(self, issue_id):
        return self._get('/event/issueEvents/' + urlquote(issue_id))

    def get_work_items(self, issue_id):
        try:
            response, content = self._req('GET',
                                          '/issue/%s/timetracking/workitem' % urlquote(issue_id))
            xml = minidom.parseString(content)
            return [youtrack.WorkItem(e, self) for e in xml.documentElement.childNodes if
                    e.nodeType == Node.ELEMENT_NODE]
        except youtrack.YouTrackException as e:
            print("Can't get work items.", str(e))
            return []

    def create_work_item(self, issue_id, work_item):
        xml = '<workItem>'
        xml += '<date>%s</date>' % work_item.date
        xml += '<duration>%s</duration>' % work_item.duration
        if hasattr(work_item, 'description') and work_item.description is not None:
            xml += '<description>%s</description>' % escape(work_item.description)
        if hasattr(work_item, 'worktype') and work_item.worktype is not None:
            xml += '<worktype><name>%s</name></worktype>' % work_item.worktype
        xml += '</workItem>'
        if isinstance(xml, str):
            xml = xml.encode('utf-8')
        self._req_xml('POST',
                      '/issue/%s/timetracking/workitem' % urlquote(issue_id), xml)

    def import_work_items(self, issue_id, work_items):
        xml = ''
        for work_item in work_items:
            xml += '<workItem>'
            xml += '<date>%s</date>' % work_item.date
            xml += '<duration>%s</duration>' % work_item.duration
            if hasattr(work_item, 'description') and work_item.description is not None:
                xml += '<description>%s</description>' % escape(work_item.description)
            if hasattr(work_item, 'worktype') and work_item.worktype is not None:
                xml += '<worktype><name>%s</name></worktype>' % work_item.worktype
            xml += '<author login=%s></author>' % quoteattr(work_item.authorLogin)
            xml += '</workItem>'
        if isinstance(xml, str):
            xml = xml.encode('utf-8')
        if xml:
            xml = '<workItems>' + xml + '</workItems>'
            self._req_xml('PUT',
                          '/import/issue/%s/workitems' % urlquote(issue_id), xml)

    def get_search_intelli_sense(self, query,
                                 context=None, caret=None, options_limit=None):
        opts = {'filter': query}
        if context:
            opts['project'] = context
        if caret is not None:
            opts['caret'] = caret
        if options_limit is not None:
            opts['optionsLimit'] = options_limit
        return youtrack.IntelliSense(
            self._get('/issue/intellisense?' + urllib.parse.urlencode(opts)), self)

    def get_command_intelli_sense(self, issue_id, command,
                                  run_as=None, caret=None, options_limit=None):
        opts = {'command': command}
        if run_as:
            opts['runAs'] = run_as
        if caret is not None:
            opts['caret'] = caret
        if options_limit is not None:
            opts['optionsLimit'] = options_limit
        return youtrack.IntelliSense(
            self._get('/issue/%s/execute/intellisense?%s'
                      % (issue_id, urllib.parse.urlencode(opts))), self)

    def get_global_time_tracking_settings(self):
        try:
            cont = self._get('/admin/timetracking')
            return youtrack.GlobalTimeTrackingSettings(cont, self)
        except youtrack.YouTrackException as e:
            if e.response.status != 404:
                raise e

    def get_project_time_tracking_settings(self, project_id):
        try:
            cont = self._get('/admin/project/' + project_id + '/timetracking')
            return youtrack.ProjectTimeTrackingSettings(cont, self)
        except youtrack.YouTrackException as e:
            if e.response.status != 404:
                raise e

    def set_global_time_tracking_settings(self, days_a_week=None, hours_a_day=None):
        xml = '<timesettings>'
        if days_a_week is not None:
            xml += '<daysAWeek>%d</daysAWeek>' % days_a_week
        if hours_a_day is not None:
            xml += '<hoursADay>%d</hoursADay>' % hours_a_day
        xml += '</timesettings>'
        return self._req_xml('PUT', '/admin/timetracking', xml)

    def set_project_time_tracking_settings(self,
                                           project_id, estimate_field=None, time_spent_field=None, enabled=None):
        if enabled is not None:
            xml = '<settings enabled="%s">' % str(enabled is True).lower()
        else:
            xml = '<settings>'
        if estimate_field is not None and estimate_field != '':
            xml += '<estimation name="%s"/>' % estimate_field
        if time_spent_field is not None and time_spent_field != '':
            xml += '<spentTime name="%s"/>' % time_spent_field
        xml += '</settings>'
        return self._req_xml(
            'PUT', '/admin/project/' + project_id + '/timetracking', xml)

    def get_all_bundles(self, field_type):
        field_type = self.get_field_type(field_type)
        if field_type == "enum":
            tag_name = "enumFieldBundle"
        elif field_type == "user":
            tag_name = "userFieldBundle"
        else:
            tag_name = self.bundle_paths[field_type]
        names = [e.getAttribute("name") for e in self._get('/admin/customfield/' +
                                                           self.bundle_paths[field_type]).getElementsByTagName(
            tag_name)]
        return [self.get_bundle(field_type, name) for name in names]

    @staticmethod
    def get_field_type(field_type):
        if "[" in field_type:
            field_type = field_type[0:-3]
        return field_type

    def get_bundle(self, field_type, name):
        field_type = self.get_field_type(field_type)
        response = self._get('/admin/customfield/%s/%s' % (self.bundle_paths[field_type],
                                                           urlquote(name.encode('utf-8'))))
        return self.bundle_types[field_type](response, self)

    def rename_bundle(self, bundle, new_name):
        response, content = self._req("POST", "/admin/customfield/%s/%s?newName=%s" % (
            self.bundle_paths[bundle.get_field_type()], bundle.name, new_name), "", ignore_status=301)
        return response

    def create_bundle(self, bundle):
        return self._req_xml('PUT', '/admin/customfield/' + self.bundle_paths[bundle.get_field_type()],
                             body=bundle.to_xml(), ignore_status=400)

    def delete_bundle(self, bundle):
        response, content = self._req("DELETE", "/admin/customfield/%s/%s" % (
            self.bundle_paths[bundle.get_field_type()], bundle.name), "")
        return response

    def add_value_to_bundle(self, bundle, value):
        if bundle.get_field_type() != "user":
            request = "/admin/customfield/%s/%s/" % (
                self.bundle_paths[bundle.get_field_type()], urlquote(bundle.name.encode('utf-8')))
            if isinstance(value, str):
                request += urlquote(value)
            elif isinstance(value, str):
                request += urlquote(value.encode('utf-8'))
            else:
                request += urlquote(value.name.encode('utf-8')) + "?"
                params = dict()
                for e in value:
                    if (e != "name") and (e != "element_name") and len(value[e]):
                        if isinstance(value[e], str):
                            params[e] = value[e].encode('utf-8')
                        else:
                            params[e] = value[e]
                if len(params):
                    request += urllib.parse.urlencode(params)
        else:
            request = "/admin/customfield/userBundle/%s/" % urlquote(bundle.name.encode('utf-8'))
            if isinstance(value, youtrack.User):
                request += "individual/%s/" % value.login
            elif isinstance(value, youtrack.Group):
                request += "group/%s/" % urlquote(value.name.encode('utf-8'))
            else:
                request += "individual/%s/" % urlquote(value)
        return self._put(request)

    def remove_value_from_bundle(self, bundle, value):
        field_type = bundle.get_field_type()
        request = "/admin/customfield/%s/%s/" % (self.bundle_paths[field_type], bundle.name)
        if field_type != "user":
            request += urlquote(value.name)
        elif isinstance(value, youtrack.User):
            request += "individual/" + urlquote(value.login)
        else:
            request += "group/" + value.name
        response, content = self._req("DELETE", request, "", ignore_status=204)
        return response

    def get_enum_bundle(self, name):
        return youtrack.EnumBundle(self._get("/admin/customfield/bundle/" + urlquote(name)), self)

    def create_enum_bundle(self, eb):
        return self.create_bundle(eb)

    def delete_enum_bundle(self, name):
        return self.delete_bundle(self.get_enum_bundle(name))

    def create_enum_bundle_detailed(self, name, values):
        xml = '<enumeration name=\"' + name.encode('utf-8') + '\">'
        xml += ' '.join('<value>' + v + '</value>' for v in values)
        xml += '</enumeration>'
        return self._req_xml('PUT', '/admin/customfield/bundle', body=xml.encode('utf8'), ignore_status=400)

    def add_value_to_enum_bundle(self, name, value):
        return self.add_value_to_bundle(self.get_enum_bundle(name), value)

    def add_values_to_enum_bundle(self, name, values):
        return ", ".join(self.add_value_to_enum_bundle(name, value) for value in values)

    bundle_paths = {
        "enum": "bundle",
        "build": "buildBundle",
        "ownedField": "ownedFieldBundle",
        "state": "stateBundle",
        "version": "versionBundle",
        "user": "userBundle",
    }

    bundle_types = {
        "enum": youtrack.EnumBundle,
        "build": youtrack.BuildBundle,
        "ownedField": youtrack.OwnedFieldBundle,
        "state": youtrack.StateBundle,
        "version": youtrack.VersionBundle,
        "user": youtrack.UserBundle,
    }
