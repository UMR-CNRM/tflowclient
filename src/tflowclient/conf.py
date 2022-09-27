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
Handle the tflowclient configuration's file.
"""

from __future__ import annotations

import configparser
import logging
import logging.handlers
import os
import shlex
import typing

__all__ = ["TFlowClientConfig", "tflowclient_conf"]

logger = logging.getLogger(__name__)


#: The default urwid palette for the tflowclient
DEFAULT_PALETTE = dict(
    ACTIVE=("black", "dark green"),
    ACTIVE_f=("black", "dark green"),
    SUSPENDED=("black", "brown"),
    SUSPENDED_f=("black", "brown"),
    ABORTED=("black", "dark red"),
    ABORTED_f=("black", "dark red"),
    SUBMITTED=("black", "dark cyan"),
    SUBMITTED_f=("black", "dark cyan"),
    COMPLETE=("black", "yellow"),
    COMPLETE_f=("black", "yellow"),
    QUEUED=("black", "white"),
    QUEUED_f=("black", "white"),
    warning=("black", "brown"),
    treeline=("black", "light gray"),
    flagged_treeline=("black", "dark magenta", ("bold", "underline")),
    treeline_f=("light gray", "dark blue", "standout"),
    flagged_treeline_f=("yellow", "dark magenta"),
    head=("yellow", "black", "standout"),
    foot=("white", "black"),
    key=("light cyan", "black", "underline"),
    title=("white", "black", "bold"),
    button=("black", "light gray"),
    button_f=("white", "dark blue", "bold"),
    editable=("black", "light gray"),
    editable_f=("white", "dark blue", "bold"),
)


class TFlowClientConfig(object):
    """Read the tflowclient configuration files.

    A system-wide configuration file can be specified using the
    TFLOWCLIENT_SITE_CONF environment variable. An additional user-wide
    configuration file while be read in (if present). It is located in
    ~/.tflowclient.ini.
    """

    _CONFIG_ENV_VAR = "TFLOWCLIENT_SITE_CONF"
    _CONFIG_FILE = os.path.join(os.environ["HOME"], ".tflowclientrc.ini")

    def __init__(self, conf_txt: str = None):
        """
        :param conf_txt: Provide a text based version of the config file. For
                         testing purposes only. If provided, the default
                         configuration (~/.tflowclientrc.ini) is not read in.
        """
        conf_obj = configparser.ConfigParser()
        conf_obj.optionxform = lambda option: option
        if conf_txt is not None:
            conf_obj.read_string(conf_txt)
        else:
            todo = []
            site_config = os.environ.get(self._CONFIG_ENV_VAR, None)
            if site_config and os.path.exists(site_config):
                todo.append(site_config)
            if os.path.exists(self._CONFIG_FILE):
                todo.append(self._CONFIG_FILE)
            if todo:
                conf_obj.read(todo, encoding="utf-8")
        self._conf = conf_obj

    def logging_config(self, filename: str = None, level: str = None):
        """Configure the logging facility.

        The ``filename`` and ``level`` options of the configuration file
        ``[logging]`` section are considered. If missing, default values for
        ``filename`` and ``level`` are ``~/.tflowclient.log`` and ``CRITICAL``.
        """
        # Handler
        if filename is None:
            filename = self._conf.get(
                "logging", "filename", fallback="~/.tflowclient.log"
            )
            filename = os.path.expanduser(filename)
        f_handler = logging.handlers.TimedRotatingFileHandler(
            filename, when="midnight", interval=1, backupCount=3, encoding="utf-8"
        )
        # Formatter
        formatter = logging.Formatter(
            "[%(asctime)s] pid=%(process)d: %(name)s %(levelname)s: %(message)s"
        )
        f_handler.setFormatter(formatter)
        # Add the Handler to the main logger
        m_logger = logging.getLogger()
        m_logger.addHandler(f_handler)
        # Configure the logging level
        if level is None:
            m_logger.setLevel(
                self._conf.get("logging", "level", fallback=logging.CRITICAL)
            )
        else:
            m_logger.setLevel(level)

    @property
    def urwid_backend(self) -> str:
        """The 'urwid' that should be used to create tha layout.

        Currently, only ``raw`` and ``curses`` are supported.

        Example::

            [urwid]
            backend = raw

        """
        return self._conf.get("urwid", "backend", fallback="raw")

    @property
    def palette(self) -> typing.Union[typing.List[typing.Tuple], None]:
        """Return a "palette" description that could be used in urwid.

        The palette configuration data are to be found in the [palette] section
        of the configuration file.

        The configuration file key corresponds to the palette entry key. The
        configuration value is split based on the ',' and '+' character in
        order to create the appropriate tuples.

        For example::

            flagged_treeline = black, dark magenta, bold+underline

        Will be transformed into the following tuple::

            ('flagged_treeline', 'black', 'dark magenta', ('bold', 'underline')),

        The resulting palette is an update of the default palette (see the
        ``DEFAULT_PALETTE`` module variable) with lines read in the
        configuration file.
        """
        full_palette = DEFAULT_PALETTE.copy()
        if self._conf.has_section("palette"):
            palette = dict()
            for k, v in self._conf.items("palette"):
                v_items = [s.strip(" ") for s in v.split(",")]
                v_items = [tuple(s.split("+")) if "+" in s else s for s in v_items]
                palette[k] = tuple(v_items)
            # noinspection PyTypeChecker
            full_palette.update(palette)
        return [(k, *v) for k, v in sorted(full_palette.items())]

    @staticmethod
    def _true_false_none_value(value: str) -> typing.Union[bool, None]:
        """Detect True, False or None in a configuration entry."""
        if value.strip(" ") in ("false", "False", "0"):
            return False
        elif value.strip(" ") in ("True", "true", "1"):
            return True
        elif value.strip(" ") in ("None", "none", "Null", "null"):
            return None
        else:
            raise ValueError("Must be True, False or None. Not {!s}.".format(value))

    @property
    def terminal_properties(self) -> dict:
        """Read the necessary data to setup the Urwid screen object.

        A ``None`` value, means do not change the default.
        """
        return dict(
            colors=int(self._conf.get("urwid", "terminal_colors", fallback=0)) or None,
            bright_is_bold=self._true_false_none_value(
                self._conf.get("urwid", "terminal_bright_is_bold", fallback="None")
            ),
            has_underline=self._true_false_none_value(
                self._conf.get("urwid", "terminal_has_underline", fallback="None")
            ),
        )

    @property
    def handle_mouse(self) -> bool:
        """Allow mouse interactions."""
        return self._true_false_none_value(
            self._conf.get("urwid", "handle_mouse", fallback="False")
        )

    @property
    def double_keystroke_delay(self) -> float:
        """
        The delay between two keystrokes for them to be considered
        "duplicated" (in seconds)."""
        return float(self._conf.get("ui", "double_keystroke_delay", fallback="0.25"))

    @property
    def logviewer_command(self) -> typing.List[str]:
        """The command-line launched to visualise logfiles.

        {filename:s} will be substituted by the actual log file path.
        """
        return shlex.split(
            self._conf.get("ui", "logviewer_command", fallback="vim -R -N {filename:s}")
        )

    @property
    def cdp_default_path(self) -> typing.Union[str, None]:
        """The path to the CDP binary."""
        return self._conf.get("cdp", "path", fallback=None)

    @property
    def cdp_default_host(self) -> typing.Union[str, None]:
        """The default SMS server to connect to."""
        return self._conf.get("cdp", "host", fallback=None)

    @property
    def cdp_default_user(self) -> typing.Union[str, None]:
        """The default SMS user to connect with."""
        return self._conf.get("cdp", "user", fallback=None)

    @property
    def cdp_default_suite(self) -> typing.Union[str, None]:
        """The default SMS suite to work with."""
        return self._conf.get("cdp", "suite", fallback=None)


#: The go-to object to fetch some configuration data
tflowclient_conf = TFlowClientConfig()
