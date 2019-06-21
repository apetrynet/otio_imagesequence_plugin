import os
import time


def timeit(method):     # pragma: nocover
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()

        print '\nfunc: %s, %2.6f sec' % (method.__name__, te - ts)
        return result
    return timed


class FileLocator(object):
    __slots__ = ['findings']

    findings = dict()

    def __new__(cls, *args, **kwargs):
        print len(cls.findings)
        return super(FileLocator, cls).__new__(cls, *args, **kwargs)

    def __init__(self, root=None):
        if root:
            self.dig_for_files(root)

    @timeit
    def locate_files(self, criteria, root=None, force=False):
        results = list()
        if root:
            if root not in self.findings or force:
                self.dig_for_files(root)

        for dirname, data in self.findings.items():
            if root and root not in dirname:
                continue

            result = filter(
                # TODO: replace with smarter function
                # lambda p: criteria['regex'].search(p),
                lambda p: self.check_criteria(
                    criteria, os.path.join(dirname, p)
                ),
                data['files']
            )
            if result:
                results.extend(result)

        return results

    @timeit
    def check_criteria(self, criteria, filename):
        valid_path = criteria['regex'].search(filename)
        if not valid_path:
            return False

        for key, tests in criteria['metadata'].items():
            if not isinstance(tests, list):
                tests = [tests]

            if key == 'timecode':
                value = get_timecode_str(filename)

            # elif key in ['width', 'height']:
            #     value =
            for test in tests:
                func, test_value = test
                if not func(value, test_value):
                    return False

        return True

    @timeit
    def dig_for_files(self, root):
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            filenames.sort()
            self.findings.setdefault(
                dirpath,
                dict(metadata=dict(), files=filenames)
            )


def link_media_reference(in_clip, media_linker_argument_map):
    root = media_linker_argument_map['root']
    loc = FileLocator(root=root)
    print 'Yohohoh', in_clip.media_reference
