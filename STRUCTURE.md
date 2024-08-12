# Project Directory Structure

```plaintext
AIden/
├── data/
│   ├── raw/                # Raw data files
│   └── processed/          # Processed data files ready for indexing
├── src/
│   ├── __init__.py         # Makes src a package
│   ├── copilot.py          # Main code for the AI copilot
│   ├── x.py                # Code for the subsystem x
│   └── utils.py            # Utility functions
├── notebooks/              # Jupyter notebooks for experimentation and analysis
├── tests/
│   ├── __init__.py         # Makes tests a package
│   ├── test_copilot.py     # Unit tests for the AI copilot
│   ├── test_x.py           # Unit tests for subsystem x
├── .gitignore              # Git ignore file
├── README.md               # Project overview and setup instructions
├── requirements.txt        # Python package dependencies
└── setup.py                # Script for installing the package
└── CONTRIBUTING.md         # Contribution documentation
