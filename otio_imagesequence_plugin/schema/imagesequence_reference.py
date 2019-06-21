"""
Implementation of the ImageSequenceReference media reference schema.
"""

import copy

import opentimelineio as otio


@otio.core.register_type
class ImageSequenceReference(otio.core.MediaReference):
    """Reference to image sequence via a url, for example
     "file:///var/tmp/foo.%04d.exr"
    """

    _serializable_label = "ImageSequenceReference.1"
    _name = "ImageSequenceReference"

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
        return 'ImageSequenceReference("{}")'.format(self.target_url)

    def __repr__(self):
        return 'otio.schemadef.ImageSequenceReference(target_url={})'.format(
            repr(self.target_url)
        )
