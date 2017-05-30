#!/usr/bin/env python

import os
from setuptools import setup
from youtrack import config

build_number = os.getenv('TRAVIS_BUILD_NUMBER', '')
branch = os.getenv('TRAVIS_BRANCH', '')
travis = any((build_number, branch,))
version = config.__version__.split('.')
develop_status = '4 - Beta'

if travis:
    version = version[0:3]
    if branch == 'master':
        develop_status = '5 - Production/Stable'
        version.append(build_number)
    else:
        version.append('{}{}'.format('dev' if branch == 'develop' else branch, build_number))
else:
    if len(version) < 4:
        version.append('local')

version = '.'.join(version)
if travis:
    with open('youtrack/config.py', 'w', encoding="utf-8") as f:
        f.write("__version__ = '{}'".format(version))

try:
    import pypandoc

    print("Converting README...")
    long_description = pypandoc.convert('README.md', 'rst')
    if branch:
        long_description = long_description.replace('youtrack.svg?branch=master',
                                                    'youtrack.svg?branch={}'.format(branch))
    links = min((long_description.find('\n.. |build'),
                 long_description.find('\n.. |codacy'),
                 long_description.find('\n.. |pypi'),
                 long_description.find('\n.. |license'),
                 ))
    if links >= 0:
        long_description = '{}\n{}'.format(
            long_description[:links],
            long_description[links:].replace('\n', '').replace('.. |', '\n.. |'),
        )  # .replace('\r\n', '\n')


except (IOError, ImportError, OSError):
    print("Pandoc not found. Long_description conversion failure.")
    with open('README.md', encoding="utf-8") as f:
        long_description = f.read()
else:
    print("Saving README.rst...")
    try:
        if len(long_description) > 0:
            with open('README.rst', 'w', encoding="utf-8") as f:
                f.write(long_description)
            if travis:
                os.remove('README.md')
    except Exception as e:
        print("  failed!")

setup(
    name='dohq-youtrack',
    version=version,
    license='MIT License',
    description='YouTrack Python 3 Client Library',
    # long_description=open('README.md').read(),
    author='Alexander Kovalev',
    author_email='ak@alkov.pro',
    url='https://devopshq.github.io/youtrack/',
    download_url='https://github.com/devopshq/youtrack',
    classifiers=[
        'Development Status :: {}'.format(develop_status),
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.1',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    keywords=[
        'tracker',
        'youtrack',
    ],
    packages=[
        'youtrack',
    ],
    install_requires=[
        'httplib2',
    ],
    setup_requires=[
    ],
    tests_require=[
        'pytest',
        'PyHamcrest',
    ],
    zip_safe=True,
    package_data={
        '': [
            '../LICENSE',
            # '../README.*',
        ],
    },
)
