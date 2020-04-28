# -*- coding: utf-8 -*-

from datetime import datetime
import os
import unittest

from tflowclient.logs_gateway import get_logs_gateway, LogsGateway

_DEMO_LOG_FILE_RESULT = """This is a demo logfile.

It has been generating for task:
/toto/task

and log_file:
task.job1
"""


class TestLogsGateway(unittest.TestCase):
    def test_gateway_factory(self):
        with self.assertRaises(ValueError):
            get_logs_gateway(kind="not_existing")
        with self.assertRaises(ValueError):
            get_logs_gateway(kind="demo", someargument="toto")
        demo_g = get_logs_gateway(kind="demo")
        self.assertIsInstance(demo_g, LogsGateway)

    def test_demo_gateway(self):
        demo_g = get_logs_gateway(kind="demo")
        self.assertListEqual(
            demo_g.list_file("/toto/task"),
            [
                ("task.1", datetime(2020, 1, 1, 0, 10, 0)),
                ("task.job1", datetime(2020, 1, 1, 0, 5, 0)),
                ("task.sms", datetime(2020, 1, 1, 0, 0, 0)),
            ],
        )
        self.assertEqual(
            demo_g.get_as_str("/toto/task", "task.job1"), _DEMO_LOG_FILE_RESULT
        )
        with demo_g.get_as_file("/toto/task", "task.job1") as t_file:
            self.assertTrue(os.path.exists(t_file.name))
            t_file.seek(0)
            self.assertEqual(t_file.read(), _DEMO_LOG_FILE_RESULT)
        self.assertFalse(os.path.exists(t_file.name))

    def test_cdp_gateway(self):
        # Just test the ping method...
        sms_g = get_logs_gateway(
            kind="sms_log_svr", host="not_existing.for.sure.fr", port=12345, path="/tmp"
        )
        self.assertFalse(sms_g.ping(connect_timeout=0.2))


if __name__ == "__main__":
    unittest.main()
