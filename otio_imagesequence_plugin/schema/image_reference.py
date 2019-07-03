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
Implementation of the ImageReference media reference schema.
"""

import copy

import opentimelineio as otio


@otio.core.register_type
class ImageReference(otio.core.MediaReference):
    """Reference to image sequence via a url, for example
     "file:///var/tmp/foo.%04d.exr"
    """

    _serializable_label = "ImageReference.1"
    _name = "ImageReference"

    target_url = otio.core.serializable_field(
        "target_url",
        doc=(
            "URL at which this media lives.  For local references, use the "
            "'file://' format."
        )
    )

    frame_range = otio.core.serializable_object.serializable_field(
        "frame_range",
        otio.opentime.TimeRange,
        doc="Frame range of media in this media reference."
    )

    def __init__(
        self,
        target_url=None,
        available_range=None,
        frame_range=None,
        metadata=None,
    ):
        otio.core.MediaReference.__init__(
            self,
            available_range=available_range,
            metadata=metadata
        )

        self.target_url = target_url

        if available_range and not frame_range:
            frame_range = copy.deepcopy(available_range)

        self.frame_range = frame_range

    def __str__(self):
        return 'ImageReference("{}")'.format(self.target_url)

    def __repr__(self):
        return 'otio.schemadef.ImageReference(target_url={})'.format(
            repr(self.target_url)
        )