import os
import re
import time
import copy
import shlex
import operator

import OpenImageIO as oiio
import opentimelineio as otio


otio.schema.schemadef.from_name('imagesequence_reference')


def timeit(method):     # pragma: nocover
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()

        print '\nfunc: %s, %2.6f sec' % (method.__name__, te - ts)
        return result
    return timed


def get_timecode_str(path):
    buf = oiio.ImageBuf(str(path))
    spec = buf.spec()
    tc = None
    tc_bin = None
    if not buf.has_error and not spec.getattribute('oiio:Movie'):
        for v in spec.extra_attribs:
            if v.name == "smpte:TimeCode":
                if isinstance(v.value, tuple):
                    tc_bin, _ = v.value

                else:
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
    __slots__ = ['file_cache']

    file_cache = dict()

    def __new__(cls, *args, **kwargs):
        return super(FileCache, cls).__new__(cls, *args, **kwargs)

    def __init__(self, root=None):
        if root:
            self.dig_for_files(root)

    @timeit
    def dig_for_files(self, root):
        self.file_cache.setdefault(root, dict())

        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            if not filenames:
                continue

            filenames.sort()
            self.file_cache.setdefault(dirpath, dict())

            for filename in filenames:
                numbers = re.findall('[0-9]+', filename)
                pat = numbers and numbers[-1] or '\a'
                identifier = re.sub(pat, '#', filename)

                self.file_cache[dirpath].setdefault(
                    identifier,
                    dict(files=list())
                )['files'].append(filename)

    @timeit
    def locate_files(self, criteria, root=None, force=False):
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
        results = list()
        for index, filename in enumerate(files):
            fullpath = os.path.join(dirname, filename)

            valid_path = criteria['regex'].search(fullpath)
            if not valid_path:
                results.append(False)

            for key, tests in criteria['metadata'].items():
                if not isinstance(tests, list):
                    tests = [tests]

                if key == 'timecode':
                    if index == 0:
                        value = self.file_cache[dirname][identifier].setdefault(
                            'tc_in',
                            get_timecode_str(fullpath)
                        )

                    else:
                        value = self.file_cache[dirname][identifier].setdefault(
                            'tc_out',
                            get_timecode_str(fullpath)
                        )

                for test in tests:
                    func, test_value = test

                    if not func(value, test_value):
                        results.append(False)

            return not results


def create_sequence_reference(in_clip, dirname, data):
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
    fullpath = os.path.join(
        dirname,
        name
    )

    seq = otio.schemadef.imagesequence_reference.ImageSequenceReference()
    seq.name = name
    seq.target_url = 'file://{path}'.format(path=fullpath)
    seq.available_range = available_range
    seq.frame_range = frame_range

    return seq


def link_media_reference(in_clip, media_linker_argument_map):
    root = media_linker_argument_map.get('root', os.curdir)
    basename = media_linker_argument_map.get(
        'basename',
        in_clip.name
    )
    ext = media_linker_argument_map.get('ext', None)

    criteria = {
        'regex': re.compile(
            r'({basename}).*(\.{ext})$'.format(basename=basename, ext=ext)
        ),
        'metadata': {
            'timecode': [
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

    }

    loc = FileCache()
    results = loc.locate_files(criteria, root=root)

    # Use the first result only
    for dirname, data in results.items():
        seq = create_sequence_reference(in_clip, dirname, data)
        in_clip.media_reference = seq
        break
