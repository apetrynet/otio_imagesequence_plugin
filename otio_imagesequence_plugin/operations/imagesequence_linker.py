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
It uses OIIO to fetch metadata from source files.
Frame numbers of source files will be used to match against clip's
source_range for image formats without TimeCode, like jpg's etc.

Example usage:

OTIO_PLUGIN_MANIFEST_PATH=../plugin_manifest.json \
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


# Check if we're using one of OTIO's console tools (bit of a hack..)
USE_FIRST = 'console' in sys.argv[0]

# Regex to locate frame number
frame_regex = re.compile('(?<=[._])[0-9]+(?=\.\w+$)')


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

    :param buf: `oiio.ImageBuf`
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

    :param buf: `oiio.ImageBuf`
    :return: `str` or `None`
    """

    spec = buf.spec()
    tc = spec.getattribute('timecode')

    if not tc:
        if oiio.VERSION < 20000:
            tc_param = next(
                (i for i in spec.extra_attribs if i.name == 'smpte:TimeCode'),
                None
            )
            tc_bin = tc_param and tc_param.value or None

        else:
            tc_param = spec.getattribute('smpte:TimeCode')
            tc_bin = tc_param and int(tc_param[0]) or None

        if tc_bin:
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
          looking for. Alternatively it will attempt to match frame number
          against source_range

        :param criteria: `dict` containing regex and timecode tests
        :param dirname: str` with dirname of file location
        :param identifier: `str` filename with hashed frame number
        :param files: `list` of first and last file found
        :return: `bool` reflecting a match or not
        """

        testname = 'timecode'

        for index, filename in enumerate(files):
            fullpath = os.path.join(dirname, filename)

            valid_path = criteria['regex'].search(fullpath)
            if not valid_path:
                return False

            buf = oiio.ImageBuf(fullpath)
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
                value = get_timecode_str(buf)

            # No TimeCode found. Try using frame number
            if not value:
                testname = 'frames'
                try:
                    if index == 0:
                        value = self.file_cache[dirname][identifier].setdefault(
                            'first_frame',
                            int(frame_regex.search(filename).group())
                        )
                    else:
                        value = int(frame_regex.search(filename).group())

                except (ValueError, AttributeError):
                    value = None

            func, test_value = criteria['tests'][testname][index]

            if not func(value, test_value):
                return False

        return True


def create_sequence_reference(in_clip, dirname, data):
    """Create an ImageReference object to pass onto in_clip's
     media_reference.

    :param in_clip: `otio.schema.Clip`
    :param dirname: `str` with dirname of file location
    :param data: `dict` containing TimeCodes, fps and files found
    :return: `otio.schemadef.imagesequence_reference.ImageReference`
    """

    duration = len(data['files'])
    rate = data.get('fps') or in_clip.source_range.start_time.rate
    frame_num = frame_regex.search(data['files'][0]).group()

    if data['tc_in']:
        start_time = otio.opentime.from_timecode(
            data['tc_in'] or data['first_frame'],
            rate=rate
        )

    else:
        start_time = otio.opentime.RationalTime(
            value=data['first_frame'],
            rate=rate
        )

    available_range = otio.opentime.TimeRange(
        start_time,
        otio.opentime.RationalTime(
            value=duration,
            rate=rate
        )
    )

    prefix, suffix = frame_regex.split(data['files'][0])
    seq = otio.schema.ImageSequenceReference(
        target_url_base=dirname + os.sep,
        name_prefix=prefix,
        name_suffix=suffix,
        start_value=int(frame_num),
        rate=rate,
        image_number_zero_padding=len(frame_num),
        available_range=available_range
    )

    return seq


# @timeit
def link_media_reference(in_clip, media_linker_argument_map):
    """Link images that match the timecodes from the `in_clip.source_range`.
     The `media_linker_argument_map` should/could provide a few keys:
        {
            'root': '/root/path/to/search/for/files',
            'pattern': '.*plate.*'  # regex to narrow down the search,
            'ext': 'exr'  # file extension to narrow down search
        }

    :param in_clip: `otio.schema.Clip`
    :param media_linker_argument_map: `dict` with kwargs
    :return: `None`, `ImageReference` or list of such
    """

    root = media_linker_argument_map.get('root', os.curdir)
    pattern = media_linker_argument_map.get('pattern', '')
    ext = media_linker_argument_map.get('ext')

    # Search criteria
    criteria = {
        'regex': re.compile(
            r'({pattern}).*(\.{ext})$'.format(pattern=pattern, ext=ext)
        ),
        'tests': {
            'timecode': [
                [
                    operator.ge,
                    otio.opentime.to_timecode(
                        in_clip.source_range.start_time
                    )
                ],
                [
                    operator.le,
                    otio.opentime.to_timecode(
                        in_clip.source_range.start_time +
                        in_clip.source_range.duration -
                        otio.opentime.RationalTime(
                            1,
                            in_clip.source_range.start_time.rate
                        )
                    )
                ]
            ],
            'frames': [
                [
                    operator.ge,
                    in_clip.source_range.start_time.value
                ],
                [
                    operator.le,
                    (
                        in_clip.source_range.start_time +
                        in_clip.source_range.duration -
                        otio.opentime.RationalTime(
                            1,
                            in_clip.source_range.start_time.rate
                        )
                    ).value
                ]
            ]
        }
    }

    cache = FileCache()
    results = cache.locate_files(criteria, root=root)

    candidates = list()
    for dirname, data in results.items():
        # If we have a clip name we'd prefer using files that match
        if in_clip.name and in_clip.name not in data['files'][0]:
            continue

        seq = create_sequence_reference(in_clip, dirname, data)
        candidates.append(seq)

    # Use the first hit when linker is used with OTIO console tools.
    if candidates and USE_FIRST:
        return candidates[0]

    # When linker is used in custom applications you may want to choose best fit
    return candidates or None
