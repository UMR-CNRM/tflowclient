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
All the necessary `urwid`` based classes needed to build the user interface.

Here are a few pointers:

* A :class:`TFlowApplication` manages the whole application UI. A call to its
  ``run`` start the Urwid main loop (and therefore actually starts the UI).
* The :class:`TFlowApplication` object, build a :class:`TFlowMainView` object
  and displays it. The :class:`TFlowMainView` "view" object is responsible for
  displaying the main application's view (the tree that shows the various
  statuses of families and tasks).
* At some point, if requested by the user, a :class:`TFlowCommandView` view
  object might be created by the :class:`TFlowMainView` "view" object in order
  to prompt the user for a command to execute on the selected entries.
* The content of the "Tree" widget, is described by ad-hoc Urwid "Node"
  objects. See :class:`FamilyNode`, :class:`TaskNode` and :class:`EmptyNode`.
* The "Tree" widget is created using objects derived from the
  :class:`urwid.TreeWidget`classes. See :class:`AnyEntryWidget` and its
  descendants.

"""

from __future__ import annotations

import abc
import collections
import contextlib
from datetime import datetime, timedelta
import functools
import logging
import subprocess
import time
import typing

import urwid
import urwid.curses_display

from .conf import tflowclient_conf
from .flow import FlowInterface, FlowNode, RootFlowNode, FlowStatus, ExtraFlowNodeInfo
from .logs_gateway import LogsGatewayRuntimeError
from .observer import Observer

__all__ = ["TFlowApplication"]

logger = logging.getLogger(__name__)

_SERVER_WAIT_TEXT = urwid.Text(
    [("warning", "Please wait until the server responds...")]
)

_NO_SELECTED_NODE = urwid.Text(
    "No node is currently focused/selected. Please pick one."
)


# ------ Urwid Tree Widgets that help to build the statuses tree view ------


class AnyEntryWidget(urwid.TreeWidget, Observer):
    """Base class for any TreeWidget."""

    indent_cols = 2

    def __init__(
        self, node: AnyUrwidFlowNode, flow_node: FlowNode, cust_label: str = None
    ):
        """
        :param node: The node we are working on (as a Urwid Node class)
        :param flow_node:  The node we are working on (as a :class:`FlowNode` class)
        :param cust_label: A custom label used when displaying the node
        """
        # internal attributes...
        self._cust_label = cust_label
        self._flow_node = flow_node
        # insert an extra AttrWrap for our own use
        super().__init__(node)
        self._w = urwid.AttrWrap(self._w, None)
        self.update_w()
        # react to changes in the _flow_node
        self._flow_node.observer_attach(self)

    def update_obs_item(self, item: FlowNode, info: dict):
        """Deal with node's selection changes."""
        if isinstance(item, FlowNode) and "flagged" in info:
            self.update_w()

    def selectable(self) -> bool:
        """All statuses nodes are selectable."""
        return True

    def user_set_expanded(self, expanded):
        """Manually change the expanded attribute."""
        pass

    def keypress(self, size: typing.Tuple[int], key: str) -> typing.Union[str, None]:
        """allow subclasses to intercept keystrokes."""
        # Suppress the standard +/- behaviour
        if key not in ("+", "-", "right"):
            key = super().keypress(size, key)
        if key == "enter":
            self._flow_node.flagged = not self._flow_node.flagged
        else:
            return key

    def update_w(self):
        """Update the attributes of self._w based on the flow_node flagged property."""
        self._w.attr = ("flagged_" if self._flow_node.flagged else "") + "treeline"
        self._w.focus_attr = self._w.attr + "_f"

    def get_display_text(self) -> list:
        """The displayed text (including the status)."""
        label = self.get_display_label()
        return [
            (
                self._flow_node.status.name,
                "[{:s}]".format(self._flow_node.status.name[:3]),
            ),
            " ",
            label,
        ]

    def get_display_label(self) -> str:
        """The node's name."""
        return self._cust_label if self._cust_label else self.get_node().get_key()

    def reset_folding(self):
        """Reset the tree folding."""
        pass


class FamilyTreeWidget(AnyEntryWidget):
    """Widget for a family node."""

    def __init__(
        self, node: AnyUrwidFlowNode, flow_node: FlowNode, cust_label: str = None
    ):
        """
        :param node: The node we are working on (as a Urwid Node class)
        :param flow_node:  The node we are working on (as a :class:`FlowNode` class)
        :param cust_label: A custom label used when displaying the node
        """
        super().__init__(node, flow_node, cust_label=cust_label)

        self._folding_keystroke_ts = 0
        self.expanded = self._flow_node.user_expanded
        if self.expanded is None:
            self.expanded = self._flow_node.expanded
        self.update_expanded_icon()

    def reset_folding(self):
        """Reset the default tree folding."""
        self.expanded = self._flow_node.expanded
        del self._flow_node.user_expanded
        self.update_expanded_icon()

    def _recursive_expanded_reset(self, reset_root: AnyEntryWidget):
        """Recursively update the folding starting from *reset_root*."""
        my_node = reset_root.get_node()
        for c_key in my_node.get_child_keys():
            child_widget = my_node.get_child_widget(c_key)
            if isinstance(child_widget, FamilyTreeWidget):
                child_widget.user_set_expanded(self.expanded)
                self._recursive_expanded_reset(child_widget)

    def user_set_expanded(self, expanded):
        """Manually change the expanded attribute."""
        self.expanded = expanded
        self._flow_node.user_expanded = expanded
        self.update_expanded_icon()

    def keypress(self, size: typing.Tuple[int], key: str) -> typing.Union[str, None]:
        """allow subclasses to intercept keystrokes"""
        if key in " ":
            # Expand ...
            new_ts = time.monotonic()
            if (
                new_ts - self._folding_keystroke_ts
                < tflowclient_conf.double_keystroke_delay
            ):
                # Double space was hit...
                self.user_set_expanded(True)
                self._recursive_expanded_reset(self)
                self._folding_keystroke_ts = 0
            else:
                self.user_set_expanded(not self.expanded)
                self._folding_keystroke_ts = new_ts
            key = None
        else:
            key = super().keypress(size, key)
        return key


class TaskTreeWidget(AnyEntryWidget):
    """Widget for a task node."""

    def get_display_text(self) -> list:
        """The displayed text (including the status)."""
        return [" " * self.indent_cols] + super().get_display_text()


class EmptyWidget(urwid.TreeWidget):
    """A marker for an expanded family with no contents."""

    def get_display_text(self) -> str:
        """The displayed text."""
        return "(empty directory)"


# ------ Urwid nodes that will be displayed in the Tree widget ------


class FamilyNode(urwid.ParentNode):
    """Metadata storage for families."""

    def __init__(self, flow_node: FlowNode, path: str, parent: FamilyNode = None):
        """
        :param flow_node: The FlowNode we are working on.
        :param path: The full path to the node.
        :param parent: The parent node (as a Urwid node).
        """
        self.flow_node = flow_node
        if path == "":
            depth = 0
            key = None
        else:
            depth = path.count("/") + 1
            key = path.split("/")[-1]
        self._c_keys = collections.OrderedDict()
        super().__init__(path, key=key, parent=parent, depth=depth)

    def load_parent(self) -> FamilyNode:
        """Create the parent node."""
        s_path = self.get_value().split("/")
        parent_name = "/".join(s_path[:-1])
        parent = FamilyNode(self.flow_node.parent, parent_name)
        parent.set_child_node(self.get_key(), self)
        return parent

    def load_child_keys(self) -> typing.List[typing.Union[None, str]]:
        """The list of children tags (so-called keys in Urwid terminology)."""
        self._c_keys = collections.OrderedDict()
        for c in self.flow_node:
            self._c_keys[c.name] = c
        if len(self._c_keys) == 0:
            depth = self.get_depth() + 1
            self._children[None] = EmptyNode("", parent=self, key=None, depth=depth)
            return [None]
        else:
            return list(self._c_keys.keys())

    def load_child_node(self, key: str) -> AnyUrwidFlowNode:
        """Create a the Urwid child node object based on the key."""
        """Return either a FileNode or DirectoryNode"""
        if key is None:
            return EmptyNode("")
        else:
            cf_node = self._c_keys[key]
            c_path = (self.get_value() + "/" if self.get_value() else "") + key
            if len(cf_node):
                return FamilyNode(cf_node, c_path, parent=self)
            else:
                return TaskNode(cf_node, c_path, parent=self)

    def load_widget(self) -> FamilyTreeWidget:
        """Load the Urwid widget for self."""
        if self.get_value():
            return FamilyTreeWidget(self, self.flow_node)
        else:
            return FamilyTreeWidget(
                self, self.flow_node, cust_label=self.flow_node.name
            )

    def reset_folding_iter(self):
        """Recursively collapse all children nodes."""
        self.get_widget().reset_folding()
        for c_key in self.get_child_keys():
            self.get_child_node(c_key).reset_folding_iter()

    def reset_folding(self):
        """Collapse all node (starting from the top of the tree)."""
        parent = self.get_parent()
        if parent:
            parent.reset_folding()
        else:
            self.reset_folding_iter()


class TaskNode(urwid.TreeNode):
    """Metadata storage for individual tasks"""

    def __init__(self, flow_node: FlowNode, path: str, parent: FamilyNode):
        """
        :param flow_node: The FlowNode we are working on.
        :param path: The full path to the node.
        :param parent: The parent node (as a Urwid node).
        """
        depth = path.count("/") + 1
        key = path.split("/")[-1]
        self.flow_node = flow_node
        urwid.TreeNode.__init__(self, path, key=key, parent=parent, depth=depth)

    def load_widget(self) -> TaskTreeWidget:
        """Load the Urwid widget for self."""
        return TaskTreeWidget(self, self.flow_node)

    def reset_folding_iter(self):
        """Nothing to collapse here."""
        pass

    def reset_folding(self):
        """Collapse all node (starting from the top of the tree)."""
        parent = self.get_parent()
        if parent:
            parent.reset_folding()


class EmptyNode(urwid.TreeNode):
    """Metadata storage for empty families markers."""

    def __init__(self, path: str, parent=None, key=None, depth=None):
        """Just add a fake flow_node attribute."""
        self.flow_node = None
        urwid.TreeNode.__init__(self, path, key=key, parent=parent, depth=depth)

    def load_widget(self) -> EmptyWidget:
        """Load the Urwid widget for self."""
        return EmptyWidget(self)

    def reset_folding(self):
        """Nothing to collapse here."""
        pass


#: Type for any of the Urwid nodes
AnyUrwidFlowNode = typing.Union[FamilyNode, TaskNode, EmptyNode]


# ------ Our very own implementation of some Urwid widgets ------


class TFlowTreeListBox(urwid.TreeListBox):
    """A TreeListBow widget dedicated to the TFlowApplication."""

    def __init__(
        self,
        void_node: AnyUrwidFlowNode,
        actual_node: AnyUrwidFlowNode,
        mainloop: urwid.MainLoop,
    ):
        """
        :param void_node: The Tree that will be displayed when updating
        :param actual_node: The Tree that is displayed most of the time
        :param mainloop: The Urwid's MainLoop object
        """
        self._void_walker = urwid.TreeWalker(void_node)
        self._void_display = False
        self._actual_node = actual_node
        self._actual_walker = urwid.TreeWalker(self._actual_node)
        self._mainloop = mainloop
        super().__init__(self._actual_walker)

    @property
    def actual_node(self) -> AnyUrwidFlowNode:
        """The Urwid node currently being displayed in the widget."""
        return self._actual_node

    @actual_node.setter
    def actual_node(self, value: AnyUrwidFlowNode):
        """Set the Urwid node being displayed in the widget."""
        self._actual_node = value
        self._actual_walker = urwid.TreeWalker(self._actual_node)
        if not self._void_display:
            self.body = self._actual_walker

    @property
    def actual_walker(self) -> urwid.TreeWalker:
        """The Urwid's TreeWalker currently in use."""
        return self._actual_walker

    @contextlib.contextmanager
    def temporary_void_display(self, condition: bool = True):
        """If **condition**, display the void Tree will inside the content manager."""
        if condition and not self._void_display:
            self._void_display = True
            self.body = self._void_walker
            self._mainloop.draw_screen()
            yield
            self.body = self._actual_walker
            self._void_display = False
        else:
            yield

    def keypress(self, size: typing.Tuple[int], key: str) -> typing.Union[str, None]:
        """Do not use left/right keys (they are useful to jump between columns)."""
        if key in ("left", "right"):
            return key
        else:
            return super().keypress(size, key)


class TFlowLongTextWidget(urwid.ListBox):
    """A scroll-able text-area."""

    def __init__(self, textlist: typing.Iterable[str]):
        """
        :param textlist: The list of strings to be displayed.
        """
        super().__init__(urwid.SimpleListWalker([urwid.Text(t) for t in textlist]))


class KeyCaptureWrapper(urwid.WidgetWrap):
    """Capture key strokes and call the current view ``keypress_hook`` callback on them."""

    def __init__(
        self, w: urwid.Widget, current_view: TFlowAbstractView, propagate: bool = True
    ):
        """
        :param w: The wrapped widget
        :param current_view:  The current view object (that must have a
                              ``keypress_hook`` callback)
        :param propagate: Call keypress on the wrapped widget depending on the
                          ``keypress_hook`` result
        """
        self._current_view = current_view
        self._propagate = propagate
        super().__init__(w)

    def selectable(self) -> bool:
        """Must be selectable to capture key strokes."""
        return True

    # noinspection PyCallingNonCallable
    def keypress(self, size: typing.Tuple[int], key: str) -> typing.Union[str, None]:
        """Divert key strokes to the ``keypress_hook`` method."""
        key = self._current_view.keypress_hook(key)
        if key and hasattr(self._w, "keypress") and self._propagate:
            return self._w.keypress(size, key)
        else:
            return key


# ------ Views are custom object that handle a given layout of the UI ------


class TFlowAbstractView(metaclass=abc.ABCMeta):
    """Any tflowclient views must inherit from this class"""

    footer_add_quit = True
    footer_text = []

    def __init__(self, flow_object: FlowInterface, app_object: TFlowApplication):
        """
        Any view must have ``header``, ``footer`` and ``main_content`` attribute.
        They will be used to build a Frame widget.

        :param flow_object: The :class:`FlowInterface` object currently being used
        :param app_object: The application object
        """
        super().__init__()
        self.flow = flow_object
        self.app = app_object
        self.header = urwid.Text("")
        self.header_update()
        self.footer = None
        self.footer_update()
        self.main_content = None

    def switch_in_hook(self):
        """Called each time this view is shown."""
        pass

    def switch_post_in_hook(self):
        """Called each time this view has been shown."""
        pass

    def switch_out_hook(self):
        """Called each time this view is hidden."""
        pass

    def header_update(self, extra: str = ""):
        """Update the header text (given any **extra** information)."""
        self.header.set_text("tCDP for {!s}. {:s}".format(self.flow, extra))

    def footer_update(self, *extras: list):
        """Update the footer text given a list of command extended by **extras**."""
        txt_pile = []
        for extra in extras:
            txt_pile.append(urwid.Text(extra))
        for extra in self.footer_text:
            txt_pile.append(urwid.Text(extra))
        if self.footer_add_quit:
            txt_pile.append(urwid.Text([("key", "Q"), ": Quit"]))
        max_len = max([len(t.text) for t in txt_pile]) if txt_pile else 1
        if self.footer is None:
            self.footer = urwid.GridFlow(
                txt_pile, max_len, h_sep=1, v_sep=0, align="left"
            )
        else:
            self.footer.contents = [(t, self.footer.options()) for t in txt_pile]
            self.footer.cell_width = max_len

    def keypress_hook(self, key: str) -> typing.Union[str, None]:
        """Leveraged when used with a :class:`KeyCaptureWrapper` wrapper."""
        return key


class TFlowAbstractCommandView(TFlowAbstractView):
    """Common things for views that launch commands."""

    def __init__(
        self,
        flow_object: FlowInterface,
        app_object: TFlowApplication,
        root_node: typing.Union[FlowNode, None],
        selected: typing.List[str],
    ):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        :param root_node: The FlowNode from which the path are computed
        :param selected: This list of selected items (the command will be
                        executed on them)
        """
        super().__init__(flow_object, app_object)
        self.root_node = root_node
        self.selected = selected
        self._todo = None
        if self.root_node is not None and self.selected:
            self.pile = urwid.Pile([])
            self.main_content = KeyCaptureWrapper(self.pile, current_view=self)
            self._with_selected_init()
        else:
            # Display the "error" message, then go back
            self.main_content = KeyCaptureWrapper(
                urwid.Filler(_NO_SELECTED_NODE), current_view=self, propagate=False
            )
            self.footer_update([("key", "ESC/BACKSPACE"), ": back to statuses"])
        self.main_content = urwid.Padding(self.main_content, left=1, right=1)

    @abc.abstractmethod
    def _with_selected_init(self):
        """Create the main_content (when the list of selected items is populated)."""
        raise NotImplementedError()

    @property
    def selected_text_container(self) -> TFlowLongTextWidget:
        """The display widget for the list of selected nodes."""
        radical = [
            self.flow.suite,
        ]
        if self.root_node.full_path:
            radical.extend(self.root_node.full_path.split("/"))
        return TFlowLongTextWidget(
            ["", "Selected nodes:"]
            + ["/" + "/".join(radical + s.split("/")).strip("/") for s in self.selected]
        )

    def _do_command(self, command: str):
        """Launch **command** and display the result."""
        self._todo = command
        # Ok. Just wait...
        wait = urwid.Text(
            (
                "warning",
                "\n\nPlease wait will the {:s} command is being issued...".format(
                    command
                ),
            )
        )
        self.pile.contents = [(urwid.Filler(wait), ("weight", 1))]
        self.footer_update()
        self.app.loop.draw_screen()
        # Display the result and wait for statuses to be refreshed
        summary = self.flow.command_gateway(command, self.root_node, self.selected)
        text_container = TFlowLongTextWidget(
            ['Result for the "{:s}" command:'.format(command)] + summary.split("\n")
        )
        wait = urwid.Text(
            ("warning", "Please wait will the statuses are being refreshed...")
        )
        self.pile.contents = [
            (text_container, ("weight", 1)),
            (urwid.Divider(), ("pack", 1)),
            (wait, ("pack", 1)),
            (urwid.Divider(), ("pack", 1)),
        ]
        self.footer_update()
        self.app.loop.draw_screen()
        self._do_post_command_update()
        # We are done with waiting
        wait.set_text("")
        self.footer_update([("key", "ESC/ENTER/BACKSPACE"), ": back to statuses"])

    def keypress_hook(self, key: str) -> typing.Union[str, None]:
        """Handle key strokes."""
        if self.selected and self._todo is None:
            key = self._selected_keypress_hook(key)
        if key in ("esc", "backspace"):
            self.app.switch_view(self.app.main_view)
        elif self._todo is not None and key == "enter":
            self.app.switch_view(self.app.main_view)
        else:
            return key

    @abc.abstractmethod
    def _do_post_command_update(self):
        raise NotImplementedError

    @abc.abstractmethod
    def _selected_keypress_hook(self, key: str) -> typing.Union[str, None]:
        raise NotImplementedError


class TFlowCommandView(TFlowAbstractCommandView):
    """The view that is triggered when the user chooses to launch a command."""

    #: (Command Display Name, Keyboard Shortcut, Command name in flow.py)
    available_commands = [
        ("Rerun", "$", "rerun"),
        ("Execute", "E", "execute"),
        ("Suspend", "S", "suspend"),
        ("Resume", "R", "resume"),
        ("Complete", "C", "complete"),
        ("Requeue", "0", "requeue"),
    ]

    def __init__(
        self,
        flow_object: FlowInterface,
        app_object: TFlowApplication,
        root_node: typing.Union[RootFlowNode, None],
    ):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        :param root_node: The current active root FlowNode
        """
        # List of selected lines (append the suite name to be compatible with flow
        # schedulers tree)
        if root_node is not None:
            selected = root_node.flagged_paths()
            if not selected:
                # Try to use the focused_node
                if root_node.focused is not None:
                    selected = [root_node.focused.path]
            super().__init__(flow_object, app_object, root_node, selected)
        else:
            super().__init__(flow_object, app_object, root_node, [])

    def _with_selected_init(self):
        """Prompt the user to choose a command."""
        self.pile.contents = [
            (self.selected_text_container, ("weight", 1)),
            (urwid.Divider(), ("pack", 1)),
            (urwid.Text("Available commands:"), ("pack", 1)),
            (self._commands_grid(), ("pack", 1)),
            (urwid.Divider(), ("pack", 1)),
        ]
        self.pile.focus_position = 0
        self.footer_update(
            [
                (
                    "key",
                    "/".join([av_c[1] for av_c in self.available_commands if av_c[1]]),
                ),
                ": launch the command",
            ],
            [("key", "ESC/BACKSPACE"), ": back to statuses"],
        )

    def _do_command(self, command: str):
        """Launch **command** and display the result."""
        # Once the command has been executed, unselect everything
        self.root_node.reset_flagged()
        # Go...
        super()._do_command(command)

    def _commands_grid(self) -> urwid.GridFlow:
        """Generate the list of Urwid buttons associated with each of the commands."""
        buttons = []
        label_sizes = []
        for av_c in self.available_commands:
            label = "[{1:s}] {0:s}".format(*av_c)
            label_sizes.append(len(label))
            buttons.append(
                urwid.AttrWrap(
                    urwid.Button(
                        label, on_press=self._button_pressed, user_data=av_c[2]
                    ),
                    "button",
                    "button_f",
                )
            )
        return urwid.GridFlow(
            buttons, cell_width=max(label_sizes) + 4, h_sep=2, v_sep=0, align="left"
        )

    def _button_pressed(self, button: urwid.Button, user_data: str):
        """Triggered when a button is pressed."""
        assert isinstance(button, urwid.Button)
        self._do_command(user_data)

    def _do_post_command_update(self):
        self.flow.refresh(self.root_node.name, force=True)

    def _selected_keypress_hook(self, key: str) -> typing.Union[str, None]:
        for av_c in self.available_commands:
            if av_c[1] and key.upper() == av_c[1]:
                self._do_command(av_c[2])
                return
        return key


class TFlowCancelCommandView(TFlowAbstractCommandView):
    """The view that is triggered when the user chooses to launch a command."""

    def __init__(
        self,
        flow_object: FlowInterface,
        app_object: TFlowApplication,
        selected_nodes: typing.Iterable[RootFlowNode],
    ):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        :param selected_nodes: The selected root nodes
        """
        selected = [s_node.full_path for s_node in selected_nodes]
        super().__init__(flow_object, app_object, flow_object.tree_roots, selected)

    def _with_selected_init(self):
        # Ask for confirmation
        self.pile.contents = [
            (self.selected_text_container, ("weight", 1)),
            (urwid.Divider(), ("pack", 1)),
            (urwid.Text(("warning", "Hit 'C' to Cancel all these nodes")), ("pack", 1)),
            (urwid.Divider(), ("pack", 1)),
        ]
        self.pile.focus_position = 0
        self.footer_update(
            [("key", "C"), ": Cancel nodes"],
            [("key", "ESC/BACKSPACE"), ": back to statuses"],
        )

    def _do_post_command_update(self):
        self.flow.refresh_tree_roots(force=True)

    def _selected_keypress_hook(self, key: str) -> typing.Union[str, None]:
        if key in ("c", "C"):
            self._do_command("cancel")
        return key


class TFlowLogsView(TFlowAbstractView):
    """The view that is triggered when the user chooses to browse the log files."""

    footer_text = [[("key", "ESC/BACKSPACE"), ": back to statuses"]]

    def __init__(
        self,
        flow_object: FlowInterface,
        app_object: TFlowApplication,
        root_node: typing.Union[RootFlowNode, None],
    ):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        :param root_node: The current active root FlowNode
        """
        super().__init__(flow_object, app_object)
        self.focused_node = None
        self.focused_path = None
        self.buttons = []
        if root_node is not None:
            self.focused_node = root_node.focused
            if self.focused_node is not None:
                self.focused_path = self.focused_node.full_path
        if self.focused_path is None:
            self.text_container = _NO_SELECTED_NODE
        elif len(self.focused_node):
            self.text_container = urwid.Text(
                "The focused node (/{:s}/{:s}) is not a leaf node (i.e. a Task).".format(
                    self.flow.suite, self.focused_path
                )
            )
        else:
            try:
                av_listings = self.flow.logs.list_file(self.focused_path)
            except LogsGatewayRuntimeError as e:
                # This step may fail (network problems, ...)
                self.text_container = urwid.Text(
                    [
                        (
                            "warning",
                            "An un-expected error occurred while fetching the "
                            + "list of available log files:\n{!s}".format(e),
                        )
                    ]
                )
                logger.error(
                    "Error while fetching log files list for path '/%s/%s':\n%s",
                    self.flow.suite,
                    self.focused_path,
                    e,
                )
            else:
                if av_listings:
                    self.text_container = urwid.Text(
                        "For node: /{:s}/{:s}\n\nThe available log files are:\n".format(
                            self.flow.suite, self.focused_path
                        )
                    )
                    cur_time = datetime.utcnow()
                    for listing in av_listings:
                        l_label = "{:s} ({!s} ago)".format(
                            listing[0].split("/")[-1],
                            timedelta(
                                seconds=(
                                    (cur_time - listing[1]) // timedelta(seconds=1)
                                )
                            ),
                        )
                        self.buttons.append(
                            urwid.AttrWrap(
                                urwid.Button(
                                    l_label,
                                    on_press=self._button_pressed,
                                    user_data=listing[0],
                                ),
                                "button",
                                "button_f",
                            )
                        )
                else:
                    self.text_container = urwid.Text(
                        "No log files are available for:\n/{:s}/{:s}".format(
                            self.flow.suite, self.focused_path
                        )
                    )
        if self.buttons:
            self.pile = urwid.Pile(
                [
                    urwid.Filler(self.text_container, valign="bottom"),
                    urwid.ListBox(urwid.SimpleFocusListWalker(self.buttons)),
                ]
            )
            self.main_content = KeyCaptureWrapper(self.pile, current_view=self)
            self.footer_update([("key", "ENTER/SPACE"), ": view the selected file"])
        else:
            self.main_content = KeyCaptureWrapper(
                urwid.Filler(self.text_container), current_view=self, propagate=False
            )
        self.main_content = urwid.Padding(self.main_content, left=1, right=1)

    def _button_pressed(self, button: urwid.Button, log_listing: str):
        """Triggered when a button is pressed (e.g. when a log file is chosen)."""
        assert isinstance(button, urwid.Button)
        try:
            with self.flow.logs.get_as_file(self.focused_path, log_listing) as f_obj:
                subprocess.check_call(
                    [
                        s.format(filename=f_obj.name)
                        for s in tflowclient_conf.logviewer_command
                    ]
                )
        except LogsGatewayRuntimeError as e:
            # This step may fail (network problems, ...)
            self.text_container.set_text(
                [
                    (
                        "warning",
                        'An error occurred while fetching the "{:s}" listing: {!s}'.format(
                            log_listing, e
                        ),
                    ),
                    "\n\n",
                    self.text_container.text,
                ]
            )
            logger.error(
                "Error while fetching '%s' for path '/%s/%s':\n%s",
                log_listing,
                self.flow.suite,
                self.focused_path,
                e,
            )
        # Redraw the whole screen (because, vim will have messed things up...)
        self.app.loop.screen.clear()

    def keypress_hook(self, key: str) -> typing.Union[str, None]:
        """Handle key strokes."""
        if key in ("esc", "backspace"):
            self.app.switch_view(self.app.main_view)
        else:
            return key


class TFlowInfoView(TFlowAbstractView):
    """The view that is triggered when the user requests extra information."""

    def __init__(
        self,
        flow_object: FlowInterface,
        app_object: TFlowApplication,
        visited_node: typing.Union[FlowNode, None],
        read_only: bool = False,
    ):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        :param visited_node: The current FlowNode
        :param read_only: Do not allow any change
        """
        self.footer_add_quit = False
        super().__init__(flow_object, app_object)
        self._visited_node = visited_node
        self._read_only = read_only
        self._info = []
        self._result = False
        # Wait screen...
        self.wait = urwid.Filler(_SERVER_WAIT_TEXT)
        if self._visited_node is not None:
            self.pile = urwid.Pile([self.wait])
        else:
            self.pile = urwid.Pile([urwid.Filler(_NO_SELECTED_NODE)])
        x_pile = KeyCaptureWrapper(self.pile, current_view=self)
        self.main_content = urwid.Padding(x_pile, left=1, right=1)

    # noinspection PyTypeChecker
    def switch_post_in_hook(self):
        """Fetch the data and display it."""
        if self._visited_node is None:
            self._refresh_footer()
            return
        # make the wait screen pop up
        self.app.loop.draw_screen()
        # Actually fetch the data
        self._info = self.flow.node_info(self._visited_node)
        self._refresh_footer()
        sorted_info = collections.defaultdict(list)
        for a_info in self._info:
            sorted_info[a_info.kind].append(a_info)
        # Create associated widgets
        to_pile_up = list()
        for kind, info in sorted(sorted_info.items()):
            to_pile_up.append(urwid.Divider())
            to_pile_up.append(urwid.Text(("title", kind.upper() + ":")))
            for item in info:
                caption = "- {:s}".format(item.name)
                if item.editable and not self._read_only:
                    edit_w = urwid.Edit(edit_text=item.value)
                    urwid.connect_signal(
                        edit_w,
                        "postchange",
                        functools.partial(self._update_value, item),
                    )
                    to_pile_up.append(
                        urwid.Columns(
                            [
                                ("pack", urwid.Text(caption + " = ")),
                                urwid.AttrWrap(edit_w, "editable", "editable_f"),
                            ]
                        )
                    )
                else:
                    to_pile_up.append(
                        urwid.Text(
                            caption + ("" if item.value is None else " = " + item.value)
                        )
                    )
                if item.description:
                    to_pile_up.append(urwid.Text("  # ({:s})".format(item.description)))
        if to_pile_up:
            to_pile_up.insert(
                0,
                urwid.Text(
                    "Node information for /{:s}/{:s}".format(
                        self.flow.suite, self._visited_node.full_path
                    )
                ),
            )
            to_pile_up.insert(0, urwid.Divider())
        else:
            to_pile_up = [ExtraFlowNodeInfo("info", "Nothing to be displayed...")]
        self.pile.contents = [
            (urwid.ListBox(urwid.SimpleListWalker(to_pile_up)), ("weight", 1))
        ]

    @property
    def touched(self):
        """Tells whether some of the fields have changed."""
        return any([i.touched for i in self._info])

    def _refresh_footer(self):
        """Add the entry related to "ENTER" only when sensible."""
        if self._visited_node is None:
            todo = [[("key", "ESC/BACKSPACE"), ": back to statuses"]]
        elif self._read_only:
            todo = [[("key", "ESC/ENTER/BACKSPACE"), ": back to statuses"]]
        else:
            todo = [[("key", "ESC"), ": back to statuses"]]
        if self.touched:
            todo.append([("key", "ENTER"), ": save & go back"])
        self.footer_update(*todo)

    def _update_value(
        self, item: ExtraFlowNodeInfo, widget: urwid.Edit, old_value: str
    ):
        assert isinstance(old_value, str)
        item.value = widget.edit_text
        self._refresh_footer()

    def keypress_hook(self, key: str) -> typing.Union[str, None]:
        """Handle key strokes."""
        if self._result:
            # Results are currently being displayed
            if key in ("esc", "enter", "backspace"):
                self.app.switch_view(self.app.main_view)
            else:
                return key
        else:
            # Main display ...
            if key == "esc" or (key == "backspace" and self._visited_node is None):
                self.app.switch_view(self.app.main_view)
            elif key in ("enter", "backspace") and self._read_only:
                self.app.switch_view(self.app.main_view)
            elif key == "enter" and self.touched:
                # This may take a while: display a message
                self.footer_add_quit = True
                self.footer_update()
                self.pile.contents = [(self.wait, ("weight", 1))]
                self.app.loop.draw_screen()
                # Actually save the results
                self._result = self.flow.save_node_info(self._visited_node, self._info)
                if self._result:
                    # Display the result
                    self.footer_update(
                        [("key", "ESC/ENTER/BACKSPACE"), ": back to statuses"]
                    )
                    self.pile.contents = [
                        (
                            TFlowLongTextWidget(
                                ["", "Output received when changing the settings:", ""]
                                + self._result.split("\n")
                            ),
                            ("weight", 1),
                        )
                    ]
                else:
                    self.app.switch_view(self.app.main_view)
            else:
                return key


class TFlowQuitView(TFlowAbstractView):
    """The view that is triggered when the user wants to quit the application."""

    def __init__(self, flow_object: FlowInterface, app_object: TFlowApplication):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        """
        super().__init__(flow_object, app_object)
        # the frame that will display the message and buttons
        frame = urwid.Frame(urwid.Filler(urwid.Divider(), "top"), focus_part="footer")
        frame.header = urwid.Pile(
            [urwid.Text("Are you sure you want to quit?"), urwid.Divider()]
        )
        # pad area around the frame
        w = urwid.Padding(frame, ("fixed left", 2), ("fixed right", 2))
        w = urwid.Filler(w, ("fixed top", 1), ("fixed bottom", 1))
        w = urwid.Padding(w, "center", 25)
        w = urwid.Filler(w, "middle", 6)
        self.main_content = w
        # Add the Yes/No buttons
        self._inner_g_flow = urwid.GridFlow(
            [
                urwid.AttrWrap(
                    urwid.Button(name, self.button_press), "button", "button_f"
                )
                for name in ("Yes", "No")
            ],
            cell_width=7,
            h_sep=3,
            v_sep=1,
            align="center",
        )
        frame.footer = urwid.Pile([urwid.Divider(), self._inner_g_flow], focus_item=1)
        # Where to go back if the user answers No ?
        self.previous_view = None

    def switch_in_hook(self):
        """Record the previous view and focus the Yes answer."""
        self.previous_view = self.app.current_view
        self._inner_g_flow.focus_position = 0

    def switch_out_hook(self):
        """Forget about the previous view."""
        self.previous_view = None

    def button_press(self, button: urwid.Button):
        """Exit or go back to the previous view."""
        if button.label == "Yes":
            raise urwid.ExitMainLoop
        else:
            self.app.switch_view(self.previous_view)

    def footer_update(self, *extras: list):
        """Empty the footer text."""
        self.footer = urwid.GridFlow([], 1, h_sep=2, v_sep=0, align="left")


class TFlowCancelMainView(TFlowAbstractView, Observer):
    """The application' main view (statuses tree)."""

    footer_text = [
        [("key", "ENTER/SPACE"), ": Select/Un-select"],
        [("key", "U"), ": Un-select all"],
        [("key", "R"), ": Refresh list"],
        [("key", "I"), ": Node Info"],
        [("key", "C"), ": Cancel selected"],
    ]

    timer_interval = 1

    def __init__(self, flow_object: FlowInterface, app_object: TFlowApplication):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        """
        super().__init__(flow_object, app_object)
        # Populate the root nodes list and display the first item in the tree widget
        self._timer = None
        # The wait screen...
        self.main_wait = KeyCaptureWrapper(
            urwid.Padding(urwid.Filler(_SERVER_WAIT_TEXT), left=1, right=1),
            current_view=self,
        )
        # Create the appropriate layout (root nodes on the left, tree on the right)
        self.grid_flow = urwid.GridFlow(
            cells=[], cell_width=8, h_sep=1, v_sep=0, align="left"
        )
        self.main_frame = KeyCaptureWrapper(
            urwid.Frame(
                urwid.Filler(self.grid_flow),
                header=urwid.Pile(
                    [
                        urwid.Divider(),
                        urwid.Text("Select the experiment(s) you want to cancel:"),
                    ]
                ),
            ),
            current_view=self,
        )
        self.update_flow_roots()
        # Start monitoring changes in the FlowInterface
        self.flow.observer_attach(self)
        # Ok, jump to the main view
        self.main_content = self.main_frame

    @contextlib.contextmanager
    def temporary_wait_display(self, condition: bool = True):
        """If **condition**, display the void Tree will inside the content manager."""
        if condition and self.main_content is not self.main_wait:
            self.main_content = self.main_wait
            self.app.loop.draw_screen()
            yield
            self.main_content = self.main_frame
        else:
            yield

    def update_obs_item(self, item: FlowInterface, info: dict):
        """Listen to the FlowInterface and update the UI accordingly"""
        if "tree_roots" in info:
            logger.debug('Tree root change notified by "%r"', item)
            self.update_flow_roots()

    def keypress_hook(self, key: str) -> typing.Union[str, None]:
        """Handle key strokes."""
        if key in ("i", "I"):
            self.info_dialog()
        elif key in ("c", "C"):
            self.cancel_dialog()
        elif key in ("u", "U"):
            logger.debug("Global un-select triggered by user.")
            for c_box in self.grid_flow.contents:
                c_box[0].state = False
        elif key in ("r", "R"):
            with self.temporary_wait_display():
                self.flow.refresh_tree_roots()
        else:
            return key

    @property
    def focused_node_name(self) -> typing.Union[str, None]:
        """The name of the selected."""
        focused = self.grid_flow.focus
        return None if focused is None else focused.label

    @property
    def focused_node(self) -> typing.Union[FlowNode, None]:
        """The object representing the selected node."""
        return (
            None
            if self.focused_node_name is None
            else self.flow.tree_roots[self.focused_node_name]
        )

    @property
    def selected_nodes_names(self) -> typing.Iterable[str]:
        """The names of the selected nodes."""
        return [c[0].label for c in self.grid_flow.contents if c[0].state]

    @property
    def selected_nodes(self) -> typing.Iterable[RootFlowNode]:
        """The object representing the selected nodes."""
        return [self.flow.tree_roots[n] for n in self.selected_nodes_names]

    def update_flow_roots(self):
        """Update the list of root nodes (aka Tree roots)."""
        # Stop any previous age updater
        if self._timer is not None:
            logger.debug("Cancelling active timer: %s", self._timer)
            self.app.loop.remove_alarm(self._timer)
            self.header_update()
            self._timer = None
        # Update the root nodes list
        g_flow_focused = self.focused_node_name
        g_flow_checked = set(self.selected_nodes_names)
        g_flow_opts = self.grid_flow.options()
        self.grid_flow.contents.clear()
        self.grid_flow.contents.extend(
            [
                (urwid.CheckBox((tr.status.name, tr.name)), g_flow_opts)
                for tr in sorted(self.flow.tree_roots, key=lambda tr: tr.name)
            ]
        )
        self.grid_flow.cell_width = 4 + max(
            [len(tr.name) for tr in self.flow.tree_roots]
        )
        # Preserve the focused/checked node
        for i_box, c_box in enumerate(self.grid_flow.contents):
            if c_box[0].label == g_flow_focused:
                self.grid_flow.set_focus(i_box)
            if c_box[0].label in g_flow_checked:
                c_box[0].state = True
        if g_flow_focused is None or g_flow_focused not in self.flow.tree_roots:
            self.grid_flow.set_focus(0)
        self._timer = self.app.loop.set_alarm_in(
            self.timer_interval, self.age_auto_update
        )
        logger.debug("Timer for age update is: %s", self._timer)

    # noinspection PyUnusedLocal
    def age_auto_update(self, current_loop: urwid.MainLoop, user_data=None):
        """Increment the root Node age."""
        self._timer = None
        self.header_update(
            "Information is {:.0f} seconds old.".format(self.flow.tree_roots.age)
        )
        self._timer = current_loop.set_alarm_in(
            self.timer_interval, self.age_auto_update
        )

    def info_dialog(self):
        """Open the info view dialog"""
        logger.debug('Info dialog requested by user on "%s".', self.focused_node_name)
        l_view = TFlowInfoView(self.flow, self.app, self.focused_node, read_only=True)
        self.app.switch_view(l_view)

    def cancel_dialog(self):
        """Open the info view dialog"""
        logger.debug("Cancel dialog requested by user.")
        l_view = TFlowCancelCommandView(self.flow, self.app, self.selected_nodes)
        self.app.switch_view(l_view)


class TFlowMainView(TFlowAbstractView, Observer):
    """The application' main view (statuses tree)."""

    footer_text = [
        [("key", "SPACE"), ": Fold/Unfold"],
        [("key", "2xSPACE"), ": Recurs. Unfold"],
        [("key", "D"), ": Default Folding"],
        [("key", "F"), ": Fold 1st Level"],
        [("key", "R"), ": Refresh"],
        [("key", "ENTER"), ": Select"],
        [("key", "A"), ": Select Aborted"],
        [("key", "U"), ": Un-select all"],
        [("key", "C"), ": Launch Command"],
        [("key", "I"), ": Node Info"],
    ]

    recent_roots_threshold = 3 * 3600

    timer_interval = 1

    def __init__(self, flow_object: FlowInterface, app_object: TFlowApplication):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        """
        if flow_object.logs is not None:
            self.footer_text += [[("key", "L"), ": Access Logs"]]
        super().__init__(flow_object, app_object)
        # Create the "Tree" widget
        void_node = FamilyNode(
            RootFlowNode(
                "Please wait (it might take some time to query the server)...",
                FlowStatus.UNKNOWN,
            ),
            "",
        )
        self.listbox = TFlowTreeListBox(void_node, void_node, mainloop=self.app.loop)
        # Display the various root nodes
        self.roots_walker = urwid.SimpleFocusListWalker([])
        self._roots_hits = dict()  # Keep track of root nodes last access time
        # Current active root node
        self._active_root = None
        self._active_root_timer = None
        # Populate the root nodes list and display the first item in the tree widget
        self.update_flow_roots()
        # Create the appropriate layout (root nodes on the left, tree on the right)
        self.main_columns = urwid.Columns(
            [
                (
                    4 + max([len(r.name) for r in self.flow.tree_roots]),
                    urwid.ListBox(self.roots_walker),
                ),
                self.listbox,
            ],
            dividechars=2,
        )
        self.main_content = KeyCaptureWrapper(self.main_columns, current_view=self)
        # Start monitoring changes in the FlowInterface
        self.flow.observer_attach(self)

    def update_obs_item(self, item: FlowInterface, info: dict):
        """Listen to the FlowInterface and update the UI accordingly"""
        if "tree_roots" in info:
            logger.debug('Tree root change notified by "%r"', item)
            self.update_flow_roots()
        if "full_status" in info:
            path = info["full_status"]["path"]
            logger.debug('Status change notified by "%r" for "%s"', item, path)
            if path == self.active_root:
                self.update_tree(self.active_root)

    @property
    def active_root(self) -> str:
        """The name of the current active root node."""
        return self._active_root

    @active_root.setter
    def active_root(self, value: str):
        """Setter for the current active root node"""
        if value != self._active_root:
            logger.debug('Switching the active node to "%s".', value)
            # Stop updating the tree age
            if self._active_root_timer is not None:
                logger.debug("Cancelling active timer: %s", self._active_root_timer)
                self.app.loop.remove_alarm(self._active_root_timer)
                self._active_root_timer = None
            # Stop tracking the focus (does nothing if not sensible)
            urwid.disconnect_signal(
                self.listbox.actual_walker, "modified", self.update_focused_node
            )
            self.update_tree(value)
            self._active_root = value

    @property
    def active_root_node(self) -> typing.Union[RootFlowNode, None]:
        """Return the current active root FlowNode object."""
        if self.active_root:
            return self.flow.full_status(self.active_root)
        else:
            return None

    @property
    def focused_tree(self):
        """Return **True** if the status tree is currently focused."""
        return self.main_columns.focus_position == 1

    def keypress_hook(self, key: str) -> typing.Union[str, None]:
        """Handle key strokes."""
        if key in ("r", "R"):
            self.flow_refresh()
        elif key in ("d", "D"):
            self.reset_folding()
        elif key in ("f", "F"):
            self.fold_first_level()
        elif key in ("c", "C"):
            self.command_dialog()
        elif key in ("l", "L") and self.flow.logs is not None:
            self.logs_dialog()
        elif key in ("i", "I"):
            self.info_dialog()
        elif key in ("a", "A"):
            logger.debug(
                'Aborted tasks selection triggered by user on "%s".', self.active_root
            )
            self.active_root_node.reset_flagged()
            self.active_root_node.flag_status(FlowStatus.ABORTED)
        elif key in ("u", "U"):
            logger.debug(
                'Global un-select triggered by user on "%s".', self.active_root
            )
            self.active_root_node.reset_flagged()
        else:
            return key

    def _radio_buttons_list(
        self, b_group: list, active: str, roots: typing.List[FlowNode]
    ) -> typing.List[urwid.RadioButton]:
        return [
            urwid.RadioButton(
                b_group,
                (tr.status.name, tr.name),
                state=(tr.name == active) if active is not None else "first True",
                on_state_change=self.update_root_choice,
            )
            for tr in roots
        ]

    def update_flow_roots(self):
        """Update the list of root nodes (aka Tree roots)."""
        active = None
        if self.active_root and self.active_root in self.flow.tree_roots:
            # keep track of the current active root Node
            active = self.active_root
        # Order the root nodes given several criteria
        current_time = time.monotonic()
        recent_roots = []
        other_roots = []
        for root_node in self.flow.tree_roots:
            age = current_time - self._roots_hits.get(root_node.name, 0)
            if age > self.recent_roots_threshold:
                other_roots.append(root_node)
            else:
                recent_roots.append(root_node)
        recent_roots.sort(key=lambda x: x.name)
        other_roots.sort(key=lambda x: (x.status.value, x.name))
        # Create the list of buttons representing the various root nodes
        roots_radio_group = []
        entries = (
            self._radio_buttons_list(roots_radio_group, active, recent_roots)
            + [urwid.Text("-")]
            + self._radio_buttons_list(roots_radio_group, active, other_roots)
        )
        # If there is no active root node: active the first root node
        if active is None:
            self.active_root = (recent_roots + other_roots)[0].name
        # Update the left column (root nodes widget)
        self.roots_walker.clear()
        self.roots_walker.extend(entries)
        active_index = [b.state for b in roots_radio_group].index(True)
        self.roots_walker.set_focus(active_index)

    def update_root_choice(self, button: urwid.RadioButton, root: str):
        """Triggered when the user selects a new root Node."""
        if root:
            new_active_root = button.get_label()
            with self.listbox.temporary_void_display():
                self.flow.refresh(new_active_root)
                self.active_root = new_active_root
                self._roots_hits[self.active_root] = time.monotonic()
                # Because the order of the items might change...
                self.update_flow_roots()
            self.main_columns.focus_position = 1  # Jump to the tree

    def update_focused_node(self):
        """Keep track of the focused flow node."""
        f_node = self.listbox.actual_walker.get_focus()[1].flow_node
        if f_node is not None:
            self.active_root_node.focused = f_node

    def age_auto_update(self, current_loop: urwid.MainLoop, registered_root: str):
        """Increment the root Node age."""
        self._active_root_timer = None
        if self.active_root == registered_root:
            try:
                root_f_node = self.active_root_node
            except ValueError:
                # If the tree root does not exists anymore in the scheduler...
                root_f_node = None
            if root_f_node is not None:
                self.header_update(
                    "Information is {:.0f} seconds old.".format(root_f_node.age)
                )
                self._active_root_timer = current_loop.set_alarm_in(
                    self.timer_interval, self.age_auto_update, user_data=registered_root
                )

    def update_tree(self, root: str):
        """Display the **root** node in the Tree widget."""
        root_f_node = self.flow.full_status(root)
        # Find out what should be the selected entry. Start with the last selected...
        focused_node = root_f_node.focused
        if focused_node is None:
            # Otherwise, start on the first leaf of importance
            focused_node = root_f_node.first_blink_leaf()
        if focused_node is None:
            # Otherwise, start on the first expanded leaf
            focused_node = root_f_node.first_expanded_leaf()
        if focused_node is None:
            # Otherwise start from top
            focused_node = root_f_node
        if focused_node is not None:
            root_f_node.focused = focused_node
        # Ok, let's update the TreeView
        if len(focused_node) or focused_node.parent is None:
            self.listbox.actual_node = FamilyNode(focused_node, focused_node.path)
        else:
            self.listbox.actual_node = TaskNode(
                focused_node,
                focused_node.path,
                FamilyNode(focused_node.parent, focused_node.parent.path),
            )
        # Keep track of the focused node
        urwid.connect_signal(
            self.listbox.actual_walker, "modified", self.update_focused_node
        )
        logger.debug(
            'Tree updated for "%s" (information is %f seconds old). Focusing "%s".',
            root,
            root_f_node.age,
            focused_node.path,
        )
        # Display the Root node age
        self.header_update("Information is {:.0f} seconds old.".format(root_f_node.age))
        # Start an age updater if needed
        if self._active_root_timer is None:
            self._active_root_timer = self.app.loop.set_alarm_in(
                self.timer_interval,
                self.age_auto_update,
                user_data=root,
            )
            logger.debug(
                "Timer for age update is: %s (for %s)", self._active_root_timer, root
            )

    def flow_refresh(self):
        """Refresh all the data."""
        logger.debug('Refresh triggered by user on "%s".', self.active_root)
        with self.listbox.temporary_void_display():
            self.flow.refresh(self.active_root)

    def reset_folding(self):
        """Restore the original folding of the Tree widget."""
        logger.debug('Folding reset triggered by user on "%s".', self.active_root)
        self.listbox.actual_node.reset_folding()
        # Reset the focus to the default selected node
        self.listbox.actual_walker.set_focus(self.listbox.actual_node)

    def fold_first_level(self):
        """Fold the nodes located at the first level of the tree."""
        logger.debug(
            'Folding of the first level triggered by user on "%s".', self.active_root
        )
        # Find the root node, and fold its child widgets
        urwid_root = self.listbox.actual_node.get_root()
        c_keys = urwid_root.get_child_keys()
        for c_key in c_keys:
            child_widget = urwid_root.get_child_widget(c_key)
            child_widget.user_set_expanded(False)
        # Select the closest level 1 node (to be consistent with the new folding)
        _, focused_node = self.listbox.actual_walker.get_focus()
        if focused_node.get_depth() > 1:
            while focused_node.get_depth() > 1:
                focused_node = focused_node.get_parent()
            self.listbox.actual_walker.set_focus(focused_node)

    def command_dialog(self):
        """Open the command dialog"""
        logger.debug('Command dialog requested by user on "%s".', self.active_root)
        if self.focused_tree:
            c_view = TFlowCommandView(
                self.flow, self.app, root_node=self.active_root_node
            )
        else:
            c_view = TFlowCommandView(self.flow, self.app, root_node=None)
        self.app.switch_view(c_view)

    def logs_dialog(self):
        """Open the log files view dialog"""
        logger.debug('Logs dialog requested by user on "%s".', self.active_root)
        if self.focused_tree:
            l_view = TFlowLogsView(self.flow, self.app, root_node=self.active_root_node)
        else:
            l_view = TFlowLogsView(self.flow, self.app, root_node=None)
        self.app.switch_view(l_view)

    def info_dialog(self):
        """Open the info view dialog"""
        logger.debug('Info dialog requested by user on "%s".', self.active_root)
        if self.focused_tree:
            l_view = TFlowInfoView(
                self.flow, self.app, visited_node=self.active_root_node.focused
            )
        else:
            l_view = TFlowInfoView(self.flow, self.app, visited_node=None)
        self.app.switch_view(l_view)


# ------ Application object:  The UI entry point ! -------


class TFlowApplication(object):
    """The object representing the tflowclient UI."""

    _APPS = {
        "TreeView": TFlowMainView,
        "Cancel": TFlowCancelMainView,
    }

    def __init__(self, flow_object: FlowInterface, app_name: str = "TreeView"):
        """
        :param flow_object: The Flow interface currently being used.
        :param app_name: Which application should be started
        """
        self.flow = flow_object
        if app_name not in self._APPS:
            raise ValueError('Unauthorised "app_name" value: {:s}'.format(app_name))
        # Create the Frame widget that will be used in the whole application
        self.view = urwid.Frame(urwid.Filler(urwid.Text("Initialising...")))
        # Create the main loop
        screen = (
            urwid.curses_display.Screen()
            if tflowclient_conf.urwid_backend == "curses"
            else urwid.raw_display.Screen()
        )
        logger.debug("Creating the urwid main loop. Screen is: %s", screen)
        if tflowclient_conf.urwid_backend != "curses":
            t_properties = tflowclient_conf.terminal_properties
            screen.set_terminal_properties(**t_properties)
            logger.debug(
                "Creating the urwid main loop. Terminal properties: %s", t_properties
            )
        palette = tflowclient_conf.palette
        logger.debug(
            "Creating the urwid main loop. Palette is:\n  %s",
            "\n  ".join([str(item) for item in palette]),
        )
        self.loop = urwid.MainLoop(
            self.view,
            palette,
            screen=screen,
            unhandled_input=self.unhandled_input,
            handle_mouse=tflowclient_conf.handle_mouse,
        )
        # Create the Main (tree) view and display it
        self.current_view = None
        self.main_view = self._APPS[app_name](self.flow, self)
        self.switch_view(self.main_view)
        # Create the Quit view (just in case)
        self.quit_view = TFlowQuitView(self.flow, self)

    # noinspection PyArgumentList
    def switch_view(self, view_obj: TFlowAbstractView):
        """Display the **view_obj** view."""
        logger.debug('Switching to view: "%s"', view_obj)
        if self.current_view is not None:
            self.current_view.switch_out_hook()
        view_obj.switch_in_hook()
        self.view.set_body(view_obj.main_content)
        self.view.set_header(urwid.AttrWrap(view_obj.header, "head"))
        self.view.set_footer(urwid.AttrWrap(view_obj.footer, "foot"))
        self.current_view = view_obj
        view_obj.switch_post_in_hook()

    def main(self):
        """Run the Urwid main loop."""
        self.loop.run()

    def unhandled_input(self, key: str):
        """Handle q/Q key strokes."""
        if key in ("q", "Q") and self.current_view != self.quit_view:
            self.switch_view(self.quit_view)
