import sys
import os

from setuptools import setup

long_description = open('README.rst').read()

classifiers = [
    'Development Status :: 4 - Beta',
    'License :: OSI Approved :: BSD License',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.5',
]

setup_kwargs = dict(
    name='powershift-cluster',
    version='1.0.3',
    description='PowerShift command plugin for creating OpenShift clusters.',
    long_description=long_description,
    url='https://github.com/getwarped/powershift-cli-cluster',
    author='Graham Dumpleton',
    author_email='Graham.Dumpleton@gmail.com',
    license='BSD',
    classifiers=classifiers,
    keywords='openshift kubernetes',
    packages=['powershift', 'powershift.cluster'],
    package_dir={'powershift': 'src/powershift'},
    install_requires=['powershift>=1.3.7'],
    entry_points = {'powershift_cli_plugins': ['cluster = powershift.cluster']},
)

setup(**setup_kwargs)
