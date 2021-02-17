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
The abstract class used by any kind of flow schedulers interfaces.

The :class:`FlowStatus` enumeration represents the possible statuses for any
family or task.

The :class:`FlowNode` and :class:`RootFlowNode` classes are designed to build
a representation of any family/tasks tree.

The :class:`FlowInterface` class describes the abstract interface used by the
:mod:`tflowclient` text-based interface to interact with the workflow scheduler.
"""

from __future__ import annotations

import abc
import collections
from enum import Enum, unique
import logging
import signal
import time
import traceback
import typing

from . import logs_gateway
from . import observer

__all__ = [
    "FlowStatus",
    "FlowNode",
    "RootFlowNode",
    "FlowInterface",
    "ExtraFlowNodeInfo",
]

logger = logging.getLogger(__name__)


@unique
class FlowStatus(Enum):
    """Possible statuses for any family or task."""

    ABORTED = 0
    SUBMITTED = 1
    ACTIVE = 2
    QUEUED = 3
    SUSPENDED = 4
    COMPLETE = 5
    UNKNOWN = 6


class FlowNode(observer.Subject):
    """Any node of the workflow tree.

    Here are some of the node characteristics:

    * A node has a ``name ``and a ``status``.
    * Each node can have zero or many children (created using the ``add``
      method).
    * A node can be selected or not (see the ``flagged`` property).
    * A node can be expanded by default in the tree representation (see the
      ``expanded`` property.
    * It can be used as a dictionary to access the child nodes (e.g. self['toto']
      will return the child node named ``toto``).
    * Each node can be observed (see the :class:`tflowclient.observer.Observer`
      class) to monitor changes on the ``flagged`` property.

    """

    EXPANDED_STATUSES = {
        FlowStatus.UNKNOWN,
        FlowStatus.ACTIVE,
        FlowStatus.ABORTED,
        FlowStatus.SUBMITTED,
    }

    def __init__(self, name: str, status: FlowStatus, parent: FlowNode = None):
        """
        :param name: The node's name
        :param status:  The node's status
        :param parent:  The node's parent node (``None`` if the node is the
                        root node of the family/task tree)
        """
        super().__init__()
        self._name = name
        self._status = status
        self._parent = parent
        self._expanded = parent is None  # The first entry is always expanded
        self._flagged = False
        self._children = collections.OrderedDict()

    @property
    def name(self) -> str:
        """The node's name."""
        return self._name

    @property
    def parent(self) -> typing.Union[FlowNode, str]:
        """The parent node."""
        return self._parent

    @property
    def status(self) -> FlowStatus:
        """The node's status."""
        return self._status

    @property
    def expanded(self):
        """Tells whether the node is expanded by default in a tree representation."""
        return self._expanded

    @property
    def flagged(self):
        """Returns `True` if the present node is selected."""
        return self._flagged

    @flagged.setter
    def flagged(self, value):
        """Set the ``flagged`` property."""
        self._flagged = bool(value)
        self._notify({"flagged": self.flagged})

    def _compute_path(self, with_root=True):
        s_path = []
        current = self
        while current is not None:
            if current.name and (with_root or current.parent is not None):
                s_path.append(current.name)
            current = current.parent
        return "/".join(reversed(s_path))

    @property
    def full_path(self):
        """Return the full path to the requested node."""
        return self._compute_path()

    @property
    def path(self):
        """Return the path to the requested node (relative to the root node)."""
        return self._compute_path(with_root=False)

    def set_expanded(self):
        """Set the `expanded` on this node and all its parents."""
        self._expanded = True
        if self.parent is not None:
            self.parent.set_expanded()

    def add(self, name: str, status: FlowStatus) -> FlowNode:
        """Create a new child node.

        :param name:  THe child node name.
        :param status: The child node status.
        """
        self._children[name] = FlowNode(name, status, parent=self)
        if status in self.EXPANDED_STATUSES:
            self._children[name].set_expanded()
        return self._children[name]

    def indented_str(self, level: int):
        """
        Creates a string representation of the current node with a given
        **level** indentation.
        """
        me = ["{0:s}[{1.status.name:s}]_{1.name:s}".format("  " * level, self)]
        me.extend([child.indented_str(level + 1) for child in self])
        return "\n".join(me)

    def __str__(self):
        """Creates a string representation of the current node with a given."""
        return self.indented_str(0)

    def __eq__(self, other):
        if not isinstance(other, FlowNode):
            return False
        identical = self.name == other.name and self.status == other.status
        identical = identical and len(self) == len(other)
        if identical:
            for s_child, o_child in zip(self, other):
                identical = identical and s_child == o_child
        return identical

    def __getitem__(self, item):
        return self._children[item]

    def __contains__(self, item):
        return item in self._children

    def __iter__(self) -> typing.Iterator[FlowNode]:
        """Iterates over children."""
        for child in self._children.values():
            yield child

    def __len__(self):
        """The number of children."""
        return len(self._children)

    def resolve_path(self, path: str) -> FlowNode:
        """Return the :class:`FlowNode` object that corresponds to a **path**.

        For example, looking for ``path='family1/task1'`` will return the
        ``task1`` child of the ``family1`` node that should be a child of
        the current node.

        If the path does not exists, a :class:`KeyError` exception will be
        raised.
        """
        if path:
            node = self
            for item in path.split("/"):
                node = node[item]
            return node
        else:
            return self

    def first_expanded_leaf(self):
        """Return the object representing the first expanded leaf in the current tree."""
        if self.expanded:
            if len(self) == 0:
                return self
            else:
                for child in self:
                    e_leaf = child.first_expanded_leaf()
                    if e_leaf is not None:
                        return e_leaf
        return None

    def iter_flagged_paths(self, path_base: str) -> typing.List[str]:
        """Internal method: iterate through the nodes tree."""
        flagged = list()
        path_base = (path_base + "/" if path_base else "") + self.name
        if self.flagged:
            flagged.append(path_base)
        for c_node in self:
            flagged.extend(c_node.iter_flagged_paths(path_base))
        return flagged

    def flagged_paths(self) -> typing.List[str]:
        """
        Return a list of paths to objects that are currently ``flagged`` below
        the current node.
        """
        flagged = []
        if self.flagged:
            flagged.append("")
        for c_node in self:
            flagged.extend(c_node.iter_flagged_paths(""))
        return flagged

    def flag_status(self, status: FlowStatus, leaf: bool = True):
        """Recursively flag all the nodes that correspond to a given **status**.

        :param status: The status of the node that should be flagged.
        :param leaf: Only flag leaf nodes (i.e. The one with no children)
        """
        if self.status == status and (not leaf or len(self) == 0):
            self.flagged = True
        for c_node in self:
            c_node.flag_status(status)

    def reset_flagged(self):
        """Reset (set to False) the flag of self and all the children nodes (recursively)."""
        if self.flagged:
            self.flagged = False
        for c_node in self:
            c_node.reset_flagged()

    def ingest_flagged(self, flaggedpaths: typing.List[str]):
        """Import a list of flagged paths."""
        for f in flaggedpaths:
            if f.startswith(self.name):
                try:
                    found = self.resolve_path(f[len(self.name) :].lstrip("/"))
                except KeyError:
                    pass
                else:
                    found.flagged = True
                    found.set_expanded()


class RootFlowNode(FlowNode):
    """An extension of the :class:`FlowNode`class that records the creation time."""

    def __init__(self, name: str, status: FlowStatus):
        """
        :param name: The node's name
        :param status:  The node's status
        """
        super().__init__(name, status)
        self._c_time = time.monotonic()
        self._focused = None

    @property
    def age(self) -> float:
        """The number of seconds from object's creation time."""
        return time.monotonic() - self._c_time

    def touch(self):
        """Update the creation time."""
        self._c_time = time.monotonic()

    @property
    def focused(self) -> FlowNode:
        """Returns the focused FlowNode within the Tree."""
        return self._focused

    @focused.setter
    def focused(self, value: FlowNode):
        """Set the ``_focused`` property."""
        assert isinstance(value, FlowNode)
        self._focused = value


class ExtraFlowNodeInfo(object):
    """An extra information on a FlowNode."""

    def __init__(
        self,
        kind: str,
        name: str,
        value: str = None,
        description: str = "",
        editable: bool = False,
    ):
        """
        :param kind: The kind of information (e.g. variable, meter, limit, ...)
        :param name: The information name (e.g. SMSTRIES, ...)
        :param value: The associated value
        :param description: Some extra information
        :param editable: Is this information editable or not ?
        """
        self._kind = kind
        self._name = name
        self._initial_value = value
        self._value = None
        self._description = description
        self._editable = editable
        if self._editable and self._initial_value is None:
            raise ValueError("incoherent editable and value settings.")

    def __eq__(self, other):
        if isinstance(other, ExtraFlowNodeInfo):
            return (
                self.kind == other.kind
                and self.name == other.name
                and self.value == other.value
                and self.description == other.description
                and self.editable == other.editable
            )
        else:
            return False

    def __str__(self):
        return "NodeInfo: {0.kind:s}-{0.name:s}. Value: {0.value!s}".format(self)

    @property
    def kind(self) -> str:
        """The kind of information (e.g. variable, meter, limit, ...)."""
        return self._kind

    @property
    def name(self) -> str:
        """The information name (e.g. SMSTRIES, ...)."""
        return self._name

    @property
    def value(self) -> str:
        """The associated value."""
        return self._initial_value if self._value is None else self._value

    @value.setter
    def value(self, new_value: str):
        """Edit the current value (if allowed)."""
        if not self.editable:
            raise RuntimeError("A readonly information cannot be modified")
        else:
            self._value = new_value

    @property
    def description(self) -> str:
        """Some extra information."""
        return self._description

    @property
    def editable(self) -> bool:
        """Is this information editable or not ?"""
        return self._editable

    @property
    def touched(self) -> bool:
        """``True`` if the value has been modified"""
        return self._value is not None and self._value != self._initial_value


class FlowInterface(observer.Subject, metaclass=abc.ABCMeta):
    """The interface to any workflow scheduler."""

    def __init__(self, suite: str, min_refresh_interval: int = 5):
        """
        :param suite: The workflow scheduler suite name
        :param min_refresh_interval: Do not refresh the statuses if they are
                                     less then X seconds old.
        """
        logger.info('Initialising "%s" for suite="%s".', str(self.__class__), suite)
        super().__init__()
        self._suite = suite
        self._min_refresh_interval = min_refresh_interval
        self._credentials = None
        self._tree_roots = None
        self._full_statuses = dict()
        self._logs_gateway_init = False
        self._logs_gateway = None

    def _initialise_connection(self):
        """Sometime, it is necessary to connect somewhere."""
        pass

    def _close_connection(self):
        """Sometime, it is necessary to close some active connections."""
        pass

    def __enter__(self):
        logger.debug('Entering in FlowInterface. Calling "_initialise_connection"')
        self._initialise_connection()

        def handler(signum, frame):
            """Internal callback to deal with signals."""
            assert frame
            raise BaseException("Signal {:d} was caught.".format(signum))

        all_signals = {
            signal.SIGHUP,
            signal.SIGINT,
            signal.SIGQUIT,
            signal.SIGPIPE,
            signal.SIGTRAP,
            signal.SIGABRT,
            signal.SIGFPE,
            signal.SIGUSR1,
            signal.SIGUSR2,
            signal.SIGTERM,
        }
        logger.debug("Installing handler for all signals: %s", all_signals)
        for sig in all_signals:
            signal.signal(sig, handler)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            logger.error('An un-handled "%s" occurred: %s', exc_type, exc_val)
            logger.error("Traceback:\n%s", "".join(traceback.format_tb(exc_tb)))
        logger.debug('Exiting FlowInterface. Calling "_close_connection"')
        self._close_connection()

    def __str__(self):
        return "suite {:s} ({:s})".format(self.suite, self.credentials_summary)

    @property
    def suite(self) -> str:
        """The suite we are working on."""
        return self._suite

    @property
    def min_refresh_interval(self) -> int:
        """The refresh threshold (in seconds).

        Statuses won't be refreshed if they were fetched less than X seconds ago.
        """
        return self._min_refresh_interval

    def _get_credentials(self) -> dict:
        if self._credentials is None:
            raise RuntimeError("Set credentials first")
        return self._credentials.copy()

    def _set_credentials(self, credentials: dict):
        self._credentials = self._valid_credentials(credentials)
        logger.debug("Credentials are: %s", self.credentials_summary)

    credentials = property(
        _get_credentials,
        _set_credentials,
        doc="The credentials used to login to the workflow scheduler.",
    )

    @property
    @abc.abstractmethod
    def credentials_summary(self) -> str:
        """
        Return a string representing the credential used to connect to the
        Workflow scheduler server.
        """
        return ""

    @abc.abstractmethod
    def _valid_credentials(
        self, credentials: typing.Dict[str, str]
    ) -> typing.Dict[str, str]:
        """Ensure that the credential provided by the user are valid."""
        return dict()

    def _notify_tree_roots(self):
        """Notify tree root changes to observers."""
        if self._tree_roots:
            self._notify(dict(tree_roots=self._tree_roots))

    @property
    def tree_roots(self) -> RootFlowNode:
        """The list of all the nodes at the root of the monitored suite."""
        if self._tree_roots is None:
            self._tree_roots = self._retrieve_tree_roots()
            self._notify_tree_roots()
        if self._tree_roots is None or len(self._tree_roots) == 0:
            raise RuntimeError(
                "Connexion to the server failed or suite={:s} does not exists/is empty".format(
                    self.suite
                )
            )
        return self._tree_roots

    def _set_tree_roots(self, value: RootFlowNode):
        """Register a new list of tree root nodes."""
        if value == self._tree_roots:
            logger.debug("Refresh has been done but no changes in tree roots.")
            self._tree_roots.touch()
        else:
            self._tree_roots = value
            self._notify_tree_roots()

    @abc.abstractmethod
    def _retrieve_tree_roots(self) -> RootFlowNode:
        """Retrieve the list of root nodes form the workflow scheduler server."""
        return RootFlowNode("", FlowStatus.ABORTED)

    def _notify_status(self, path: str):
        """Notify status changes to observers."""
        self._notify(dict(full_status=dict(path=path, node=self._full_statuses[path])))

    def in_cache(self, path: str) -> bool:
        """Check if a given **path** is already cached."""
        return path in self._full_statuses

    def full_status(self, path: str) -> RootFlowNode:
        """Return the full statuses tree for a given root node (**path**)."""
        if path not in self.tree_roots:
            raise ValueError(
                "The path base node {!s} is not in the tree roots list.".format(path)
            )
        if path not in self._full_statuses:
            logger.debug('Status for "%s" is not yet cached.', path)
            self._full_statuses[path] = self._retrieve_status(path)
            self._notify_status(path)
        return self._full_statuses[path]

    def _set_full_status(self, path, value: RootFlowNode):
        """Register new statuses for **path**."""
        if path in self._full_statuses and value == self._full_statuses[path]:
            logger.debug('Refresh has been done but no changes in "%s".', path)
            self._full_statuses[path].touch()
        else:
            if path in self._full_statuses:
                value.ingest_flagged(self._full_statuses[path].flagged_paths())
            self._full_statuses[path] = value
            self._notify_status(path)

    @abc.abstractmethod
    def _retrieve_status(self, path: str) -> RootFlowNode:
        """Retrieve the full statuses tree for the **path** root node."""
        return RootFlowNode("fake", FlowStatus.ABORTED)

    def refresh_tree_roots(self):
        """Refresh the list of root nodes."""
        if self.tree_roots.age > self.min_refresh_interval:
            self._set_tree_roots(self._retrieve_tree_roots())

    def refresh(self, path: str):
        """
        Refresh both the list of root nodes and the status for the **path**
        root node.
        """
        # Update the node's status
        logger.info('Status refresh requested by the user (for "%s").', path)
        if (
            path not in self._full_statuses
            or self._full_statuses[path].age >= self.min_refresh_interval
        ):
            self._set_full_status(path, self._retrieve_status(path))
        # Update tree roots...
        self.refresh_tree_roots()

    def _command_path_expand(
        self, root_node: FlowNode, paths: typing.List[str], with_suite: bool = True
    ) -> typing.List[str]:
        """Generate a list of **paths** starting at **root_node**."""
        radical = []
        if with_suite:
            radical.append(self.suite)
        root_node_full_path = root_node.full_path
        if root_node_full_path:
            radical.extend(root_node_full_path.split("/"))
        return ["/".join(radical + p.split("/")).rstrip("/") for p in paths]

    def command_gateway(
        self, command: str, root_node: FlowNode, paths: typing.List[str]
    ) -> str:
        """Launch **command** on the *paths* list of nodes."""
        logger.info('Calling the "%s" command on:\n  %s', command, "\n  ".join(paths))
        return getattr(self, "do_{:s}".format(command))(root_node, paths)

    @abc.abstractmethod
    def do_rerun(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """Actual implementation of the ``execute`` command."""
        pass

    @abc.abstractmethod
    def do_execute(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """Actual implementation of the ``execute`` command."""
        pass

    @abc.abstractmethod
    def do_suspend(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """Actual implementation of the ``suspend`` command."""
        pass

    @abc.abstractmethod
    def do_resume(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """Actual implementation of the ``resume`` command."""
        pass

    @abc.abstractmethod
    def do_complete(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """Actual implementation of the ``complete`` command."""
        pass

    @abc.abstractmethod
    def do_requeue(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """Actual implementation of the ``execute`` command."""
        pass

    @abc.abstractmethod
    def do_cancel(self, root_node: FlowNode, paths: typing.List[str]) -> str:
        """Actual implementation of the ``cancel`` command."""
        pass

    @property
    def logs(self):
        """Return the logs gateway object to be used with this FlowInterface.

        :note: ``None`` may be returned if no log access mechanism is implemented
               or available for a given FlowInterface.
        """
        if not self._logs_gateway_init:
            self._logs_gateway = self._logs_gateway_create()
            self._logs_gateway_init = True
        return self._logs_gateway

    @staticmethod
    def _logs_gateway_create() -> typing.Union[logs_gateway.LogsGateway, None]:
        """Create a LogGateway object (the first time it is requested).

        Implement this method in a concrete class
        """
        return None

    @abc.abstractmethod
    def node_info(self, node: FlowNode) -> typing.List[ExtraFlowNodeInfo]:
        """Return a bunch of information on a **node**.

        Such as try number, meters, limits, ...
        """
        pass

    @abc.abstractmethod
    def _actual_save_node_info(
        self, node: FlowNode, info: typing.List[ExtraFlowNodeInfo]
    ) -> str:
        """Save the modified information in a given **node**"""
        pass

    def save_node_info(
        self, node: FlowNode, info: typing.List[ExtraFlowNodeInfo]
    ) -> typing.Union[None, str]:
        """Save the information associated in a given **node**."""
        todo = [i for i in info if i.touched]
        if todo:
            return self._actual_save_node_info(node, todo)
        else:
            return None
