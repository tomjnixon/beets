# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2019, Guilherme Danno.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""Update library's tags using MusicBrainz.
"""
from __future__ import division, absolute_import, print_function

from beets.plugins import BeetsPlugin
from beets import ui, util
from beets.autotag.mb import musicbrainzngs
from collections import defaultdict, namedtuple

import re

MBID_REGEX = r"(\d|\w){8}-(\d|\w){4}-(\d|\w){4}-(\d|\w){4}-(\d|\w){12}"
ORDER_ATTR_ID = 'a59c5830-5ec7-38fe-9a21-c7ea54f6650a'

SeriesType = namedtuple('SeriesType', [
    'name',
    'relation',
    'relation_list',
    'get_field'
])

TYPES = [
    SeriesType(
        name='Release series',
        relation='release-rels',
        relation_list='release-relation-list',
        get_field=lambda a: a.mb_albumid
    ),
    SeriesType(
        name='Release group series',
        relation='release-group-rels',
        relation_list='release_group-relation-list',
        get_field=lambda a: a.mb_releasegroupid
    ),
]

SERIES_RELS = [t.relation for t in TYPES]


def apply_item_changes(lib, item, move, pretend, write):
    """Store, move and write the item according to the arguments.
    """
    if not pretend:
        # Move the item if it's in the library.
        if move and lib.directory in util.ancestry(item.path):
            item.move(with_album=False)

        if write:
            item.try_write()
        item.store()


def get_series_type(name):
    for t in TYPES:
        if t.name == name:
            return t
    return None


def get_attribute(item, attr):
    try:
        return [x['value'] for x in item['attributes']
                if x['type-id'] == attr][0]
    except KeyError:
        return None


def get_series(mb_series_id):

    series = musicbrainzngs.get_series_by_id(mb_series_id, SERIES_RELS)
    series_type = get_series_type(series['series']['type'])

    if not series_type:
        return

    data = {
        'id': series['series']['id'],
        'name': series['series']['name'],
        'type': series_type,
        'items': defaultdict(dict),
    }

    for item in series['series'][data['type'].relation_list]:
        data['items'][item['target']] = {
            'order': get_attribute(item, ORDER_ATTR_ID),
            'name': data['name'],
            'id': data['id'],
        }

    return data


class MbSeriesPlugin(BeetsPlugin):

    mapping = {
        'id': 'id',
        'name': 'name',
        'volume': 'order',
    }

    def __init__(self):
        super(MbSeriesPlugin, self).__init__()

        self.config.add({
            'auto': True,
            'fields': {
                'id': {
                    'field_name': 'mb_seriesid',
                    'write': True,
                },
                'name': {
                    'field_name': 'series',
                    'write': True,
                },
                'volume': {
                    'field_name': 'volume',
                    'write': True,
                },
            }
        })

    def commands(self):
        def func(lib, opts, args):
            """
            Command handler for the series function.
            """
            move = ui.should_move(opts.move)
            pretend = opts.pretend
            write = ui.should_write(opts.write)
            query = ui.decargs(args)
            series_id = opts.id

            self.albums(lib, query, series_id, move, pretend, write)
        cmd = ui.Subcommand('series', help=u'Fetch series from MusicBrainz')
        cmd.parser.add_option(
            u'-S', u'--id', action='store',
            help=u'Series id')
        cmd.parser.add_option(
            u'-p', u'--pretend', action='store_true',
            help=u'show all changes but do nothing')
        cmd.parser.add_option(
            u'-m', u'--move', action='store_true', dest='move',
            help=u"move files in the library directory")
        cmd.parser.add_option(
            u'-M', u'--nomove', action='store_false', dest='move',
            help=u"don't move files in library")
        cmd.parser.add_option(
            u'-W', u'--nowrite', action='store_false',
            default=None, dest='write',
            help=u"don't write updated metadata to files")
        cmd.func = func
        return [cmd]

    def is_mb_release(self, a):
        if not a.mb_albumid:
            self._log.info(u'Skipping album with no mb_albumid: {0}',
                           format(a))
            return False

        if not re.match(MBID_REGEX, a.mb_albumid):
            self._log.info(u'Skipping album with invalid mb_albumid: {0}',
                           format(a))
            return False

        return True

    def albums(self, lib, query, series_id, move, pretend, write):
        """Retrieve and apply info from the autotagger for albums matched by
        query and their items.
        """
        series = get_series(series_id)

        if not series:
            return

        fields = []
        for key, field in self.config['fields'].items():
            if field['write']:
                field['attr'] = self.mapping[key]
                fields.append(field)

        for a in lib.albums(query):
            if not self.is_mb_release(a):
                continue

            mbid = series['type'].get_field(a)
            if not series['items'][mbid]:
                continue

            item = series['items'][mbid]

            for f in fields:
                if item[f['attr'].get()]:
                    a[f['field_name'].get()] = item[f['attr'].get()]

            ui.show_model_changes(a)
            apply_item_changes(lib, a, move, pretend, write)
