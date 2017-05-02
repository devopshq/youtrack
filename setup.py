#!/usr/bin/env python

import os
from setuptools import setup

__version__ = '0.2'  # identify main version of dohq-youtrack

if 'TRAVIS_BUILD_NUMBER' in os.environ and 'TRAVIS_BRANCH' in os.environ:
    print("This is TRAVIS-CI build")
    print("TRAVIS_BUILD_NUMBER = {}".format(os.environ['TRAVIS_BUILD_NUMBER']))
    print("TRAVIS_BRANCH = {}".format(os.environ['TRAVIS_BRANCH']))

    __version__ += '.{}{}'.format(
        '' if 'release' in os.environ['TRAVIS_BRANCH'] or os.environ['TRAVIS_BRANCH'] == 'master' else 'dev',
        os.environ['TRAVIS_BUILD_NUMBER'],
    )

else:
    print("This is local build")
    __version__ += '.localbuild'  # set version as major.minor.localbuild if local build: python setup.py install

print("dohq-youtrack build version = {}".format(__version__))


with open('README.md') as readme:
    long_description = readme.read()

setup(
    name='dohq-youtrack',
    version=__version__,
    license='MIT License',
    description='YouTrack Python 3 Client Library',
    long_description=long_description,
    author='Alexander Kovalev',
    author_email='ak@alkov.pro',
    url='https://devopshq.github.io/youtrack/',
    download_url='https://github.com/devopshq/youtrack',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.1',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Software Development :: Libraries',
    ],
    keywords=[
        'development',
        'dependency',
        'requirements',
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
    ],
    zip_safe=True,
    package_data={
        '': [
            './LICENSE',
            './README.md',
        ],
    },
)
