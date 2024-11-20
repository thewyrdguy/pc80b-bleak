from setuptools import setup
from re import findall

with open("debian/changelog", "r") as clog:
    _, version, _ = findall(
        r"(?P<src>.*) \((?P<version>.*)\) (?P<suite>.*); .*",
        clog.readline().strip(),
    )[0]

setup(
    name="bluering",
    version=version,
    description="Tool to read realtime ECG from PC-80B",
    url="http://www.average.org/bluering/",
    author="Peter Wyrd",
    author_email="thewyrdguy@gmail.com",
    install_requires=["bleak"],
    license="MIT",
    packages=[
        "ecgble",
    ],
    scripts=["scripts/ecgble"],
    long_description=open("README.md").read(),
)
