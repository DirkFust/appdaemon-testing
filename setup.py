from setuptools import setup, find_packages

with open("README.md") as f:
    readme = f.read()

tests_require = ["pytest"]

setup(
    name="appdaemon-testing",
    description="Utilities for testing AppDaemon applications",
    long_description=readme,
    long_description_content_type="text/markdown",
    author="Nick Whyte",
    author_email="nick@nickwhyte.com",
    url="https://github.com/nickw444/appdaemon-testing",
    entry_points={"pytest11": ["appdaemon_testing = appdaemon_testing.pytest"]},
    install_requires=["appdaemon"],
    setup_requires=["pytest-runner"],
    tests_require=tests_require,
    extras_require={"test": tests_require, "pytest": ["pytest"]},
    license="MIT",
    classifiers=[
        "Framework :: Pytest",
        "Programming Language :: Python :: 3.11",
    ],
    packages=find_packages(exclude=("appdaemon_testing_tests",)),
)
