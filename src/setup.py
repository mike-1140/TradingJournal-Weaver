from setuptools import setup, find_packages

setup(
    name="xml",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        # Spezifische Dependencies
        "pandas>=2.2.0"
    ],
    extras_require={
        'dev': ['pytest', 'black', 'flake8']
    }
)
