#!/usr/bin/env python

from setuptools import setup
from youtrack import __version__

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
    url='https://github.com/devopshq/youtrack.git',
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
    download_url='https://github.com/devopshq/youtrack',
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
        # 'pytest-runner',
        'wheel',
    ],
    # tests_require=[
        # 'pytest',
    # ],
    zip_safe=False,
    package_data={
        '': [
            '../LICENSE',
        ],
    },
)
