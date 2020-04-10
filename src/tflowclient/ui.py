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
import logging
import time
import typing

import urwid
import urwid.curses_display

from .conf import tflowclient_conf
from .flow import FlowInterface, FlowNode, RootFlowNode, FlowStatus
from .observer import Observer

__all__ = ['TFlowApplication']

logger = logging.getLogger(__name__)


# ------ Urwid Tree Widgets that help to build the statuses tree view ------

class AnyEntryWidget(urwid.TreeWidget, Observer):
    """Base class for any TreeWidget."""

    indent_cols = 2

    def __init__(self, node: AnyUrwidFlowNode, flow_node: FlowNode, cust_label: str = None):
        """
        :param node: The node we are working on (as a Urwid Node class)
        :param flow_node:  The node we are working on (as a :class:`FlowNode` class)
        :param cust_label: A custom label used when displaying the node
        """
        # internal attributes...
        self._cust_label = cust_label
        self._flow_node = flow_node
        self._flow_node.flagged = False
        # insert an extra AttrWrap for our own use
        super().__init__(node)
        self._w = urwid.AttrWrap(self._w, None)
        self.update_w()
        # react to changes in the _flow_node
        self._flow_node.observer_attach(self)

    def update_obs_item(self, item: FlowNode, info: dict):
        """Deal with node's selection changes."""
        if isinstance(item, FlowNode) and 'flagged' in info:
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
        self._w.attr = ('flagged_' if self._flow_node.flagged else '') + 'treeline'
        self._w.focus_attr = self._w.attr + '_f'

    def get_display_text(self) -> list:
        """The displayed text (including the status)."""
        label = self.get_display_label()
        return [(self._flow_node.status.name, '[{:s}]'.format(self._flow_node.status.name[:3])),
                ' ', label]
    
    def get_display_label(self) -> str:
        """The node's name."""
        return self._cust_label if self._cust_label else self.get_node().get_key()

    def reset_folding(self):
        """Reset the tree folding."""
        pass


class FamilyTreeWidget(AnyEntryWidget):
    """Widget for a family node."""

    def __init__(self, node: AnyUrwidFlowNode, flow_node: FlowNode, cust_label: str = None):
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
        return [' ' * self.indent_cols, ] + super().get_display_text()


class EmptyWidget(urwid.TreeWidget):
    """A marker for an expanded family with no contents."""

    def get_display_text(self) -> str:
        """The displayed text."""
        return '(empty directory)'


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
        if path == '':
            depth = 0
            key = None
        else:
            depth = path.count('/') + 1
            key = path.split('/')[-1]
        self._c_keys = collections.OrderedDict()
        super().__init__(path, key=key, parent=parent, depth=depth)

    def load_parent(self) -> FamilyNode:
        """Create the parent node."""
        s_path = self.get_value().split('/')
        parent_name = '/'.join(s_path[:-1])
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
            self._children[None] = EmptyNode('', parent=self, key=None, depth=depth)
            return [None]
        else:
            return list(self._c_keys.keys())

    def load_child_node(self, key: str) -> AnyUrwidFlowNode:
        """Create a the Urwid child node object based on the key."""
        """Return either a FileNode or DirectoryNode"""
        if key is None:
            return EmptyNode('')
        else:
            cf_node = self._c_keys[key]
            c_path = (self.get_value() + '/' if self.get_value() else '') + key
            if len(cf_node):
                return FamilyNode(cf_node, c_path, parent=self)
            else:
                return TaskNode(cf_node, c_path, parent=self)

    def load_widget(self) -> FamilyTreeWidget:
        """Load the Urwid widget for self."""
        if self.get_value():
            return FamilyTreeWidget(self, self.flow_node)
        else:
            return FamilyTreeWidget(self, self.flow_node, cust_label=self.flow_node.name)

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
        depth = path.count('/') + 1
        key = path.split('/')[-1]
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

class ArrowLessTreeListBox(urwid.TreeListBox):
    """A TreeListBow widget that does not use left/right keys."""

    def keypress(self, size: typing.Tuple[int], key: str) -> typing.Union[str, None]:
        """Do not use left/right keys."""
        if key in ('left', 'right'):
            return key
        else:
            return super().keypress(size, key)


class KeyCaptureWrapper(urwid.WidgetWrap):
    """Capture key strokes and call the current view ``keypress_hook`` callback on them."""

    def __init__(self, w: urwid.Widget, current_view: TFlowAbstractView,
                 propagate: bool = True):
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
        if key and hasattr(self._w, 'keypress') and self._propagate:
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

    def header_update(self, extra: str = ''):
        """Update the header text (given any **extra** information)."""
        self.header.set_text("tCDP for {!s}. {:s}".format(self.flow, extra))

    def footer_update(self, *extras: list):
        """Update the footer text given a list of command extended by **extras**."""
        txt_pile = []
        for extra in extras:
            txt_pile.append(urwid.Text(extra))
        for extra in self.footer_text:
            txt_pile.append(urwid.Text(extra))
        txt_pile.append(urwid.Text([('key', "Q"), ": Quit"]))
        max_len = max([len(t.text) for t in txt_pile])
        if self.footer is None:
            self.footer = urwid.GridFlow(txt_pile, max_len,
                                         h_sep=2, v_sep=0, align='left')
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
        ('Rerun', '$', 'rerun'),
        ('Execute', 'E', 'execute'),
        ('Suspend', 'S', 'suspend'),
        ('Resume', 'R', 'resume'),
        ('Complete', 'C', 'complete'),
        ('Requeue', '0', 'requeue'),
    ]

    def __init__(self, flow_object: FlowInterface, app_object: TFlowApplication, root_node: FlowNode):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        :param root_node: The current active root FlowNode
        """
        super().__init__(flow_object, app_object)
        self.root_node = root_node
        # List of selected lines (append the suite name to be compatible with flow
        # schedulers tree)
        self.selected = ['/' + self.flow.suite + '/' + p
                         for p in root_node.flagged_paths()]
        if self.selected:
            # Prompt the user to choose a command
            self.text_container = urwid.Text(self._get_message())
            self.grid_flow = self._commands_grid()
            self.pile = urwid.Pile([
                urwid.Filler(self.text_container, valign='bottom'),
                urwid.Filler(self.grid_flow, valign='top')
                ])
            self.main_content = KeyCaptureWrapper(self.pile, current_view=self)
            self.footer_update([('key', '/'.join([av_c[1] for av_c in self.available_commands
                                                  if av_c[1]])),
                                ': launch the command'],
                               [('key', 'ESC'), ': back to statuses'])
        else:
            # Display the "error" message, then go back
            self.text_container = urwid.Text("Select at least one node...")
            self.main_content = KeyCaptureWrapper(urwid.Filler(self.text_container),
                                                  current_view=self, propagate=False)
            self.footer_update([('key', 'ESC/ENTER'), ': back to statuses'])
        self._todo = None

    def _get_message(self) -> str:
        return ('Selected nodes:\n{:s}\n\nAvailable commands:\n'
                .format('\n'.join(self.selected)))

    def _commands_grid(self) -> urwid.GridFlow:
        """Generate the list of Urwid buttons associated with each of the commands."""
        buttons = []
        label_sizes = []
        for av_c in self.available_commands:
            label = '[{1:s}] {0:s}'.format(* av_c)
            label_sizes.append(len(label))
            buttons.append(urwid.Button(label, on_press=self._button_pressed,
                                        user_data=av_c[2]))
        return urwid.GridFlow(buttons, cell_width=max(label_sizes) + 4,
                              h_sep=2, v_sep=0, align='left')

    def _button_pressed(self, button: urwid.Button, user_data: str):
        """Triggered when a button is pressed."""
        assert isinstance(button, urwid.Button)
        self._do_command(user_data)

    def _do_command(self, command: str):
        """Launch **command** and display the result."""
        self._todo = command
        summary = 'Result for the "{:s}" command:\n'.format(command)
        summary += self.flow.command_gateway(command, self.root_node, self.selected)
        wait = '\n\nPlease wait will the status tree is being refreshed...'
        self.root_node.reset_flagged()
        self.text_container = urwid.Text([summary, ('warning', wait)])
        self.pile.contents = [(urwid.Filler(self.text_container), ('weight', 1))]
        self.app.loop.draw_screen()
        self.app.main_view.flow_refresh()
        self.text_container = urwid.Text(summary)
        self.pile.contents = [(urwid.Filler(self.text_container), ('weight', 1))]
        self.footer_update([('key', 'ESC/ENTER'), ': back to statuses'])

    def keypress_hook(self, key: str) -> typing.Union[str, None]:
        """Handle key strokes."""
        if self.selected and self._todo is None:
            for av_c in self.available_commands:
                if av_c[1] and key.upper() == av_c[1]:
                    self._do_command(av_c[2])
                    return
            if key == 'esc':
                self.app.switch_view(self.app.main_view)
            else:
                return key
        else:
            if key in ('esc', 'enter'):
                self.app.switch_view(self.app.main_view)
            else:
                return key


class TFlowMainView(TFlowAbstractView):
    """The application' main view (statuses tree)."""

    footer_text = [
        [('key', "SPACE"), ": Fold/Unfold"],
        [('key', "F"), ": Reset Folding"],
        [('key', "R"), ": Refresh"],
        [('key', "ENTER"), ": Select"],
        [('key', "A"), ": Select Aborted"],
        [('key', "U"), ": Un-select all"],
        [('key', "C"), ": Launch Command"],
        ]

    recent_roots_threshold = 3 * 3600

    timer_interval = 1

    def __init__(self, flow_object: FlowInterface, app_object: TFlowApplication):
        """
        :param flow_object: The flow object currently being used
        :param app_object: The application object
        """
        super().__init__(flow_object, app_object)
        # Create the "Tree" widget
        self.listbox_void_node = FamilyNode(
            RootFlowNode('Please wait (it might take some time to query the server)...',
                         FlowStatus.UNKNOWN),
            ''
        )
        self.listbox_void_walker = urwid.TreeWalker(self.listbox_void_node)
        self.listbox_f_node = self.listbox_void_node
        self.listbox = ArrowLessTreeListBox(self.listbox_void_walker)
        self.listbox_focused = dict()
        # Display the various root nodes
        self.roots_walker = urwid.SimpleFocusListWalker([])
        roots_list = urwid.ListBox(self.roots_walker)
        self._roots_hits = dict()
        self._roots_radio_group = []
        self._active_root = None
        self._active_root_timer = None
        # Populate the root nodes list and display the first item in the tree widget
        self.update_flow_roots()
        # Create the appropriate layout (root nodes on the left, tree on the right)
        self.main_columns = urwid.Columns([(4 + max([len(r.name) for r in self.flow.tree_roots]),
                                            roots_list),
                                           self.listbox],
                                          dividechars=2)
        self.main_content = KeyCaptureWrapper(self.main_columns,
                                              current_view=self)

    @property
    def active_root_node(self) -> typing.Union[RootFlowNode, None]:
        """Return the current active root FlowNode object"""
        if self._active_root:
            return self.flow.full_status(self._active_root)
        else:
            return None

    def keypress_hook(self, key: str) -> typing.Union[str, None]:
        """Handle key strokes."""
        if key in ('r', 'R'):
            self.flow_refresh()
        elif key in ('f', 'F'):
            self.reset_folding()
        elif key in ('c', 'C'):
            self.command_dialog()
        elif key in ('a', 'A'):
            logger.debug('Aborted tasks selection triggered by user on "%s".',
                         self._active_root)
            self.active_root_node.flag_status(FlowStatus.ABORTED)
        elif key in ('u', 'U'):
            logger.debug('Global un-select triggered by user on "%s".',
                         self._active_root)
            self.active_root_node.reset_flagged()
        else:
            return key

    def update_flow_roots(self):
        """Update the list of root nodes"""
        active = None
        if self._active_root and self._active_root in self.flow.tree_roots:
            # keep track of the current active root Node
            active = self._active_root
        # Create the list of buttons representing the various root nodes
        self._roots_radio_group = []
        current_time = time.time()
        #
        sorted_roots = sorted(self.flow.tree_roots,
                              key=lambda x: (current_time - self._roots_hits.get(x.name, 0)
                                             > self.recent_roots_threshold))
        entries = [urwid.RadioButton(self._roots_radio_group,
                                     (tr.status.name, tr.name),
                                     state=(tr.name == active) if active is not None else 'first True',
                                     on_state_change=self.update_root_choice)
                   for tr in sorted_roots]
        # If there is no active root node: active the first root node
        if active is None:
            self._active_root = list(self.flow.tree_roots)[0].name
            logger.debug('Switching the active node to "%s" (in update_flow_roots).',
                         self._active_root)
        active_index = [b.state for b in self._roots_radio_group].index(True)
        # Display the active node in the Tree widget
        self.update_tree(self._active_root)
        # Update the left column (root nodes widget)
        self.roots_walker.clear()
        self.roots_walker.extend(entries)
        self.roots_walker.set_focus(active_index)

    def update_root_choice(self, button: urwid.RadioButton, root: str):
        """Triggered when the user selects a new root Node."""
        if root:
            self.age_auto_update_cancel()
            self._active_root = button.get_label()
            self._roots_hits[self._active_root] = time.time()
            logger.debug('Switching the active node to "%s" (requested by the user).',
                         self._active_root)
            if not self.flow.in_cache(self._active_root):
                self.listbox.body = self.listbox_void_walker
                self.app.loop.draw_screen()
            self.update_flow_roots()
            self.main_columns.focus_position = 1  # Jump to the tree

    def update_focused_node(self, root_f_node):
        """Keep track of the focused flow node."""
        f_node = self.listbox.body.get_focus()[1].flow_node
        if f_node is not None:
            root_f_node.focused = f_node

    def age_auto_update(self, current_loop: urwid.MainLoop, registered_root: str):
        """Increment the root Node age."""
        self._active_root_timer = None
        if self._active_root == registered_root:
            root_f_node = self.active_root_node
            if root_f_node is not None:
                self.header_update("Information is {:.0f} seconds old."
                                   .format(root_f_node.age))
                self._active_root_timer = current_loop.set_alarm_in(
                    self.timer_interval,
                    self.age_auto_update,
                    user_data=registered_root
                )

    def age_auto_update_cancel(self):
        """Cancel the age updater."""
        if self._active_root_timer is not None:
            logger.debug('Cancelling active timer: %s', self._active_root_timer)
            self.app.loop.remove_alarm(self._active_root_timer)
            self._active_root_timer = None

    def update_tree(self, root: str):
        """Display the **root** root Node in the Tree widget."""
        self.age_auto_update_cancel()
        root_f_node = self.flow.full_status(root)
        # Last selected entry
        focused_node = root_f_node.focused
        if focused_node is None:
            # Otherwise, start on the first expanded leaf
            focused_node = root_f_node.first_expanded_leaf()
        if focused_node is None:
            # Otherwise start from top
            focused_node = root_f_node
        if len(focused_node) or focused_node.parent is None:
            self.listbox_f_node = FamilyNode(focused_node, focused_node.path)
        else:
            self.listbox_f_node = TaskNode(focused_node, focused_node.path,
                                           FamilyNode(focused_node.parent,
                                                      focused_node.parent.path))
        self.listbox.body = urwid.TreeWalker(self.listbox_f_node)
        # Keep track of the focused node
        urwid.connect_signal(self.listbox.body, 'modified',
                             self.update_focused_node, root_f_node)
        logger.debug('Tree updated for "%s" (information is %f seconds old). Focusing "%s".',
                     self._active_root, root_f_node.age, focused_node.path)
        self.header_update("Information is {:.0f} seconds old."
                           .format(root_f_node.age))
        self._active_root_timer = self.app.loop.set_alarm_in(
            self.timer_interval,
            self.age_auto_update,
            user_data=root,
        )
        logger.debug('Update timer for age update is: %s (for %s)',
                     self._active_root_timer, root)

    def flow_refresh(self):
        """Refresh all the data."""
        self.age_auto_update_cancel()
        logger.debug('Refresh triggered by user on "%s".', self._active_root)
        self.listbox.body = self.listbox_void_walker
        self.app.loop.draw_screen()
        self.flow.refresh(self._active_root)
        self.update_flow_roots()

    def reset_folding(self):
        """Restore the original folding of the Tree widget."""
        logger.debug('Folding reset triggered by user on "%s".', self._active_root)
        self.listbox_f_node.reset_folding()

    def command_dialog(self):
        """Open the command dialog"""
        self.age_auto_update_cancel()
        logger.debug('Command dialog requested by user on "%s".', self._active_root)
        c_view = TFlowCommandView(self.flow, self.app,
                                  root_node=self.active_root_node)
        self.app.switch_view(c_view)


# ------ Application object:  The UI entry point ! -------

class TFlowApplication(object):
    """The object representing the tflowclient UI."""

    def __init__(self, flow_object: FlowInterface):
        """
        :param flow_object: The Flow interface currently being used.
        """
        self.flow = flow_object
        # Create the Frame widget that will be used in the whole application
        self.view = urwid.Frame(urwid.Filler(urwid.Text('Initialising...')))
        # Create the main loop
        screen = (urwid.curses_display.Screen()
                  if tflowclient_conf.urwid_backend == 'curses' else
                  urwid.raw_display.Screen())
        t_properties = tflowclient_conf.terminal_properties
        screen.set_terminal_properties(** t_properties)
        palette = tflowclient_conf.palette
        logger.debug('Creating the urwid main loop. Palette is:\n  %s',
                     '\n  '.join([str(item) for item in palette]))
        logger.debug('Creating the urwid main loop. Screen is: %s', screen)
        logger.debug('Creating the urwid main loop. Terminal properties: %s',
                     t_properties)
        self.loop = urwid.MainLoop(self.view, palette, screen=screen,
                                   unhandled_input=self.unhandled_input)
        # Create the Main (tree) view and display it
        self.main_view = TFlowMainView(self.flow, self)
        self.switch_view(self.main_view)

    def switch_view(self, view_obj: TFlowAbstractView):
        """Display the **view_obj** view."""
        logger.debug('Switching to view: "%s"', view_obj)
        self.view.set_body(view_obj.main_content)
        self.view.set_header(urwid.AttrWrap(view_obj.header, 'head'))
        self.view.set_footer(urwid.AttrWrap(view_obj.footer, 'foot'))

    def main(self):
        """Run the Urwid main loop."""
        self.loop.run()

    @staticmethod
    def unhandled_input(key: str):
        """Handle q/Q key strokes."""
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
