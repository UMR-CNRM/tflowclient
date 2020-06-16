# -*- coding: utf-8 -*-

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

import collections
import contextlib
from datetime import datetime, timedelta
import logging
import subprocess
import time
import typing

import urwid
import urwid.curses_display

from .conf import tflowclient_conf
from .flow import FlowInterface, FlowNode, RootFlowNode, FlowStatus
from .logs_gateway import LogsGatewayRuntimeError
from .observer import Observer

__all__ = ["TFlowApplication"]

logger = logging.getLogger(__name__)


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

    def keypress(self, size: typing.Tuple[int], key: str) -> typing.Union[str, None]:
        """allow subclasses to intercept keystrokes"""
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
        self.expanded = True
        self.reset_folding()

    def reset_folding(self):
        """Reset the tree folding."""
        self.expanded = self._flow_node.expanded
        self.update_expanded_icon()

    def keypress(self, size: typing.Tuple[int], key: str) -> typing.Union[str, None]:
        """allow subclasses to intercept keystrokes"""
        if key == " ":
            # Expand ...
            self.expanded = not self.expanded
            self.update_expanded_icon()
        else:
            return super().keypress(size, key)


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


# ------ Our very own implementation of sme Urwid widgets ------


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

    def keypress(self, size: typing.Tuple[int], key: str) -> typing.Union[str, None]:
        """Divert key strokes to the ``keypress_hook`` method."""
        key = self._current_view.keypress_hook(key)
        if key and hasattr(self._w, "keypress") and self._propagate:
            return self._w.keypress(size, key)
        else:
            return key


# ------ Views are custom object that handle a given layout of the UI ------


class TFlowAbstractView(object):
    """Any tflowclient views must inherit from this class"""

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
        txt_pile.append(urwid.Text([("key", "Q"), ": Quit"]))
        max_len = max([len(t.text) for t in txt_pile])
        if self.footer is None:
            self.footer = urwid.GridFlow(
                txt_pile, max_len, h_sep=2, v_sep=0, align="left"
            )
        else:
            self.footer.cell_width = max_len
            self.footer.contents = [(t, self.footer.options()) for t in txt_pile]

    def keypress_hook(self, key: str) -> typing.Union[str, None]:
        """Leveraged when used with a :class:`KeyCaptureWrapper` wrapper."""
        return key


class TFlowCommandView(TFlowAbstractView):
    """The view that is triggered when the user chooses to launch a command."""

    footer_text = []

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
        root_node: RootFlowNode,
    ):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        :param root_node: The current active root FlowNode
        """
        super().__init__(flow_object, app_object)
        self.root_node = root_node
        # List of selected lines (append the suite name to be compatible with flow
        # schedulers tree)
        self.selected = [
            "/" + self.flow.suite + "/" + p for p in root_node.flagged_paths()
        ]
        if not self.selected:
            # Try to use the focused_node
            if root_node.focused is not None and self.app.main_view.focused_tree:
                self.selected = [
                    "/"
                    + self.flow.suite
                    + "/"
                    + root_node.name
                    + "/"
                    + root_node.focused.path
                ]
        if self.selected:
            # Prompt the user to choose a command
            self.text_container = urwid.Text(self._get_message())
            self.grid_flow = self._commands_grid()
            self.pile = urwid.Pile(
                [
                    urwid.Filler(self.text_container, valign="bottom"),
                    urwid.Filler(self.grid_flow, valign="top"),
                ]
            )
            self.main_content = KeyCaptureWrapper(self.pile, current_view=self)
            self.footer_update(
                [
                    (
                        "key",
                        "/".join(
                            [av_c[1] for av_c in self.available_commands if av_c[1]]
                        ),
                    ),
                    ": launch the command",
                ],
                [("key", "ESC"), ": back to statuses"],
            )
        else:
            # Display the "error" message, then go back
            self.text_container = urwid.Text("Select at least one node...")
            self.main_content = KeyCaptureWrapper(
                urwid.Filler(self.text_container), current_view=self, propagate=False
            )
            self.footer_update([("key", "ESC/ENTER"), ": back to statuses"])
        self._todo = None

    def _get_message(self) -> str:
        return "Selected nodes:\n{:s}\n\nAvailable commands:\n".format(
            "\n".join(self.selected)
        )

    def _commands_grid(self) -> urwid.GridFlow:
        """Generate the list of Urwid buttons associated with each of the commands."""
        buttons = []
        label_sizes = []
        for av_c in self.available_commands:
            label = "[{1:s}] {0:s}".format(*av_c)
            label_sizes.append(len(label))
            buttons.append(
                urwid.Button(label, on_press=self._button_pressed, user_data=av_c[2])
            )
        return urwid.GridFlow(
            buttons, cell_width=max(label_sizes) + 4, h_sep=2, v_sep=0, align="left"
        )

    def _button_pressed(self, button: urwid.Button, user_data: str):
        """Triggered when a button is pressed."""
        assert isinstance(button, urwid.Button)
        self._do_command(user_data)

    def _do_command(self, command: str):
        """Launch **command** and display the result."""
        self._todo = command
        wait = "\n\nPlease wait will the {:s} command is being issued...".format(
            command
        )
        self.text_container = urwid.Text([("warning", wait)])
        self.pile.contents = [(urwid.Filler(self.text_container), ("weight", 1))]
        self.footer_update()
        self.app.loop.draw_screen()
        summary = 'Result for the "{:s}" command:\n'.format(command)
        summary += self.flow.command_gateway(command, self.root_node, self.selected)
        wait = "\n\nPlease wait will the status tree is being refreshed..."
        self.text_container = urwid.Text([summary, ("warning", wait)])
        self.pile.contents = [(urwid.Filler(self.text_container), ("weight", 1))]
        self.footer_update()
        self.app.loop.draw_screen()
        self.flow.refresh(self.root_node.name)
        self.text_container = urwid.Text(summary)
        self.pile.contents = [(urwid.Filler(self.text_container), ("weight", 1))]
        self.footer_update([("key", "ESC/ENTER/BACKSPACE"), ": back to statuses"])

    def keypress_hook(self, key: str) -> typing.Union[str, None]:
        """Handle key strokes."""
        if self.selected and self._todo is None:
            for av_c in self.available_commands:
                if av_c[1] and key.upper() == av_c[1]:
                    self._do_command(av_c[2])
                    return
            if key == "esc":
                self.app.switch_view(self.app.main_view)
            else:
                return key
        else:
            if key in ("esc", "enter", "backspace"):
                self.app.switch_view(self.app.main_view)
            else:
                return key


class TFlowLogsView(TFlowAbstractView):
    """The view that is triggered when the user chooses to browse the log files."""

    footer_text = [
        [("key", "ESC/BACKSPACE"), ": back to statuses"],
        [("key", "ENTER/SPACE"), ": view the selected file"],
    ]

    def __init__(
        self,
        flow_object: FlowInterface,
        app_object: TFlowApplication,
        root_node: RootFlowNode,
    ):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        :param root_node: The current active root FlowNode
        """
        super().__init__(flow_object, app_object)
        self.focused_node = root_node.focused
        self.focused_path = (
            "/" + self.flow.suite + "/" + root_node.name + "/" + self.focused_node.path
            if self.focused_node is not None and self.app.main_view.focused_tree
            else None
        )
        self.buttons = []
        if self.focused_path is None:
            self.text_container = urwid.Text(
                "No node is currently focused. Please pick one."
            )
        elif len(self.focused_node):
            self.text_container = urwid.Text(
                "The focused node ({:s}) is not a leaf node (i.e. a Task).".format(
                    self.focused_path
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
                            "An un-expected error occured while fetching the "
                            + "list of available log files:\n{!s}".format(e),
                        )
                    ]
                )
                logger.error(
                    "Error while fetching log files list for path '%s':\n%s",
                    self.focused_path,
                    e,
                )
            else:
                if av_listings:
                    self.text_container = urwid.Text(
                        "For node: {:s}\n\nThe available log files are:\n".format(
                            self.focused_path
                        )
                    )
                    b_group = list()
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
                            urwid.Button(
                                l_label,
                                on_press=self._button_pressed,
                                user_data=listing[0],
                            )
                        )
                else:
                    self.text_container = urwid.Text(
                        "No log files are available for:\n{:s}".format(
                            self.focused_path
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
        else:
            self.main_content = KeyCaptureWrapper(
                urwid.Filler(self.text_container), current_view=self, propagate=False
            )

    def _button_pressed(self, button: urwid.Button, log_listing: str):
        """Triggered when a button is pressed (e.g. when a log file is chosen)."""
        assert isinstance(button, urwid.Button)
        try:
            with self.flow.logs.get_as_file(self.focused_path, log_listing) as f_obj:
                subprocess.check_call(["vim", "-R", "-N", f_obj.name])
        except LogsGatewayRuntimeError as e:
            # This step may fail (network problems, ...)
            self.text_container.set_text(
                [
                    (
                        "warning",
                        'An error occured while fetching the "{:s}" listing: {!s}'.format(
                            log_listing, e
                        ),
                    ),
                    "\n\n",
                    self.text_container.text,
                ]
            )
            logger.error(
                "Error while fetching '%s' for path '%s':\n%s",
                log_listing,
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


class TFlowMainView(TFlowAbstractView, Observer):
    """The application' main view (statuses tree)."""

    footer_text = [
        [("key", "SPACE"), ": Fold/Unfold"],
        [("key", "D"), ": Default Folding"],
        [("key", "F"), ": Fold 1st Level"],
        [("key", "R"), ": Refresh"],
        [("key", "ENTER"), ": Select"],
        [("key", "A"), ": Select Aborted"],
        [("key", "U"), ": Un-select all"],
        [("key", "C"), ": Launch Command"],
    ]

    recent_roots_threshold = 3 * 3600

    timer_interval = 1

    def __init__(self, flow_object: FlowInterface, app_object: TFlowApplication):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        """
        if flow_object.logs is not None:
            self.footer_text = self.footer_text + [[("key", "L"), ": Access Logs"]]
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
        elif key in ("a", "A"):
            logger.debug(
                'Aborted tasks selection triggered by user on "%s".', self.active_root
            )
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
        current_time = time.time()
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
            with self.listbox.temporary_void_display(
                not self.flow.in_cache(new_active_root)
            ):
                self.active_root = new_active_root
                self._roots_hits[self.active_root] = time.time()
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
                self.timer_interval, self.age_auto_update, user_data=root,
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
            child_widget.expanded = False
            child_widget.update_expanded_icon()
        # Select the closest level 1 node (to be consistent with the new folding)
        _, focused_node = self.listbox.actual_walker.get_focus()
        if focused_node.get_depth() > 1:
            while focused_node.get_depth() > 1:
                focused_node = focused_node.get_parent()
            self.listbox.actual_walker.set_focus(focused_node)

    def command_dialog(self):
        """Open the command dialog"""
        logger.debug('Command dialog requested by user on "%s".', self.active_root)
        c_view = TFlowCommandView(self.flow, self.app, root_node=self.active_root_node)
        self.app.switch_view(c_view)

    def logs_dialog(self):
        """Open the log files view dialog"""
        logger.debug('Logs dialog requested by user on "%s".', self.active_root)
        l_view = TFlowLogsView(self.flow, self.app, root_node=self.active_root_node)
        self.app.switch_view(l_view)


# ------ Application object:  The UI entry point ! -------


class TFlowApplication(object):
    """The object representing the tflowclient UI."""

    def __init__(self, flow_object: FlowInterface):
        """
        :param flow_object: The Flow interface currently being used.
        """
        self.flow = flow_object
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
            self.view, palette, screen=screen, unhandled_input=self.unhandled_input
        )
        # Create the Main (tree) view and display it
        self.main_view = TFlowMainView(self.flow, self)
        self.switch_view(self.main_view)

    def switch_view(self, view_obj: TFlowAbstractView):
        """Display the **view_obj** view."""
        logger.debug('Switching to view: "%s"', view_obj)
        self.view.set_body(view_obj.main_content)
        self.view.set_header(urwid.AttrWrap(view_obj.header, "head"))
        self.view.set_footer(urwid.AttrWrap(view_obj.footer, "foot"))

    def main(self):
        """Run the Urwid main loop."""
        self.loop.run()

    @staticmethod
    def unhandled_input(key: str):
        """Handle q/Q key strokes."""
        if key in ("q", "Q"):
            raise urwid.ExitMainLoop()
