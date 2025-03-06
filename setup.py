from setuptools import setup
from re import findall

with open("debian/changelog", "r") as clog:
    _, version, _ = findall(
        r"(?P<src>.*) \((?P<version>.*)\) (?P<suite>.*); .*",
        clog.readline().strip(),
    )[0]

# for compiling gsettings schema:
# https://askubuntu.com/a/907762

setup(
    name="pc80b-bleak",
    version=version,
    description="Tool to live stream ECG from PC-80B with sound",
    url="https://www.github.com/thewyrdguy/pc80b-bleak",
    author="Peter Wyrd",
    author_email="thewyrdguy@gmail.com",
    install_requires=["bleak", "gi", "cairo"],
    license="MIT",
    packages=["pc80b_bleak"],
    scripts=["scripts/pc80b-bleak"],
    long_description=open("README.md").read(),
)
