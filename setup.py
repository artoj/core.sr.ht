#!/usr/bin/env python3
from distutils.core import setup
import subprocess
import glob
import os

if not os.path.exists("srht/node_modules"):
    subprocess.call(["npm", "i"], cwd="srht")

setup(
  name = 'srht',
  packages = ['srht'],
  version = subprocess.run(['git', 'describe', '--tags'],
      stdout=subprocess.PIPE).stdout.decode().strip(),
  description = 'sr.ht core modules',
  author = 'Drew DeVault',
  author_email = 'sir@cmpwn.com',
  url = 'https://git.sr.ht/~sircmpwn/srht',
  requires = ['flask', 'humanize', 'sqlalchemy', 'sqlalchemy-utils'],
  license = 'GPL-2.0',
  package_data={
      'srht': [
          'Makefile',
          'minify-css.js',
          'package.json',
          'templates/*.html',
          'scss/*.scss',
          'scss/bootstrap/LICENSE',
      ] + [f[5:] for f in glob.glob('srht/node_modules/**', recursive=True)] \
        + [f[5:] for f in glob.glob('srht/scss/bootstrap/scss/**/*.scss', recursive=True)]
  }
)
