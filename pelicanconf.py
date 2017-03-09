#!/usr/bin/env python
# -*- coding: utf-8 -*- #
from __future__ import unicode_literals
import os


AUTHOR = 'Francesco'
SITENAME = 'Python Computing'
SITETITLE = 'Python Computing'
SITESUBTITLE = 'Distributed Computing for the Rest of Us'
SITELOGO = 'images/profile.jpg'
SITEURL = ''

PATH = 'content'
STATIC_PATHS = ['images']

TIMEZONE = 'Europe/Paris'

DEFAULT_LANG = 'en'

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

ROBOTS = 'index, follow'

CC_LICENSE = {
    'name': 'Creative Commons Attribution-ShareAlike',
    'version': '4.0',
    'slug': 'by-sa'
}

# Blogroll
LINKS = (('Checkout my book!', 'https://distributedcomputingwithpython.com/'),)

# Social widget
SOCIAL = (('You can add links in your config file', '#'),
          ('Another social link', '#'),)

DEFAULT_PAGINATION = 10
SUMMARY_MAX_LENGTH = 0

# Uncomment following line if you want document-relative URLs when developing
# RELATIVE_URLS = True

# Customization
ROOT_DIR = os.path.join(os.path.expanduser('~'), 't')
# THEMES_DIR = os.path.join(ROOT_DIR, 'pelican-themes')
THEME = 'Flex'
PLUGIN_PATHS = [os.path.join(ROOT_DIR, 'pelican-plugins')]
PLUGINS = ['assets', 'gzip_cache']

# Theme-specific
PYGMENTS_STYLE = 'monokai'
MAIN_MENU = True
MENUITEMS = (('Home', '/'),
             ('Archives', 'archives.html'),
             ('Categories','categories.html'),
             ('Tags', 'tags.html'))
