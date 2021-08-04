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
Test the log gateway classes.
"""

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
    """Unit-test class for the log gateways."""

    def test_gateway_factory(self):
        """Test the factory method."""
        with self.assertRaises(ValueError):
            get_logs_gateway(kind="not_existing")
        with self.assertRaises(ValueError):
            get_logs_gateway(kind="demo", someargument="toto")
        demo_g = get_logs_gateway(kind="demo")
        self.assertIsInstance(demo_g, LogsGateway)

    # noinspection PyUnresolvedReferences
    def test_demo_gateway(self):
        """Test the Demo gateway."""
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
        """Test the SMS log gateway."""
        # Just test the ping method...
        sms_g = get_logs_gateway(
            kind="sms_log_svr",
            host="not_existing.for.sure.fr",
            port=12345,
            paths=[
                "/tmp",
            ],
        )
        self.assertFalse(sms_g.ping(connect_timeout=0.2))


if __name__ == "__main__":
    unittest.main()
