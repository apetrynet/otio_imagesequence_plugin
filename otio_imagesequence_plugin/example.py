import os
import re

import opentimelineio as otio


"""
This example will create an RV session with linked image-sequence based 
media for your edl.

PLEASE NOTE:
 that I replace the source_range of the clip. This is because the 
rv_session adapter doesn't know how to handle the ImageReference files and 
map the frame range accordingly. If this whole idea seems like a good way of 
handling image sequences I suggest adding the ImageReference to the built in 
schema's and adding some logic to call the `map_source_range_to_frame_range` 
mehtod when needed in adapters like rv_session.
"""


def get_rv_path():
    for p in os.environ.get('PATH', '').split(os.pathsep):
        if re.search('rv[0-9]+\.[0-9]+\.[0-9]+?', p):
            return p

    return None


# You must provide rv_path if the above function doesn't do it for you
rv_path = get_rv_path()

otioenv = {
    'OTIO_RV_PYTHON_BIN': os.path.join(rv_path, 'py-interp'),
    'OTIO_RV_PYTHON_LIB': os.path.join(rv_path, '..', 'src', 'python')
    }

os.environ.update(otioenv)


def main():
    edl_path = 'my_efforts_V1.edl'
    args = {
            'pattern': '.*proxy.*',
            'ext': 'exr',
            'root': '/path/to/source/plates'
        }

    tl = otio.adapters.read_from_file(edl_path, 'cmx_3600', rate=23.976)
    linker = otio.media_linker.from_name('imagesequence_linker')

    for clip in tl.each_clip():

        results = linker.link_media_reference(clip, args)
        if results:
            index = 0
            if len(results) > 1:
                alternatives = '\n'.join(
                    ['{i}, {p}'.format(i=i, p=r.target_url)
                     for i, r in enumerate(results)]
                )
                index = raw_input(
                    'Several hits found for {c}:\n{results}\n'
                    'Please enter index of the one you like? [0]: '
                    .format(c=clip.name, results=alternatives)
                ) or 0

                if index > len(results) - 1:
                    print 'You chose out of range so I used index 0'
                    index = 0

            seq = results[int(index)]
            clip.media_reference = seq
            clip.source_range = seq.map_source_range_to_frame_range(
                clip.source_range
            )

    otio.adapters.write_to_file(tl, './my_efforts_V1.rv', 'rv_session')


if __name__ == '__main__':
    main()
