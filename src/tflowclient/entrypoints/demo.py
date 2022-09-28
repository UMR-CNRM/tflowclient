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
This is a demonstration-only executable.

It creates a dummy flow scheduler family/tasks tree. Compared to the "real"
``tflowclient_sms.py`` executable, it does not require any external software
or server.
"""

import argparse
import os
import sys

from tflowclient import TFlowApplication
from tflowclient.conf import tflowclient_conf
from tflowclient import demo_flow


def main():
    """Start the CLqI interface"""

    tflowclient_conf.logging_config()

    # Process the command-line arguments
    program_name = os.path.basename(sys.argv[0])
    program_short_desc = program_name + " -- " + __doc__.lstrip("\n")
    # noinspection PyTypeChecker
    parser = argparse.ArgumentParser(
        description=program_short_desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-a",
        "--app",
        dest="app",
        action="store",
        default="TreeView",
        help="The app that should be started [default: %(default)s].",
    )
    args = parser.parse_args()

    demo = demo_flow.DemoFlowInterface("fakesuite")
    with demo:
        app = TFlowApplication(demo, app_name=args.app)
        app.main()
