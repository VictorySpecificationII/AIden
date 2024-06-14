from setuptools import setup, find_packages

setup(
    name='AIden',
    version='0.1',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    install_requires=[
        'llama-index',
        'transformers',
        'torch',
        'requests',
        'pytest',
        'python-dotenv',
	'pip install llama-index-llms-huggingface',
	'pip install llama-index-embeddings-huggingface'
    ],
    entry_points={
        'console_scripts': [
            'copilot=src.copilot:main',
        ],
    },
)
