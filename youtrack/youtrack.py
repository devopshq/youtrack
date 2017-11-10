# -*- coding: utf-8 -*-
"""
YouTrack 2.0 REST API (python 3 version)
"""

import re
from xml.dom import Node
from xml.dom.minidom import Document
from xml.dom import minidom
from xml.sax.saxutils import escape

basestring = (str, bytes)
EXISTING_FIELD_TYPES = {
    'numberInProject': 'integer',
    'summary': 'string',
    'description': 'string',
    'created': 'date',
    'updated': 'date',
    'updaterName': 'user[1]',
    'resolved': 'date',
    'reporterName': 'user[1]',
    'watcherName': 'user[*]',
    'voterName': 'user[*]'
}

EXISTING_FIELDS = ['numberInProject', 'projectShortName'] + [x for x in EXISTING_FIELD_TYPES.keys()]


def cmp(a, b):
    return (a > b) - (a < b)


def to_str(a):
    return a.decode('utf-8') if isinstance(a, bytes) else str(a)


def to_bytes(a):
    return a.encode('utf-8') if isinstance(a, str) else a


# mixin class for Python3 supporting __cmp__
class Py3Cmp:
    def __eq__(self, other):
        return self.__cmp__(other) == 0

    def __ne__(self, other):
        return self.__cmp__(other) != 0

    def __gt__(self, other):
        return self.__cmp__(other) > 0

    def __lt__(self, other):
        return self.__cmp__(other) < 0

    def __ge__(self, other):
        return self.__cmp__(other) >= 0

    def __le__(self, other):
        return self.__cmp__(other) <= 0


class YouTrackBroadException(Exception):
    def __init__(self, msg):
        self.message = msg
        super().__init__(msg)


class YouTrackException(Exception):
    def __init__(self, url, response, content):
        self.response = response
        self.content = content
        msg = 'Error for [' + url + "]: " + str(response.status)

        if response.reason is not None:
            msg += ": " + response.reason

        if 'content-type' in response:
            ct = response["content-type"]
            if ct is not None and ct.find('text/html') == -1:
                try:
                    xml = minidom.parseString(content)
                    self.error = YouTrackError(xml, self)
                    msg += ": " + self.error.error
                except YouTrackBroadException:
                    self.error = content
                    msg += ": " + self.error

        super().__init__(msg)


class YouTrackObject(Py3Cmp):
    def __init__(self, xml=None, youtrack=None):
        self._data = {}
        self.youtrack = youtrack
        self._attribute_types = dict()
        self._update(xml)

    def to_xml(self):
        raise NotImplementedError

    def _update(self, xml):
        if xml is None:
            return
        if isinstance(xml, Document):
            xml = xml.documentElement

        self._update_from_attrs(xml)
        self._update_from_children(xml)

    def _update_from_attrs(self, el):
        if el.attributes is not None:
            for i in range(el.attributes.length):
                a = el.attributes.item(i)
                self[a.name] = a.value

    def _update_from_children(self, el):
        children = [e for e in el.childNodes if e.nodeType == Node.ELEMENT_NODE]
        if children:
            for c in children:
                name = c.getAttribute('name')
                value = None
                if not len(name):
                    continue
                name = to_str(name)
                values = c.getElementsByTagName('value')
                if (values is not None) and len(values):
                    if values.length == 1:
                        value = self._text(values.item(0))
                    elif values.length > 1:
                        value = [self._text(value) for value in values]
                elif c.hasAttribute('value'):
                    value = c.getAttribute('value')
                if value is not None:
                    self[name] = value
                    if c.hasAttribute('xsi:type'):
                        self._attribute_types[name] = c.getAttribute('xsi:type')

    @staticmethod
    def _text(el):
        return "".join([e.data for e in el.childNodes if e.nodeType == Node.TEXT_NODE])

    def __repr__(self):
        _repr = ''
        for k, v in self._data.items():
            if k in ('youtrack', '_attribute_types'):
                continue
            _repr += to_str(k) + ' = ' + to_str(v) + '\n'
        return _repr

    def __iter__(self):
        for item in self._data:
            if item == '_attribute_types':
                continue
            attr = self[item]
            if isinstance(attr, basestring) or isinstance(attr, list) \
                    or getattr(attr, '__iter__', False):
                yield item

    def get(self, key, default):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value


class YouTrackError(YouTrackObject):
    def to_xml(self):
        super().to_xml()

    def _update(self, xml):
        if xml.documentElement.tagName == 'error':
            self.error = self._text(xml.documentElement)
        else:
            self.error = xml.toxml()


class Issue(YouTrackObject):
    def __init__(self, xml=None, youtrack=None):
        super().__init__(xml, youtrack)
        if xml is not None:
            if len(xml.getElementsByTagName('links')) > 0:
                self.links = [Link(e, youtrack) for e in xml.getElementsByTagName('issueLink')]
            else:
                self.links = None
            if len(xml.getElementsByTagName('tag')) > 0:
                self.tags = [self._text(e) for e in xml.getElementsByTagName('tag')]
            else:
                self.tags = None
            if len(xml.getElementsByTagName('attachments')) > 0:
                self.attachments = [Attachment(e, youtrack) for e in xml.getElementsByTagName('fileUrl')]
            else:
                self.attachments = None
            for m in ['fixedVersion', 'affectsVersion']:
                self._normalize_multiple(m)
            if self.get('fixedInBuild', '') == 'Next build':
                self['fixedInBuild'] = None

    def to_xml(self):
        super().to_xml()

    def _normalize_multiple(self, name):
        if name in self._data:
            attr_value = self[name]
            if not isinstance(attr_value, list):
                if attr_value is None or not len(attr_value):
                    self._data.pop(name)
                else:
                    attr_value = to_str(attr_value)
                    self[name] = [value.strip() for value in attr_value.split(',')]

    def get_reporter(self):
        return self.youtrack.get_user(self['reporterName'])

    def has_assignee(self):
        return 'Assignee' in self._data

    def get_assignee(self):
        assignee = self.get('Assignee', None)
        if assignee is None:
            return None
        elif isinstance(assignee, (list, tuple)):
            return [self.youtrack.get_user(u) for u in assignee]
        return self.youtrack.get_user(assignee)

    def get_updater(self):
        return self.youtrack.get_user(self.get('updaterName', None))

    def has_voters(self):
        return 'voterName' in self._data

    def get_voters(self):
        voters = self.get('voterName', None)
        if voters:
            if isinstance(voters, list):
                voters = [self.youtrack.get_user(v) for v in voters]
            else:
                voters = [self.youtrack.get_user(voters)]
        return voters

    def get_comments(self):
        # TODO: do not make rest request if issue was inited with comments
        if self.get('comments', None) is None:
            self['comments'] = self.youtrack.get_comments(self['id'])
        return self['comments']

    def get_attachments(self):
        if self.get('attachments', None) is None:
            return self.youtrack.get_attachments(self['id'])
        else:
            return self['attachments']

    def delete_attachment(self, attachment):
        return self.youtrack.delete_attachment(self._data['id'], attachment.id)

    def get_links(self, outward_only=False):
        if self.get('links', None) is None:
            return self.youtrack.get_links(self['id'], outward_only)
        else:
            return [l for l in self['links'] if l.source == self['id'] or not outward_only]

    @property
    def events(self):
        return self.youtrack.get_events(self['id'])

    @property
    def custom_fields(self):
        cf = []
        for attr_name, attr_type in self._attribute_types.items():
            if attr_type in ('CustomFieldValue', 'MultiUserField'):
                cf.append(self[attr_name])
        return cf


class Comment(YouTrackObject):
    def __init__(self, xml=None, youtrack=None):
        self.author = ''
        super().__init__(xml, youtrack)
        if not hasattr(self, 'text'):
            self.text = ''

    def to_xml(self):
        super().to_xml()

    def get_author(self):
        return self.youtrack.get_user(self.author)


class IssueChange(YouTrackObject):
    def __init__(self, xml=None, youtrack=None):
        self.fields = []
        self.updated = 0
        self.updater_name = None
        self.comments = []
        super().__init__(xml, youtrack)

    def to_xml(self):
        super().to_xml()

    def _update(self, xml):
        if xml is None:
            return
        if isinstance(xml, Document):
            xml = xml.documentElement

        for field in xml.getElementsByTagName('field'):
            name = field.getAttribute('name')
            if name == 'updated':
                self.updated = int(self._text(field.getElementsByTagName('value')[0]))
            elif name == 'updaterName':
                self.updater_name = self._text(field.getElementsByTagName('value')[0])
            elif name == 'links':
                pass
            else:
                self.fields.append(ChangeField(field, self.youtrack))

        for comment in xml.getElementsByTagName('comment'):
            self.comments.append(comment.getAttribute('text'))


class ChangeField(YouTrackObject):
    def __init__(self, xml=None, youtrack=None):
        self.name = None
        self.old_value = []
        self.new_value = []
        super().__init__(xml, youtrack)

    def to_xml(self):
        super().to_xml()

    def _update(self, xml):
        self.name = xml.getAttribute('name')
        old_value = xml.getElementsByTagName('oldValue')
        for value in old_value:
            self.old_value.append(self._text(value))
        new_value = xml.getElementsByTagName('newValue')
        for value in new_value:
            self.new_value.append(self._text(value))


class Link(YouTrackObject):
    type_name = ''
    source = ''
    target = ''

    def to_xml(self):
        super().to_xml()

    def __hash__(self):
        return hash((self.type_name, self.source, self.target))

    def __eq__(self, other):
        return isinstance(other, Link) and \
               self.type_name == other.type_name and self.source == other.source and self.target == other.target

    def __ne__(self, other):
        return not self.__eq__(other)


class Attachment(YouTrackObject):
    def __init__(self, xml=None, youtrack=None):
        self.author_login = ''
        super().__init__(xml, youtrack)
        # Workaround for JT-18936
        self['url'] = re.sub(r'^.*?(?=/_persistent)', '', self['url'])

    def to_xml(self):
        super().to_xml()

    def get_content(self):
        return self.youtrack.get_attachment_content(self['url'])

    def get_author(self):
        if self.author_login == '<no user>':
            return None
        return self.youtrack.get_user(self.author_login)


class User(YouTrackObject):
    def __init__(self, xml=None, youtrack=None):
        self.login = ''
        super().__init__(xml, youtrack)
        self.get_groups = lambda: []

    def to_xml(self):
        super().to_xml()

    def __hash__(self):
        return hash(self.login)

    def __cmp__(self, other):
        if isinstance(other, User):
            return cmp(self.login, other.login)
        else:
            return cmp(self.login, other)


class Group(YouTrackObject):
    def __init__(self, xml=None, youtrack=None):
        self.name = ''
        super().__init__(xml, youtrack)

    def to_xml(self):
        super().to_xml()


class Role(YouTrackObject):
    def to_xml(self):
        super().to_xml()


class UserRole(YouTrackObject):
    def __init__(self, xml=None, youtrack=None):
        self.name = ''
        self.projects = []
        super().__init__(xml, youtrack)

    def _update(self, xml):
        if xml is None:
            return
        if isinstance(xml, Document):
            xml = xml.documentElement

        self.name = xml.getAttribute("name")
        projects = xml.getElementsByTagName("projectRef")
        self.projects = [p.getAttribute("id") for p in projects] if projects is not None else []

    def to_xml(self):
        result = '<userRole name="%s">' % self.name.encode('utf-8')
        if len(self.projects):
            result += '<projects>'
            result += "".join(
                '<projectRef id="%s" url="dirty_hack"/>' % project.encode('utf-8') for project in self.projects)
            result += '</projects>'
        else:
            result += '<projects/>'
        result += '</userRole>'
        return result


class Permission(YouTrackObject):
    def to_xml(self):
        pass


class Project(YouTrackObject):
    def __init__(self, xml=None, youtrack=None):
        super().__init__(xml, youtrack)
        self[id] = ''
        if 'description' not in self._data:
            self['description'] = ''

    def to_xml(self):
        super().to_xml()

    def get_subsystems(self):
        return self.youtrack.get_subsystems(self['id'])

    def create_subsystem(self, name, is_default, default_assignee_login):
        return self.youtrack.create_subsystem(self['id'], name, is_default, default_assignee_login)


class Subsystem(YouTrackObject):
    def to_xml(self):
        super().to_xml()


class Version(YouTrackObject):
    def __init__(self, xml=None, youtrack=None):
        super().__init__(xml, youtrack)
        if 'description' not in self._data:
            self['description'] = ''

        if 'releaseDate' not in self._data:
            self['releaseDate'] = None

    def to_xml(self):
        super().to_xml()


class IssueLinkType(YouTrackObject):
    def to_xml(self):
        super().to_xml()


class WorkItem(YouTrackObject):
    def to_xml(self):
        super().to_xml()

    def _update(self, xml):
        if xml is None:
            return
        if isinstance(xml, Document):
            xml = xml.documentElement

        self['url'] = xml.getAttribute('url')
        for e in xml.childNodes:
            if e.tagName == 'author':
                self['authorLogin'] = e.getAttribute('login')
            elif e.tagName.lower() == 'worktype':
                self['worktype'] = self._text(e.getElementsByTagName('name')[0])
            else:
                self[e.tagName] = self._text(e)


class CustomField(YouTrackObject):
    def to_xml(self):
        super().to_xml()


class ProjectCustomField(YouTrackObject):
    def to_xml(self):
        super().to_xml()

    def _update_from_children(self, el):
        self.params = {}
        for c in el.getElementsByTagName('param'):
            name = c.getAttribute('name')
            value = c.getAttribute('value')
            self[name] = value
            self.params[name] = value


class UserBundle(YouTrackObject):
    def __init__(self, xml=None, youtrack=None):
        self.users = []
        self.groups = []
        super().__init__(xml, youtrack)

    def _update(self, xml):
        if xml is None:
            return
        if isinstance(xml, Document):
            xml = xml.documentElement

        self.name = xml.getAttribute("name")
        users = xml.getElementsByTagName("user")
        if users is not None:
            self.users = [self.youtrack.getUser(v.getAttribute("login")) for v in users]
        else:
            self.users = []
        groups = xml.getElementsByTagName("userGroup")
        if groups is not None:
            self.groups = [self.youtrack.getGroup(v.getAttribute("name")) for v in groups]
        else:
            self.groups = []

    def to_xml(self):
        result = '<userBundle name="%s">' % self.name.encode('utf-8')
        result += "".join(
            '<userGroup name="%s" url="dirty_hack"></userGroup>' % group.name.encode('utf-8') for group in self.groups)
        result += "".join(
            '<user login="%s" url="yet_another_dirty_hack"></user>' % user.login.encode('utf-8') for user in self.users)
        result += '</userBundle>'
        return result

    @staticmethod
    def get_field_type():
        return "user"

    def get_all_users(self):
        all_users = self.users
        for group in self.groups:
            # returns objects containing only login and url info
            group_users = self.youtrack.get_users({'group': group.name.encode('utf-8')})
            for user in group_users:
                # re-request credentials separately for each user to get more details
                try:
                    refined_user = self.youtrack.get_user(user.login)
                    all_users.append(refined_user)
                except YouTrackException as e:
                    print("Error on extracting user info for [{}] user won't be imported".format(str(user.login)))
                    print(e)
        return list(set(all_users))


class Bundle(YouTrackObject):
    def __init__(self, element_tag_name, bundle_tag_name, xml=None, youtrack=None):
        self._element_tag_name = element_tag_name
        self._bundle_tag_name = bundle_tag_name
        self.values = []
        super().__init__(xml, youtrack)

    def _update(self, xml):
        if xml is None:
            return
        if isinstance(xml, Document):
            xml = xml.documentElement

        self.name = xml.getAttribute("name")
        values = xml.getElementsByTagName(self._element_tag_name)
        if values is not None:
            self.values = [self._create_element(value) for value in values]
        else:
            self.values = []

    def to_xml(self):
        result = '<%s name="%s">' % (self._bundle_tag_name, escape(self.name))
        result += ''.join(v.to_xml() for v in self.values)
        result += '</%s>' % self._bundle_tag_name
        return result

    def get_field_type(self):
        return self._element_tag_name

    def create_element(self, name):
        element = self._create_element(None)
        element.name = name
        return element

    def _create_element(self, xml):
        return {}


class BundleElement(YouTrackObject):
    def __init__(self, element_tag_name, xml=None, youtrack=None):
        self.element_name = element_tag_name
        super().__init__(xml, youtrack)

    def to_xml(self):
        result = '<' + self.element_name
        for elem in self:
            if elem in ("name", "element_name"):
                continue
            value = self[elem]
            if value is None or not len(value):
                continue
            if isinstance(elem, str):
                elem = elem
            if isinstance(value, str):
                value = value
            result += ' %s="%s"' % (escape(elem), escape(str(value)))
        result += ">%s</%s>" % (escape(self.name), self.element_name)
        return result

    def _update(self, xml):
        if xml is None:
            return
        if isinstance(xml, Document):
            xml = xml.documentElement

        self.name = [e.data for e in xml.childNodes if e.nodeType == Node.TEXT_NODE][0]
        self.description = xml.getAttribute('description')
        self.colorIndex = xml.getAttribute('colorIndex')
        self._update_specific_attributes(xml)

    def _update_specific_attributes(self, xml):
        pass


class EnumBundle(Bundle):
    def __init__(self, xml=None, youtrack=None):
        super().__init__("value", "enumeration", xml, youtrack)

    def _create_element(self, xml):
        return EnumField(xml, self.youtrack)

    def get_field_type(self):
        return "enum"


class EnumField(BundleElement):
    def __init__(self, xml=None, youtrack=None):
        super().__init__("value", xml, youtrack)


class BuildBundle(Bundle):
    def __init__(self, xml=None, youtrack=None):
        super().__init__("build", "buildBundle", xml, youtrack)

    def _create_element(self, xml):
        return Build(xml, self.youtrack)


class Build(BundleElement):
    def __init__(self, xml=None, youtrack=None):
        super().__init__("build", xml, youtrack)

    def _update_specific_attributes(self, xml):
        self.assembleDate = xml.getAttribute('assembleName')


class OwnedFieldBundle(Bundle):
    def __init__(self, xml=None, youtrack=None):
        super().__init__("ownedField", "ownedFieldBundle", xml, youtrack)

    def _create_element(self, xml):
        return OwnedField(xml, self.youtrack)


class OwnedField(BundleElement):
    def __init__(self, xml=None, youtrack=None):
        super().__init__("ownedField", xml, youtrack)

    def _update_specific_attributes(self, xml):
        owner = xml.getAttribute("owner")
        if owner != '<no user>':
            self.owner = owner
        else:
            self.owner = None


class StateBundle(Bundle):
    def __init__(self, xml=None, youtrack=None):
        super().__init__("state", "stateBundle", xml, youtrack)

    def _create_element(self, xml):
        return StateField(xml, self.youtrack)


class StateField(BundleElement):
    def __init__(self, xml=None, youtrack=None):
        super().__init__("state", xml, youtrack)

    def _update_specific_attributes(self, xml):
        self.is_resolved = xml.getAttribute("isResolved")


class VersionBundle(Bundle):
    def __init__(self, xml=None, youtrack=None):
        super().__init__("version", "versions", xml, youtrack)

    def _create_element(self, xml):
        return VersionField(xml, self.youtrack)


class VersionField(BundleElement):
    def __init__(self, xml=None, youtrack=None):
        super().__init__("version", xml, youtrack)

    def _update_specific_attributes(self, xml):
        self.releaseDate = xml.getAttribute("releaseDate")
        self.released = xml.getAttribute("released").lower() == "true"
        self.archived = xml.getAttribute("archived").lower() == "true"


class IntelliSense(YouTrackObject):
    def __init__(self, xml=None, youtrack=None):
        self.suggestions = []
        self.highlights = []
        self.queries = []
        super().__init__(xml, youtrack)

    def to_xml(self):
        super().to_xml()

    def _update(self, xml):
        if not xml:
            return
        if isinstance(xml, Document):
            xml = xml.documentElement
        for c in xml.childNodes:
            if c.tagName in ('suggest', 'recent'):
                for item in c.getElementsByTagName('item'):
                    suggest = {}
                    for i in item.childNodes:
                        if i.tagName in ('completion', 'match'):
                            suggest[i.tagName] = {
                                'start': int(i.getAttribute('start')),
                                'end': int(i.getAttribute('end'))}
                        else:
                            if i.tagName == 'caret':
                                suggest[i.tagName] = int(self._text(i))
                            else:
                                suggest[i.tagName] = self._text(i)
                    if 'option' not in suggest:
                        continue
                    if c.tagName == 'suggest':
                        self.suggestions.append(suggest)
                    else:
                        self.queries.append(suggest)
            elif c.tagName == 'highlight':
                for item in c.getElementsByTagName('range'):
                    rng = {}
                    for i in item.childNodes:
                        if i.tagName in ('start', 'end'):
                            rng[i.tagName] = int(self._text(i))
                        else:
                            rng[i.tagName] = self._text(i)
                    self.highlights.append(rng)


class GlobalTimeTrackingSettings(YouTrackObject):
    def to_xml(self):
        super().to_xml()

    def _update(self, xml):
        if not xml:
            return
        if isinstance(xml, Document):
            xml = xml.documentElement
        for e in xml.childNodes:
            self[e.tagName] = self._text(e)


class ProjectTimeTrackingSettings(YouTrackObject):
    def to_xml(self):
        super().to_xml()

    def _update(self, xml):
        if not xml:
            return
        if isinstance(xml, Document):
            xml = xml.documentElement
        self['Enabled'] = xml.getAttribute('enabled').lower() == 'true'
        self['EstimateField'] = None
        self['TimeSpentField'] = None
        for e in xml.childNodes:
            if e.tagName.lower() == 'estimation':
                self['EstimateField'] = e.getAttribute('name')
            elif e.tagName.lower() == 'spenttime':
                self['TimeSpentField'] = e.getAttribute('name')
