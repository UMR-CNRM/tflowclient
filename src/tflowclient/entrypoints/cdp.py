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
This is a Text-based workFlow Scheduler Client
based on the SMS' CDP utility.
"""

import argparse
import os
import sys

from tflowclient import TFlowApplication
from tflowclient.conf import tflowclient_conf
from tflowclient import cdp_flow

EPILOG_STR = """
Note: Default path to CDP and SMS credentials can be added to the user-wide
      configuration file (~/.tflowclientrc.ini) in order to command without
      any argument. For instance:
      
      [cdp]
      path=path_to_cdp
      host=sms_server.meteo.fr
      user=username
      suite=suitename
"""


def main():
    """Start the CLI interface"""

    # Setup the logging facility
    tflowclient_conf.logging_config()

    # Detect an existing CDP utility somewhere in $PATH
    cdp_from_path = None
    for path in os.get_exec_path():
        the_cdp = os.path.join(path, "cdp")
        if os.path.exists(the_cdp):
            cdp_from_path = the_cdp
            break

    # Process the command-line arguments
    program_name = os.path.basename(sys.argv[0])
    program_short_desc = program_name + " -- " + __doc__.lstrip("\n")
    # noinspection PyTypeChecker
    parser = argparse.ArgumentParser(
        description=program_short_desc,
        epilog=EPILOG_STR,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--cdp",
        dest="cdp",
        action="store",
        default=tflowclient_conf.cdp_default_path or cdp_from_path,
        help="The path to the CDP binary [default: %(default)s].",
    )
    parser.add_argument(
        "-a",
        "--app",
        dest="app",
        action="store",
        default="TreeView",
        help="The app that should be started [default: %(default)s].",
    )
    parser.add_argument(
        "-s",
        "--server",
        dest="server",
        action="store",
        default=tflowclient_conf.cdp_default_host,
        help="The SMS server to connect to [default: %(default)s].",
    )
    parser.add_argument(
        "-u",
        "--user",
        dest="user",
        action="store",
        default=tflowclient_conf.cdp_default_user,
        help=(
            "The user required to login to the SMS server " + "[default: %(default)s]."
        ),
    )
    parser.add_argument(
        "-r",
        "--rootsuite",
        dest="suite",
        action="store",
        default=tflowclient_conf.cdp_default_suite,
        help="The SMS suite to follow [default: %(default)s].",
    )
    args = parser.parse_args()

    # Sanity checks
    def _arg_assert(item, description):
        if item is None:
            parser.print_help()
            raise ValueError(description + " needs to be provided.")

    _arg_assert(args.cdp, "A path to the CDP utility")
    _arg_assert(args.server, "An SMS server host name")
    _arg_assert(args.user, "A SMS user name")
    _arg_assert(args.suite, "A SMS suite to monitor")

    # Lookup for a password in ~/.smsrc
    password = cdp_flow.SmsRcReader().get_password(args.server, args.user)

    # Let's go
    cdp = cdp_flow.CdpInterface(args.suite)
    cdp.credentials = dict(
        cdp_path=args.cdp, host=args.server, user=args.user, password=password
    )
    with cdp:
        app = TFlowApplication(cdp, app_name=args.app)
        app.main()
