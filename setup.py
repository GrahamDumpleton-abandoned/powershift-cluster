import sys
import os

from setuptools import setup

long_description = open('README.rst').read()

classifiers = [
    'Development Status :: 4 - Beta',
    'License :: OSI Approved :: BSD License',
    'Programming Language :: Python :: 2',
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.3',
    'Programming Language :: Python :: 3.4',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
]

setup_kwargs = dict(
    name='powershift-cluster',
    version='2.0.0',
    description='PowerShift command plugin for creating OpenShift clusters.',
    long_description=long_description,
    url='https://github.com/getwarped/powershift-cluster',
    author='Graham Dumpleton',
    author_email='Graham.Dumpleton@gmail.com',
    license='BSD',
    classifiers=classifiers,
    keywords='openshift kubernetes',
    packages=['powershift', 'powershift.cluster', 'powershift.cluster.scripts'],
    package_dir={'powershift': 'src/powershift'},
    install_requires=['passlib'],
    extras_require={'cli': ['powershift-cli>=1.1.8']},
    entry_points = {'powershift_cli_plugins': ['cluster = powershift.cluster']},
    package_data = {'powershift.cluster.scripts': ['enable-labels.sh',
        'enable-htpasswd.sh']},
)

setup(**setup_kwargs)
