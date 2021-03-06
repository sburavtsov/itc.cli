import os
import sys
from setuptools import setup, find_packages

setup(name = "itc.cli",
      version = "0.2.0",
      author = 'Pavel Mazurin',
      author_email = 'me@kovpas.ru',
      description = 'iTunesConnect command line interface.',
      url = 'https://github.com/kovpas/itc.cli',
      packages = find_packages(),
      package_data = {'itc.util': ['languages.json']},
      install_requires = ['requests', 'lxml', 'html5lib'],
      scripts = ['itc/bin/itc'],
      include_package_data = True,
      zip_safe = False,
)

