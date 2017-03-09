#!/usr/bin/env python3
'''
Create a skeleton post in Markdown format with basic metadata.
'''
import argparse
import datetime
import os
import titlecase
import slugify


ROOT_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                         '..',
                                         'content'))


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('title', type=str, nargs=1,
                    help='post title. It is used also for slug and filename.')
parser.add_argument('--dir', '-d', type=str,
                    help='content directory. The post will be created there.',
                    default=ROOT_DIR)
args = parser.parse_args()
raw_title = args.title[0]

if not os.path.isdir(args.dir):
    raise IOError(f'{args.dir} is not a directory! Aborting.')

post_slug = slugify.slugify(raw_title)
post_title = titlecase.titlecase(raw_title)

today = datetime.datetime.today().date().isoformat()
postpath = os.path.join(args.dir, f'{today}_{post_slug}.md')
if os.path.exists(postpath):
    raise IOError(f'{postpath} already exists! Aborting.')

with open(postpath, 'w') as f:
    f.write(f'''\
Title: {post_title}
Date: {today}
Tags: Python, Pelican
Slug: {post_slug}

Text here

''')
