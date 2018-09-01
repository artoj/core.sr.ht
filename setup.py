#!/usr/bin/env python3
from setuptools import setup
import subprocess
import glob
import os

subprocess.call(["npm", "i"], cwd="srht")

ver = os.environ.get("PKGVER") or subprocess.run(['git', 'describe', '--tags'],
      stdout=subprocess.PIPE).stdout.decode().strip()

setup(
  name = 'srht',
  packages = ['srht'],
  version = ver,
  description = 'sr.ht core modules',
  author = 'Drew DeVault',
  author_email = 'sir@cmpwn.com',
  url = 'https://git.sr.ht/~sircmpwn/srht',
  install_requires = [
      'flask',
      'humanize',
      'sqlalchemy',
      'sqlalchemy-utils',
      'psycopg2-binary',
      'markdown',
      'bleach',
      'requests',
      'BeautifulSoup4',
  ],
  license = 'AGPL-3.0',
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
        + [f[5:] for f in glob.glob('srht/scss/bootstrap/scss/**/*.scss', recursive=True)]
  }
)
