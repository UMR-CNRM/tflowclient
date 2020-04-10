# -*- coding: utf-8 -*-

from setuptools import setup


def readme():
    with open('README.md') as f:
        return f.read()


setup(name='tflowview',
      version='0.1',
      description='A text-based viewer for ECMWF workflow schedulers.',
      long_description=readme(),
      classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console :: Curses',
        'Intended Audience :: Science/Research',
        'Natural Language :: English',
        'License :: CeCILL-C Free Software License Agreement (CECILL-C)',
        'Programming Language :: Python :: 3.5',
      ],
      keywords='SMS',
      url='http://opensource.umr-cnrm.fr',
      author='Louis-François Meunier',
      author_email='louis-francois.meunier@meteo.fr',
      license='CECILL-C',
      package_dir={'tflowclient': 'src/tflowclient'},
      packages=['tflowclient'],
      scripts=['bin/tflowclient_cdp.py'],
      install_requires=[
          'urwid',
      ],
      test_suite='nose.collector',
      tests_require=['nose'],
      include_package_data=True,
      zip_safe=True)
