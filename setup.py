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
    version='1.0.8',
    description='PowerShift command plugin for creating OpenShift clusters.',
    long_description=long_description,
    url='https://github.com/getwarped/powershift-cluster',
    author='Graham Dumpleton',
    author_email='Graham.Dumpleton@gmail.com',
    license='BSD',
    classifiers=classifiers,
    keywords='openshift kubernetes',
    packages=['powershift', 'powershift.cluster'],
    package_dir={'powershift': 'src/powershift'},
    install_requires=['powershift-cli>=1.0.1'],
    entry_points = {'powershift_cli_plugins': ['cluster = powershift.cluster']},
)

setup(**setup_kwargs)
