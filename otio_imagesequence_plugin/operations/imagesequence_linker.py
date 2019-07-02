# MIT License
#
# Copyright (c) 2019- Daniel Flehner Heen (Storm Studios)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


"""
This media linker requires OpenImageIO with python bindings to be available.
It uses OIIO to fetch TimeCode and FPS from source files.

Example usage:

OTIO_PLUGIN_MANIFEST_PATH=./otio_imagesequence_plugin/plugin_manifest.json \
otioview -m imagesequence_linker \
-M root=/net/projects/big_dump_of_source_files/ \
-M pattern='.*proxy-3k.*' \
-M ext=exr \
-a rate=23.976 \
my_efforts_V1.edl
"""


import os
import sys
import re
import time
import copy
import operator

import OpenImageIO as oiio
import opentimelineio as otio


# Load our custom schemadef
otio.schema.schemadef.from_name('imagesequence_reference')

# Check if we're using one of OTIO's console tools (bit of a hack..)
USE_FIRST = 'console' in sys.argv[0]


# Timer decorator used under development to measure time spent
def timeit(method):     # pragma: nocover
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()

        print ('\nfunc: %s, %2.6f sec' % (method.__name__, te - ts))
        return result
    return timed


def get_fps(buf):
    """Get frame rate from source ImageBuf

    :param buf: oiio.ImageBuf
    :return: `float` or `None`
    """

    spec = buf.spec()
    attrlut = dict(
        exr='FramesPerSecond',
        dpx='dpx:FrameRate'
    )

    _, ext = os.path.splitext(buf.name)
    attrname = attrlut.get(ext[1:].lower())

    if attrname:
        value = spec.getattribute(attrname)
        if isinstance(value, float):
            return round(value, 3)

        elif isinstance(value, tuple):
            return round(float(value[0]) / float(value[1]), 3)

        return value

    return None


def get_timecode_str(buf):
    """Get TimeCode from source ImageBuf

    :param buf: oiio.ImageBuf
    :return: `str` or `None`
    """

    spec = buf.spec()
    tc = spec.getattribute('timecode')

    if not tc and not spec.getattribute('oiio:Movie'):
        tc_bin = None
        for v in spec.extra_attribs:
            if v.name == "smpte:TimeCode":
                # OIIO 2.x
                if isinstance(v.value, tuple):
                    tc_bin, _ = v.value

                else:
                    # OIIO 1.8.x
                    tc_bin = v.value

                break

        if tc_bin is not None:
            bits = range(0, 32, 8)
            tc = ':'.join(
                [
                    '{0:02d}'.format(int(hex((tc_bin >> i) & 0xff)[2:]))
                    for i in bits[::-1]
                ]
            )

    return tc


class FileCache(object):
    """ Cache to look for new files and hold account of what it previously
     found along the way for faster lookup later on.

    """

    __slots__ = ['file_cache']

    file_cache = dict()

    def __new__(cls, *args, **kwargs):
        return super(FileCache, cls).__new__(cls, *args, **kwargs)

    def __init__(self, root=None):
        if root:
            self.dig_for_files(root)

    # @timeit
    def dig_for_files(self, root):
        """Dig for all files under the given root and store findings
         in the cache.

        :param root: `str` root location to begin digging for files
        :return: None
        """

        self.file_cache.setdefault(root, dict())

        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            if not filenames:
                continue

            filenames.sort()
            self.file_cache.setdefault(dirpath, dict())

            for filename in filenames:
                numbers = re.findall('[0-9]+', filename)
                pat = numbers and numbers[-1] or '\a'

                # identifier used to collect related images
                identifier = re.sub(pat, '#', filename)

                self.file_cache[dirpath].setdefault(
                    identifier,
                    dict(files=list())
                )['files'].append(filename)

    # @timeit
    def locate_files(self, criteria, root=None, force=False):
        """Locate files which match the given criteria.

        :param criteria: `dict` containing regex and timecode tests
        :param root: `str` root folder to look for files in
         `FileCache` will dig for files at this root if not found in cache
        :param force: `bool` Force a new dig at passed root in case of new files
        :return:
        """

        results = dict()
        if root:
            if root not in self.file_cache or force:
                self.dig_for_files(root)

        for dirname, data in self.file_cache.items():
            if root and root not in dirname:
                continue

            for identifier, cache in data.items():
                if not cache['files']:
                    continue

                files = [cache['files'][0], cache['files'][-1]]
                if self.check_criteria(criteria, dirname, identifier, files):
                    results.update(
                        {
                            dirname: copy.deepcopy(
                                self.file_cache[dirname][identifier]
                            )
                        }
                    )

        return results

    # @timeit
    def check_criteria(self, criteria, dirname, identifier, files):
        """Check that the passed files match the timecode and naming we're
          looking for

        :param criteria: `dict` containing regex and timecode tests
        :param dirname: str` with dirname of file location
        :param identifier: `str` filename with hashed frame number
        :param files: `list` of first and last file found
        :return: `bool` reflecting a match or not
        """

        for index, filename in enumerate(files):
            fullpath = os.path.join(dirname, filename)

            valid_path = criteria['regex'].search(fullpath)
            if not valid_path:
                return False

            buf = oiio.ImageBuf(str(fullpath))
            if buf.has_error:
                return False

            if index == 0:
                value = self.file_cache[dirname][identifier].setdefault(
                    'tc_in',
                    get_timecode_str(buf)
                )
                self.file_cache[dirname][identifier].setdefault(
                    'fps',
                    get_fps(buf)
                )

            else:
                value = self.file_cache[dirname][identifier].setdefault(
                    'tc_out',
                    get_timecode_str(buf)
                )

            for test in criteria['tests']:
                func, test_value = test

                if not func(value, test_value):
                    return False

        return True


def create_sequence_reference(in_clip, dirname, data):
    """Create an ImageSequenceReference object to pass onto in_clip's
     media_reference.

    :param in_clip: `otio.schema.Clip`
    :param dirname: `str` with dirname of file location
    :param data: `dict` containing TimeCodes, fps and files found
    :return: `otio.schemadef.imagesequence_reference.ImageSequenceReference`
    """

    # Regex to locate frame number
    frame_reg = re.compile('(?<=[._])[0-9]+(?=\.\w+$)')

    duration = len(data['files'])
    rate = data.get('fps') or in_clip.source_range.start_time.rate
    frame_num = frame_reg.search(data['files'][0]).group()

    available_range = otio.opentime.TimeRange(
        otio.opentime.from_timecode(
            data['tc_in'],
            rate=rate
        ),
        otio.opentime.RationalTime(
            value=duration,
            rate=rate
        )
    )
    frame_range = otio.opentime.TimeRange(
        otio.opentime.RationalTime(
            value=int(frame_num),
            rate=rate
        ),
        otio.opentime.RationalTime(
            value=duration,
            rate=rate
        )
    )

    name = frame_reg.sub('%0{n}d'.format(n=len(frame_num)), data['files'][0])
    fullpath = os.path.join(dirname, name)

    seq = otio.schemadef.imagesequence_reference.ImageSequenceReference()
    seq.name = name
    seq.target_url = 'file://{path}'.format(path=fullpath)
    seq.available_range = available_range
    seq.frame_range = frame_range

    return seq


def link_media_reference(in_clip, media_linker_argument_map):
    """Link images that match the timecodes from the `in_clip.source_range`.
     The `media_linker_argument_map` should provide a few keys:
        {
            'root': '/root/path/to/search/for/files',
            'pattern': '.*plate*.'  # regex to narrow down the search,
            'ext': 'exr'  # file extension to narrow down search
        }

    :param in_clip:
    :param media_linker_argument_map:
    :return: `None`, `ImageSequenceReference` or list of such
    """

    root = media_linker_argument_map.get('root', os.curdir)
    pattern = media_linker_argument_map.get('pattern', '')
    ext = media_linker_argument_map.get('ext')

    # Search criteria
    criteria = {
        'regex': re.compile(
            r'({pattern}).*(\.{ext})$'.format(pattern=pattern, ext=ext)
        ),
        'tests': [
            [
                operator.ge,
                otio.opentime.to_timecode(
                    in_clip.source_range.start_time
                )
            ],
            [
                operator.lt,
                otio.opentime.to_timecode(
                    in_clip.source_range.start_time +
                    in_clip.source_range.duration
                )
            ]
        ]
    }

    cache = FileCache()
    results = cache.locate_files(criteria, root=root)

    candidates = list()
    for dirname, data in results.items():
        if in_clip.name in data['files'][0]:
            seq = create_sequence_reference(in_clip, dirname, data)
            candidates.append(seq)

    # Use the first hit when linked with OTIO console tools.
    if candidates and USE_FIRST:
        return candidates[0]

    # When used in custom applications you may want to choose best fit
    return candidates or None
