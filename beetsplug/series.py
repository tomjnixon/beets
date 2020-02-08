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
from collections import defaultdict

import re
import musicbrainzngs

musicbrainzngs.set_useragent('beets plugin', '0.0.1', '')

MBID_REGEX = r"(\d|\w){8}-(\d|\w){4}-(\d|\w){4}-(\d|\w){4}-(\d|\w){12}"
ORDER_ATTR_ID = 'a59c5830-5ec7-38fe-9a21-c7ea54f6650a'

RELEASE_SERIES = 'Release series'
RELEASE_GROUP_SERIES = 'Release group series'

SERIES_KEY = {
    RELEASE_SERIES: 'release-relation-list',
    RELEASE_GROUP_SERIES: 'release_group-relation-list',
}


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


def get_field(series, a):
    if series['type'] == RELEASE_SERIES:
        return a.mb_albumid
    if series['type'] == RELEASE_GROUP_SERIES:
        return a.mb_releasegroupid


def get_order(item):
    try:
        return [x['value'] for x in item['attributes']
                if x['type-id'] == ORDER_ATTR_ID][0]
    except KeyError:
        return None


def get_series(mb_series_id):

    rels = ['release-rels', 'release-group-rels']
    series = musicbrainzngs.get_series_by_id(mb_series_id, rels)
    data = {
        'id': series['series']['id'],
        'name': series['series']['name'],
        'type': series['series']['type'],
        'items': defaultdict(dict),
    }

    for item in series['series'][SERIES_KEY[data['type']]]:
        data['items'][item['target']] = {
            'order': get_order(item),
            'name': data['name'],
            'id': data['id'],
        }

    return data


class MbSeriesPlugin(BeetsPlugin):
    def __init__(self):
        super(MbSeriesPlugin, self).__init__()

        self.config.add({
            'auto': True,
            'fields': {
                'id': {
                    'field_name': 'mb_seriesid',
                    'write': True,
                    'attr': 'id',
                },
                'name': {
                    'field_name': 'series',
                    'write': True,
                    'attr': 'name',
                },
                'volume': {
                    'field_name': 'volume',
                    'write': True,
                    'attr': 'order',
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

        for a in lib.albums(query):
            if not self.is_mb_release(a):
                continue

            mbid = get_field(series, a)
            if not series['items'][mbid]:
                continue

            item = series['items'][mbid]

            for f in [f for f in self.config['fields'].values() if f['write']]:
                if item[f['attr'].get()]:
                    a[f['field_name'].get()] = item[f['attr'].get()]

            ui.show_model_changes(a)
            apply_item_changes(lib, a, move, pretend, write)
