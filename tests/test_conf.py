# -*- coding: utf-8 -*-

import unittest

from tflowclient.conf import TFlowClientConfig


class TestConf(unittest.TestCase):

    _default_palette = [
        ("ABORTED", "black", "dark red"),
        ("ABORTED_f", "black", "dark red"),
        ("ACTIVE", "black", "dark green"),
        ("ACTIVE_f", "black", "dark green"),
        ("COMPLETED", "black", "light gray"),
        ("COMPLETED_f", "black", "light gray"),
        ("QUEUED", "black", "white"),
        ("QUEUED_f", "black", "white"),
        ("SUBMITTED", "black", "dark cyan"),
        ("SUBMITTED_f", "black", "dark cyan"),
        ("SUSPENDED", "black", "brown"),
        ("SUSPENDED_f", "black", "brown"),
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

    def test_cdp_stuff(self):
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
