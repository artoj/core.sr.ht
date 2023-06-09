#!/usr/bin/env python3
from setuptools import setup
import subprocess
import glob
import os
import sys

ver = os.environ.get("PKGVER") or subprocess.run(['git', 'describe', '--tags'],
      stdout=subprocess.PIPE).stdout.decode().strip()

setup(
  name = 'srht',
  packages = [
      'srht',
      'srht.alembic',
      'srht.alembic.versions',
      'srht.graphql',
      'srht.oauth',
      'srht.webhook',
  ],
  version = ver,
  description = 'sr.ht core modules',
  author = 'Drew DeVault',
  author_email = 'sir@cmpwn.com',
  url = 'https://git.sr.ht/~sircmpwn/core.sr.ht',
  install_requires = [
      'flask',
      'humanize',
      'sqlalchemy',
      'sqlalchemy-utils',
      'psycopg2',
      'markdown',
      'mistletoe',
      'bleach',
      'requests',
      'BeautifulSoup4',
      'pgpy',
      'pygments',
      'cryptography',
      'prometheus_client',
      'alembic',
      'redis',
      'celery',
  ],
  license = 'BSD-3-Clause',
  package_data={
      'srht': [
          'Makefile',
          'minify-css.js',
          'package.json',
          'templates/*.html',
          'scss/*.scss',
          'scss/*.css',
          'scss/bootstrap/LICENSE',
          'static/*'
      ] + [f[5:] for f in glob.glob('srht/node_modules/**', recursive=True)] \
        + [f[5:] for f in glob.glob('srht/static/**', recursive=True)] \
        + [f[5:] for f in glob.glob('srht/scss/bootstrap/scss/**/*.scss', recursive=True)]
  },
  scripts = [
      'srht-update-profiles',
      'srht-migrate',
      'srht-keygen',
  ]
)
