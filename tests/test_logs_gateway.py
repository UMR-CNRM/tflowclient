# -*- coding: utf-8 -*-

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
            get_logs_gateway(kind='not_existing')
        with self.assertRaises(ValueError):
            get_logs_gateway(kind='demo', someargument='toto')
        demo_g = get_logs_gateway(kind='demo')
        self.assertIsInstance(demo_g, LogsGateway)

    def test_demo_gateway(self):
        demo_g = get_logs_gateway(kind='demo')
        self.assertListEqual(demo_g.list_file('/toto/task'),
                             ['task.1', 'task.job1', 'task.sms'])
        self.assertEqual(demo_g.get_as_str('/toto/task', 'task.job1'),
                         _DEMO_LOG_FILE_RESULT)
        with demo_g.get_as_file('/toto/task', 'task.job1') as t_file:
            self.assertTrue(os.path.exists(t_file.name))
            t_file.seek(0)
            self.assertEqual(t_file.read(), _DEMO_LOG_FILE_RESULT)
        self.assertFalse(os.path.exists(t_file.name))


if __name__ == '__main__':
    unittest.main()
