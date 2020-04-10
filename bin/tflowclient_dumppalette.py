#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dump the default palette (i.e color scheme) in a form that will be directly
usable in the configuration file.
"""

from tflowclient.conf import TFlowClientConfig

if __name__ == '__main__':
    palette = TFlowClientConfig(conf_txt='').palette
    print('[palette]')
    for line in palette:
        print('{:s} = {:s}'
              .format(line[0],
                      ', '.join(['+'.join(i) if isinstance(i, tuple) else i
                                 for i in line[1:]]))
              )
