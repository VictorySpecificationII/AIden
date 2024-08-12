from setuptools import setup, find_packages

setup(
    name='AIden',
    version='0.1',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    install_requires=[
        'transformers',
        'torch',
        'requests',
        'pytest',
        'python-dotenv'
    ],
    entry_points={
        'console_scripts': [
            'copilot=src.copilot:main',
        ],
    },
)
