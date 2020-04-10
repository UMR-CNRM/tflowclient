#! /usr/bin/env python3
# -*- coding: utf-8 -*-

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

if __name__ == '__main__':
    # Setup the logging facility
    tflowclient_conf.logging_config()

    # Detect an existing CDP utility somewhere in $PATH
    cdp_from_path = None
    for path in os.get_exec_path():
        the_cdp = os.path.join(path, 'cdp')
        if os.path.exists(the_cdp):
            cdp_from_path = the_cdp
            break

    # Process the command-line arguments
    program_name = os.path.basename(sys.argv[0])
    program_short_desc = program_name + ' -- ' + __import__('__main__').__doc__.lstrip("\n")
    parser = argparse.ArgumentParser(description=program_short_desc, epilog=EPILOG_STR,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--cdp", dest="cdp", action="store",
                        default=tflowclient_conf.cdp_default_path or cdp_from_path,
                        help="The path to the CDP binary [default: %(default)s].")
    parser.add_argument("-s", "--server", dest="server", action="store",
                        default=tflowclient_conf.cdp_default_host,
                        help="The SMS server to connect to [default: %(default)s].")
    parser.add_argument("-u", "--user", dest="user", action="store",
                        default=tflowclient_conf.cdp_default_user,
                        help=("The user required to login to the SMS server " +
                              "[default: %(default)s]."))
    parser.add_argument("-r", "--rootsuite", dest="suite", action="store",
                        default=tflowclient_conf.cdp_default_suite,
                        help="The SMS suite to follow [default: %(default)s].")
    args = parser.parse_args()

    # Sanity checks
    def _arg_assert(item, description):
        if item is None:
            parser.print_help()
            raise ValueError(description + ' needs to be provided.')
    _arg_assert(args.cdp, 'A path to the CDP utility')
    _arg_assert(args.server, 'An SMS server host name')
    _arg_assert(args.user, 'A SMS user name')
    _arg_assert(args.suite, 'A SMS suite to monitor')

    # Lookup for a password in ~/.smsrc
    password = cdp_flow.SmsRcReader().get_password(args.server, args.user)

    # Let's go
    cdp = cdp_flow.CdpInterface(args.suite)
    cdp.credentials = dict(cdp_path=args.cdp, host=args.server, user=args.user,
                           password=password)
    app = TFlowApplication(cdp)
    app.main()
