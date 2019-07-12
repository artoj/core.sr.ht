#!/usr/bin/env python3
from setuptools import setup
import subprocess
import glob
import os
import sys

if subprocess.call(["npm", "i"], cwd="srht") != 0:
    sys.exit(1)

ver = os.environ.get("PKGVER") or subprocess.run(['git', 'describe', '--tags'],
      stdout=subprocess.PIPE).stdout.decode().strip()

setup(
  name = 'srht',
  packages = [
      'srht',
      'srht.alembic',
      'srht.alembic.versions',
      'srht.oauth',
      'srht.webhook',
  ],
  version = ver,
  description = 'sr.ht core modules',
  author = 'Drew DeVault',
  author_email = 'sir@cmpwn.com',
  url = 'https://git.sr.ht/~sircmpwn/srht',
  install_requires = [
      'flask',
      'flask-login',
      'humanize',
      'sqlalchemy',
      'sqlalchemy-utils',
      'psycopg2',
      'markdown',
      'bleach',
      'requests',
      'BeautifulSoup4',
      'pgpy',
      'misaka',
      'pygments',
      'cryptography',
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
      'srht-webhook-keygen',
  ]
)
