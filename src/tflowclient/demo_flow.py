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
This module provides a :class:``tflowclient.flow.FlowInterface`` implementation
that do not need any external tools to actually connect to a flow scheduler
server.

A fake workflow is generated. This class is solely used fo demonstration
purposes in the ``bin/tflowclient_demo.py`` executable.
"""
import collections
import logging
import time
import typing

from .flow import FlowInterface, FlowNode, RootFlowNode, FlowStatus, ExtraFlowNodeInfo
from .logs_gateway import LogsGateway, get_logs_gateway

__all__ = ["DemoFlowInterface"]

logger = logging.getLogger(__name__)


class DemoFlowInterface(FlowInterface):
    """A demonstration/dependency-less :class:`FlowInterface`."""

    def __init__(self, suite: str, min_refresh_interval: int = 5):
        self._n_refreshed = collections.defaultdict(int)
        super().__init__(suite, min_refresh_interval)

    @property
    def credentials_summary(self) -> str:
        """
        Return a string representing the credential used to connect to the
        Workflow scheduler server.
        """
        return "fakeuser@fakeserver"

    def _valid_credentials(self, credentials: dict) -> dict:
        """This is an abstract method: we need to implement it.

        But it's not actually used in the demo.
        """
        return credentials

    def _retrieve_tree_roots(self) -> RootFlowNode:
        """Create a fake list of root nodes for our workflow definition."""
        rfn = RootFlowNode("", FlowStatus.ACTIVE)
        for i_x in range(2):
            rfn.add("{:04d}".format(i_x), FlowStatus.COMPLETE)
        rfn.add("{:04d}".format(2), FlowStatus.ABORTED)
        for i_x in range(3, 80):
            rfn.add("{:04d}".format(i_x), FlowStatus.SUSPENDED)
        logger.debug("Got tree roots statuses:\n%s", rfn)
        return rfn

    def _generic_flow_node(self, path, top_status=None, overall_status=None):
        """Create fake family/tasks tree for our workflow definition."""
        time.sleep(1)
        self._n_refreshed[path] += 1
        rfn = RootFlowNode(path, top_status or overall_status or FlowStatus.ABORTED)
        for i_f in range(15):
            f_status = FlowStatus.QUEUED
            ff_status = FlowStatus.QUEUED
            if i_f < 4:
                f_status = FlowStatus.COMPLETE
                ff_status = FlowStatus.COMPLETE
            if i_f == 4:
                f_status = (
                    FlowStatus.ACTIVE
                    if self._n_refreshed[path] % 3
                    else FlowStatus.ABORTED
                )
                ff_status = None
            family = rfn.add(
                "{:s}_family{:02d}".format(path, i_f), overall_status or f_status
            )
            efm = family.add(
                "extra_family", overall_status or ff_status or FlowStatus.ACTIVE
            )
            for i_t in range(3):
                efm.add(
                    "task{:02d}".format(i_t),
                    overall_status or ff_status or FlowStatus.COMPLETE,
                )
            efm.add(
                "task{:02d}".format(4), overall_status or ff_status or FlowStatus.ACTIVE
            )
            for i_t in range(3):
                family.add(
                    "task{:02d}".format(i_t),
                    overall_status or ff_status or FlowStatus.COMPLETE,
                )
            for i_t in range(3, 5):
                family.add(
                    "task{:02d}".format(i_t),
                    overall_status or ff_status or FlowStatus.ACTIVE,
                )
            family.add(
                "task{:02d}".format(5),
                overall_status
                or ff_status
                or (
                    FlowStatus.ACTIVE
                    if self._n_refreshed[path] % 3
                    else FlowStatus.ABORTED
                ),
            )
            family.add(
                "task{:02d}".format(6),
                overall_status or ff_status or FlowStatus.SUBMITTED,
            )
            family.add(
                "task{:02d}".format(7),
                overall_status or ff_status or FlowStatus.UNKNOWN,
            )
        logger.debug('Got statuses for "%s":\n%s', path, rfn)
        return rfn

    def _retrieve_status(self, path: str) -> RootFlowNode:
        """Create fake family/tasks tree for our workflow definition."""
        time.sleep(0.1)
        if path in ("0000", "0001"):
            return self._generic_flow_node(path, overall_status=FlowStatus.COMPLETE)
        if path == "0002":
            return self._generic_flow_node(path)
        else:
            return self._generic_flow_node(
                path, top_status=FlowStatus.SUSPENDED, overall_status=FlowStatus.QUEUED
            )

    @staticmethod
    def _any_command(root_node: FlowNode, paths: typing.List[str]) -> str:
        """This is a dummy method that will be called instead of any actual command."""
        assert isinstance(root_node, FlowNode)
        time.sleep(0.5)
        return "\n".join(
            [
                "This is a demo run: what did you expect ?",
                "Here is the list of paths:",
            ]
            + paths
        )

    do_rerun = _any_command
    do_execute = _any_command
    do_suspend = _any_command
    do_resume = _any_command
    do_complete = _any_command
    do_requeue = _any_command
    do_cancel = _any_command

    def _logs_gateway_create(self) -> LogsGateway:
        """Create a demo LogsGateway object."""
        return get_logs_gateway(kind="demo")

    def node_info(self, node: FlowNode) -> typing.List[ExtraFlowNodeInfo]:
        """Some demo information."""
        return [
            ExtraFlowNodeInfo(
                "flowspecific",
                "MaxTries",
                "1",
                description="Inherited from /{:s}".format(self.suite),
                editable=True,
            ),
            ExtraFlowNodeInfo("limit", "run", "10", editable=True),
            ExtraFlowNodeInfo("limit", "runpp", "2", editable=True),
            ExtraFlowNodeInfo("meter", "ymdh", "2020010100", editable=True),
            ExtraFlowNodeInfo("trigger", "toto [complete]"),
            ExtraFlowNodeInfo(
                "repeat",
                "YMD",
                "2021010100",
                description="type: date. info: from 20210616 to 20211231 step 1",
                editable=True,
            ),
        ]

    def _actual_save_node_info(
        self, node: FlowNode, info: typing.List[ExtraFlowNodeInfo]
    ) -> str:
        """This is a dummy method that will be called instead of any actual command."""
        assert self
        assert isinstance(node, FlowNode)
        assert isinstance(info, list)
        time.sleep(0.5)
        return "This is a demo run: what did you expect ?"
