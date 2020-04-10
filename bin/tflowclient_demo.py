#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This is a demonstration-only executable.

It creates a dummy flow scheduler family/tasks tree. Compared to the "real"
``tflowclient_sms.py`` executable, it does not require any external software
or server.
"""

from tflowclient import TFlowApplication
from tflowclient.conf import tflowclient_conf
from tflowclient import demo_flow

if __name__ == '__main__':
    tflowclient_conf.logging_config()
    demo = demo_flow.DemoFlowInterface('fakesuite')
    app = TFlowApplication(demo)
    app.main()
