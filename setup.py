from setuptools import setup


setup(
    name='otio_imagesequence_plugin',
    entry_points={
        'opentimelineio.plugins': 'image_sequence = otio_imagesequence_plugin'
    },
    packages=[
        'otio_imagesequence_plugin',
        'otio_imagesequence_plugin.operations',
        'otio_imagesequence_plugin.schema'
    ],
    package_data={
        'otio_imagesequence_plugin': [
            'plugin_manifest.json'
        ]
    },
    keywords='plugin OpenTimelineIO image sequence',
    platforms='any',
    version='1.0.0',
    description='Schemadef and media linker to work with image sequences',
    license='MIT License',
    author='Daniel Flehner Heen',
    author_email='flehnerheener@gmail.com',
    url='http://opentimeline.io'
)
