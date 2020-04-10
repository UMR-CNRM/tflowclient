# -*- coding: utf-8 -*-

"""
The ``tflowclient`` package (Text-based workFlow scheduler Client) provides all
the necessary bits to build text-based console clients to interact with
various workflow schedulers. For now, only ``SMS`` is supported: see the
``tflowclient_sms.py`` executable.

Here are a few pointers for a better understanding of the code:

* The interactions with the WorkFlow scheduler server, is handle by objects
  that inherit from :class:`tflowclient.flow.FlowInterface`. The
  :class:`tflowclient.flow.FlowInterface` class defines an abstract interface
  we rely on to build the user interface.
* At some point, the statuses of the family/tasks tree will need to be retrieved
  and represented. An abstract representation for such a tree, can be created
  using the :class:`tflowclient.flow.FlowNode` class. The family/task status is
  stored using a limited set of values defined in the
  :class:`tflowclient.flow.FlowStatus` class.
* The :mod:`tflowclient.demo_flow` and :mod:`tflowclient.cdp_flow` provide
  concrete implementations of the :class:`tflowclient.flow.FlowInterface`
  abstract class.
* The :mod:`tflowclient.conf` is an utility module that is used to handle the
  configuration data
* The :mod:`tflowclient.observer` provides a very simple implementation of the
  Observer design pattern.

"""

__all__ = ['cdp_flow', 'demo_flow', 'TFlowApplication']

__version__ = '0.1'

from .ui import TFlowApplication
