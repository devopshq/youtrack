YouTrack Python 3 Client Library
================================

[![build](https://travis-ci.org/devopshq/youtrack.svg?branch=master)](https://travis-ci.org/devopshq/youtrack) [![pypi](https://img.shields.io/pypi/v/dohq-youtrack.svg)](https://pypi.python.org/pypi/dohq-youtrack) [![codacy](https://api.codacy.com/project/badge/Grade/30f18d23f1a5481cb3c5ca6570458ad7)](https://www.codacy.com/app/tim55667757/youtrack/dashboard) [![license](https://img.shields.io/pypi/l/dohq-youtrack.svg)](https://github.com/devopshq/youtrack/blob/master/LICENSE)

This document describes Python 3 library that wraps YouTrack REST API.

Compatibility

Current implementation of the YouTrack Python 3 Client Library and scripts is compatible with YouTrack 3.x and higher REST API and Python 3.

Installation
------------

To install YouTrack Python 3 Client Library:

```
  pip install dohq-youtrack
```

Authenticating
--------------

```
  from youtrack.connection import Connection

  connection = Connection('http://teamsys.intellij.net', 'xxx', 'xxx')
```

Get Issues
----------

```
  # get one issue

  connection.get_issue('SB-1')
```

```
  # get first 10 issues in project JT for query 'for: me #unresolved'

  connection.get_issues('JT', 'for: me #unresolved', 0, 10)
```

Create Issue
------------

```
  connection.create_issue('SB', 'resttest', 'Test issue', 'Test description', '2', 'Bug', 'First', 'Open', '', '', '')
```

Other Methods
-------------

See method of class Connection in [youtrack/connection.py](https://github.com/devopshq/youtrack/blob/master/youtrack/connection.py)
