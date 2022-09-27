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
Test everything related to the tflowclient configuration parser
"""

import unittest

from tflowclient.conf import TFlowClientConfig


class TestConf(unittest.TestCase):
    """Unit-test class for the configuration parser."""

    _default_palette = [
        ("ABORTED", "black", "dark red"),
        ("ABORTED_f", "black", "dark red"),
        ("ACTIVE", "black", "dark green"),
        ("ACTIVE_f", "black", "dark green"),
        ("COMPLETE", "black", "yellow"),
        ("COMPLETE_f", "black", "yellow"),
        ("QUEUED", "black", "white"),
        ("QUEUED_f", "black", "white"),
        ("SUBMITTED", "black", "dark cyan"),
        ("SUBMITTED_f", "black", "dark cyan"),
        ("SUSPENDED", "black", "brown"),
        ("SUSPENDED_f", "black", "brown"),
        ("button", "black", "light gray"),
        ("button_f", "white", "dark blue", "bold"),
        ("editable", "black", "light gray"),
        ("editable_f", "white", "dark blue", "bold"),
        ("flagged_treeline", "black", "dark magenta", ("bold", "underline")),
        ("flagged_treeline_f", "yellow", "dark magenta"),
        ("foot", "white", "black"),
        ("head", "yellow", "black", "standout"),
        ("key", "light cyan", "black", "underline"),
        ("title", "white", "black", "bold"),
        ("treeline", "black", "light gray"),
        ("treeline_f", "light gray", "dark blue", "standout"),
        ("warning", "black", "brown"),
    ]

    def assertPaletteConf(self, conf_line, expected, new=False):
        """Assert if the palette is properly read from file."""
        res = TFlowClientConfig(
            conf_txt="""
            [palette]
            {:s}
            """.format(
                conf_line
            )
        ).palette
        self.assertIn(expected, res)
        self.assertEqual(len(res), len(self._default_palette) + int(new))

    def test_palette(self):
        """Test the palette reading."""
        self.assertListEqual(
            TFlowClientConfig(conf_txt="").palette, self._default_palette
        )
        self.assertPaletteConf(
            "treeline =  yellow,  dark green", ("treeline", "yellow", "dark green")
        )
        self.assertPaletteConf(
            "treeline=yellow,dark blue", ("treeline", "yellow", "dark blue")
        )
        self.assertPaletteConf(
            "treeline=yellow,dark blue,  bold+strikeout",
            ("treeline", "yellow", "dark blue", ("bold", "strikeout")),
        )
        self.assertPaletteConf(
            "ABORTED_f=yellow,dark blue,  bold+strikeout",
            ("ABORTED_f", "yellow", "dark blue", ("bold", "strikeout")),
        )

    def test_urwid_stuff(self):
        """Test urwid related config."""
        self.assertEqual(TFlowClientConfig(conf_txt="").urwid_backend, "raw")
        self.assertEqual(
            TFlowClientConfig(
                conf_txt="""[urwid]
            backend= curses
            """
            ).urwid_backend,
            "curses",
        )
        self.assertEqual(
            TFlowClientConfig(
                conf_txt="""[urwid]
                    handle_mouse= 1
                    """
            ).handle_mouse,
            True,
        )
        self.assertEqual(
            TFlowClientConfig(
                conf_txt="""[urwid]
            terminal_colors= 256
            """
            ).terminal_properties,
            dict(colors=256, has_underline=None, bright_is_bold=None),
        )
        self.assertEqual(
            TFlowClientConfig(
                conf_txt="""[urwid]
            terminal_has_underline= False
            terminal_bright_is_bold=  none
            """
            ).terminal_properties,
            dict(colors=None, has_underline=False, bright_is_bold=None),
        )
        self.assertEqual(
            TFlowClientConfig(
                conf_txt="""[urwid]
            terminal_has_underline= 1
            terminal_bright_is_bold=  0
            """
            ).terminal_properties,
            dict(colors=None, has_underline=True, bright_is_bold=False),
        )
        with self.assertRaises(ValueError):
            assert TFlowClientConfig(
                conf_txt="""[urwid]
                terminal_has_underline= hello
                """
            ).terminal_properties

    def test_ui_stuff(self):
        self.assertEqual(TFlowClientConfig(conf_txt="").double_keystroke_delay, 0.25)
        self.assertEqual(
            TFlowClientConfig(
                conf_txt="""[ui]
                    double_keystroke_delay=0.5
                    """
            ).double_keystroke_delay,
            0.5,
        )
        with self.assertRaises(ValueError):
            assert TFlowClientConfig(
                conf_txt="""[ui]
                double_keystroke_delay=toto
                """
            ).double_keystroke_delay
        self.assertEqual(
            TFlowClientConfig(conf_txt="").logviewer_command,
            ["vim", "-R", "-N", "{filename:s}"],
        )
        self.assertEqual(
            TFlowClientConfig(
                conf_txt="""[ui]
                            logviewer_command=shell   lexer \
                                was here
                            """
            ).logviewer_command,
            ["shell", "lexer", "was", "here"],
        )

    def test_cdp_stuff(self):
        """Test SMS/CDP related config."""
        self.assertEqual(TFlowClientConfig(conf_txt="").cdp_default_host, None)
        self.assertEqual(TFlowClientConfig(conf_txt="").cdp_default_user, None)
        self.assertEqual(TFlowClientConfig(conf_txt="").cdp_default_suite, None)
        self.assertEqual(TFlowClientConfig(conf_txt="").cdp_default_path, None)
        t_flow_conf = TFlowClientConfig(
            conf_txt="""[cdp]
        path=toto
        suite=groucho
        user=groucho
        host=server
        """
        )
        self.assertEqual(t_flow_conf.cdp_default_host, "server")
        self.assertEqual(t_flow_conf.cdp_default_user, "groucho")
        self.assertEqual(t_flow_conf.cdp_default_suite, "groucho")
        self.assertEqual(t_flow_conf.cdp_default_path, "toto")


if __name__ == "__main__":
    unittest.main()
