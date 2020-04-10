# -*- coding: utf-8 -*-

"""
This module provides a :class:``tflowclient.flow.FlowInterface`` implementation
that do not need any external tools to actually connect to a flow scheduler
server.

A fake workflow is generated. This class is solely used fo demonstration
purposes in the ``bin/tflowclient_demo.py`` executable.
"""

import logging
import typing

from . flow import FlowInterface, FlowNode, RootFlowNode, FlowStatus

__all__ = ['DemoFlowInterface']

logger = logging.getLogger(__name__)


class DemoFlowInterface(FlowInterface):
    """A demonstration/dependency-less :class:`FlowInterface`."""

    @property
    def credentials_summary(self) -> str:
        """
        Return a string representing the credential used to connect to the
        Workflow scheduler server.
        """
        return 'fakeuser@fakeserver'

    def _valid_credentials(self, credentials: dict) -> dict:
        """This is an abstract method: we need to implement it.

        But it's not actually used in the demo.
        """
        return credentials

    def _retrieve_tree_roots(self) -> RootFlowNode:
        """Create a fake list of root nodes for our workflow definition."""
        rfn = RootFlowNode(self.suite, FlowStatus.ACTIVE)
        for i_x in range(2):
            rfn.add('{:04d}'.format(i_x), FlowStatus.COMPLETE)
        rfn.add('{:04d}'.format(2), FlowStatus.ABORTED)
        for i_x in range(3, 80):
            rfn.add('{:04d}'.format(i_x), FlowStatus.SUSPENDED)
        logger.debug('Got tree roots statuses:\n%s', rfn)
        return rfn

    @staticmethod
    def _generic_flow_node(path, top_status=None, overall_status=None):
        """Create fake family/tasks tree for our workflow definition."""
        rfn = RootFlowNode(path,
                           top_status or overall_status or FlowStatus.ABORTED)
        for i_f in range(15):
            f_status = FlowStatus.QUEUED
            ff_status = FlowStatus.QUEUED
            if i_f < 4:
                f_status = FlowStatus.COMPLETE
                ff_status = FlowStatus.COMPLETE
            if i_f == 4:
                f_status = FlowStatus.ABORTED
                ff_status = None
            family = rfn.add('{:s}_family{:02d}'.format(path, i_f),
                             overall_status or f_status)
            efm = family.add('extra_family',
                             overall_status or ff_status or FlowStatus.ACTIVE)
            for i_t in range(3):
                efm.add('task{:02d}'.format(i_t),
                        overall_status or ff_status or FlowStatus.COMPLETE)
            efm.add('task{:02d}'.format(4),
                    overall_status or ff_status or FlowStatus.ACTIVE)
            for i_t in range(3):
                family.add('task{:02d}'.format(i_t),
                           overall_status or ff_status or FlowStatus.COMPLETE)
            for i_t in range(3, 5):
                family.add('task{:02d}'.format(i_t),
                           overall_status or ff_status or FlowStatus.ACTIVE)
            family.add('task{:02d}'.format(5),
                       overall_status or ff_status or FlowStatus.ABORTED)
            family.add('task{:02d}'.format(6),
                       overall_status or ff_status or FlowStatus.SUBMITTED)
            family.add('task{:02d}'.format(7),
                       overall_status or ff_status or FlowStatus.UNKNOWN)
        logger.debug('Got statuses for "%s":\n%s', path, rfn)
        return rfn

    def _retrieve_status(self, path: str) -> RootFlowNode:
        """Create fake family/tasks tree for our workflow definition."""
        if path in ('0000', '0001'):
            return self._generic_flow_node(path, overall_status=FlowStatus.COMPLETE)
        if path == '0002':
            return self._generic_flow_node(path)
        else:
            return self._generic_flow_node(path, top_status=FlowStatus.SUSPENDED,
                                           overall_status=FlowStatus.QUEUED)

    @staticmethod
    def _any_command(root_node: FlowNode, paths: typing.List[str]) -> str:
        """This is a dummy method that will be called instead of any actual command."""
        assert isinstance(root_node, FlowNode)
        assert isinstance(paths, list)
        return "This is a demo run: what did you expect ?"

    do_rerun = _any_command
    do_execute = _any_command
    do_suspend = _any_command
    do_resume = _any_command
    do_complete = _any_command
    do_requeue = _any_command
