# -*- coding: utf-8 -*-

"""
tflowclient setuptools configuration file.
"""

from setuptools import setup


def readme():
    """Re-use the README.md file."""
    with open("README.md") as f:
        return f.read()


setup(
    name="tflowview",
    version="0.5.3",
    description="A text-based viewer for ECMWF workflow schedulers.",
    long_description=readme(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Natural Language :: English",
        "License :: CeCILL-C Free Software License Agreement (CECILL-C)",
        "Programming Language :: Python :: 3.5",
    ],
    keywords="SMS",
    url="http://opensource.umr-cnrm.fr",
    author="Louis-François Meunier",
    author_email="louis-francois.meunier@meteo.fr",
    license="CECILL-C",
    package_dir={"tflowclient": "src/tflowclient"},
    packages=["tflowclient"],
    scripts=[
        "bin/tflowclient_cdp.py",
        "bin/tflowclient_demo.py",
        "bin/tflowclient_dumppalette.py",
    ],
    install_requires=["urwid"],
    include_package_data=True,
    zip_safe=True,
)
