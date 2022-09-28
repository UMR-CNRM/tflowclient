# -*- coding: utf-8 -*-

#  Copyright (©) Meteo-France (2020-)
#
#  This software is a computer program whose purpose is to provide
#   a text-based console client to interact with various workflow schedulers.
#
#  This software is governed by the CeCILL-C license under French law and
#  abiding by the rules of distribution of free software.  You can  use,
#  modify and/ or redistribute the software under the terms of the CeCILL-C
#  license as circulated by CEA, CNRS and INRIA at the following URL
#  "http://www.cecill.info".
#
#  As a counterpart to the access to the source code and  rights to copy,
#  modify and redistribute granted by the license, users are provided only
#  with a limited warranty  and the software's author,  the holder of the
#  economic rights,  and the successive licensors  have only  limited
#  liability.
#
#  In this respect, the user's attention is drawn to the risks associated
#  with loading,  using,  modifying and/or developing or reproducing the
#  software by the user in light of its specific status of free software,
#  that may mean  that it is complicated to manipulate,  and  that  also
#  therefore means  that it is reserved for developers  and  experienced
#  professionals having in-depth computer knowledge. Users are therefore
#  encouraged to load and test the software's suitability as regards their
#  requirements in conditions enabling the security of their systems and/or
#  data to be ensured and,  more generally, to use and operate it in the
#  same conditions as regards security.
#
#  The fact that you are presently reading this means that you have had
#  knowledge of the CeCILL-C license and that you accept its terms.

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
* :mod:`tflowclient.conf` is an utility module that is used to handle the
  configuration data
* The :mod:`tflowclient.logs_gateway` module makes it possible to list and
  fetch the some log files for a given task
* The :mod:`tflowclient.observer` provides a very simple implementation of the
  Observer design pattern.

"""

__all__ = ["cdp_flow", "demo_flow", "TFlowApplication"]

__version__ = "0.6.0"

from .ui import TFlowApplication
