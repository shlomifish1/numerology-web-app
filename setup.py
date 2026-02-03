from setuptools import setup

setup(
    name='fishman_numerology',
    version='0.1',
    py_modules=['numerology'],
    entry_points={
        'console_scripts': [
            'numerology=numerology:main',
        ],
    },
)
