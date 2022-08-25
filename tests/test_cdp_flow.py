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
Test on some of the SMS/CDP specific tools.
"""

from contextlib import contextmanager
import os
import tempfile
import unittest

from tflowclient.cdp_flow import (
    SmsRcReader,
    SmsRcPermissionsError,
    CdpOutputParserMixin,
)
from tflowclient.flow import RootFlowNode, FlowStatus, ExtraFlowNodeInfo


_CDP_STATIC_FULL_OUTPUT = """
Welcome to cdp version 4.4.14 compiled on lun. déc. 30 13:52:27 CET 2019
# MSG:SMS-CLIENT-LOGIN:groucho logged into localhost with password [812590]
/groucho/A157             {abo}   20200114     [abo]   00 [com]   production[com]   obsextract     {com}   
                                                                                    obsextract_surf{com}   

                                                                  assim     [com]   obsextract     [com]   
                                                                                    obsextract_surf[com]      

                                                       12 [abo]   production[act]   obsextract     {com}   
                                                                                    obsextract_surf{act}   

                                                                  assim     [abo]   obsextract     [abo]   
                                                                                    obsextract_surf[sub]      

                                  20200115     [que]   00 [que]   production[que]   obsextract     {que}   
                                                                                    obsextract_surf{que}   

                                                                  assim     [que]   obsextract     [que]   
                                                                                    obsextract_surf[que]      

                                                       12 [que]   production[que]   obsextract     {que}   
                                                                                    obsextract_surf{que}   

                                                                  assim     [que]   obsextract     [que]   
                                                                                    obsextract_surf[que]      

# MSG:SMS-CLIENT-LOGOUT:logout from localhost
Goodbye groucho
"""

_CDP_STATIC_SMALL_OUTPUT = """
Welcome to cdp version 4.4.14 compiled on lun. déc. 30 13:52:27 CET 2019
# MSG:SMS-CLIENT-LOGIN:groucho logged into localhost with password [812590]
groucho{que}   diagnostics{abo}

               A157       {abo}

               A158       {que}

# MSG:SMS-CLIENT-LOGOUT:logout from localhost
Goodbye groucho
"""

_CDP_STATIC_INFO_V_OUTPUT = """
Welcome to cdp version 4.4.14 compiled on lun. déc. 30 13:52:27 CET 2019
# MSG:SMS-CLIENT-LOGIN:groucho logged into localhost with password [812590]
//localhost/leffe/B9GN/20190228/00/production/fc/forecast [task] is active
Default status is:  queued
  limit version septembre 2018 - mo07_mocage@camsfcst-main.03 - TEST [running 0 max 0]
  limit running [running 1 max 3]
       /leffe/B9GN/20190228/00/production/fc/forecast [active]
Flags set: has user messages
Current try number: 1
  METER work is 3 limits are [0 - 6]
  LABEL jobid 'beaufixcn:85583522--mtool:407991'
repeat date variable YMD from 20210616 to 20211231 step 1 currently 20210616
Nodes triggered by this node
    /leffe/B9GN/20190228/00/production/fc/post_bdap
Nodes that trigger this node
    /leffe/B9GN/20190228/00/production/fc/topbd [complete]
    /leffe/B9GN/20190227/00/production/fc_init/control_guess/clim_restart [complete]
Variables
    (TASK         = forecast                                                                 ) []
    (SMSNAME      = /leffe/B9GN/20190228/00/production/fc/forecast                           ) []
    (FAMILY       = B9GN/20190228/00/production/fc                                           ) [/leffe/B9GN]
     SMSTRIES     = 2                                                                          [/leffe]
     SMSINCLUDE   = /home/verolive/swapp/repository/sms/include                                [/leffe]
    (SUITE        = leffe                                                                    ) [/leffe]
     SMSNODE      = cxsms5.cnrm.meteo.fr                                                       [/]
"""

_SMSRC_EXAMPLE = "thehost.meteo.fr test fancy_password"


def _ini_cdp_static_full_flow():
    r_fn = RootFlowNode("A157", FlowStatus.ABORTED)
    f_d14 = r_fn.add("20200114", FlowStatus.ABORTED)
    f_00 = f_d14.add("00", FlowStatus.COMPLETE)
    for cutoff in ("production", "assim"):
        f_cutoff = f_00.add(cutoff, FlowStatus.COMPLETE)
        f_cutoff.add("obsextract", FlowStatus.COMPLETE)
        f_cutoff.add("obsextract_surf", FlowStatus.COMPLETE)
    f_12 = f_d14.add("12", FlowStatus.ABORTED)
    f_prod = f_12.add("production", FlowStatus.ACTIVE)
    f_prod.add("obsextract", FlowStatus.COMPLETE)
    f_prod.add("obsextract_surf", FlowStatus.ACTIVE)
    f_assim = f_12.add("assim", FlowStatus.ABORTED)
    f_assim.add("obsextract", FlowStatus.ABORTED)
    f_assim.add("obsextract_surf", FlowStatus.SUBMITTED)
    f_d15 = r_fn.add("20200115", FlowStatus.QUEUED)
    for hh in ("00", "12"):
        f_hh = f_d15.add(hh, FlowStatus.QUEUED)
        for cutoff in ("production", "assim"):
            f_cutoff = f_hh.add(cutoff, FlowStatus.QUEUED)
            f_cutoff.add("obsextract", FlowStatus.QUEUED)
            f_cutoff.add("obsextract_surf", FlowStatus.QUEUED)
    return r_fn


class TestCdpOutputParserMixin(CdpOutputParserMixin):
    """Test class intended to test tje CDp mixin."""

    @property
    def suite(self):
        """The fake suite name."""
        return "groucho"


class TestCdpFlow(unittest.TestCase):
    """Unit test class for SMS/CDP specific tools."""

    def test_cdp_output_parser(self):
        """Test the status parser."""
        self.assertEqual(
            TestCdpOutputParserMixin()._parse_status_output(_CDP_STATIC_FULL_OUTPUT),
            dict(A157=_ini_cdp_static_full_flow()),
        )
        self.assertEqual(
            TestCdpOutputParserMixin()._parse_status_output(_CDP_STATIC_SMALL_OUTPUT),
            dict(
                diagnostics=RootFlowNode("diagnostics", FlowStatus.ABORTED),
                A157=RootFlowNode("A157", FlowStatus.ABORTED),
                A158=RootFlowNode("A158", FlowStatus.QUEUED),
            ),
        )
        self.assertEqual(
            TestCdpOutputParserMixin()._parse_status_output(
                _CDP_STATIC_SMALL_OUTPUT + _CDP_STATIC_FULL_OUTPUT
            ),
            dict(
                diagnostics=RootFlowNode("diagnostics", FlowStatus.ABORTED),
                A157=_ini_cdp_static_full_flow(),
                A158=RootFlowNode("A158", FlowStatus.QUEUED),
            ),
        )

    def test_cdp_info_parser(self):
        """Test the info parser."""
        self.assertEqual(
            TestCdpOutputParserMixin()._parse_info_outputs(_CDP_STATIC_INFO_V_OUTPUT),
            [
                ExtraFlowNodeInfo(
                    "limit",
                    "version septembre 2018 - mo07_mocage@camsfcst-main.03 - TEST",
                    "0",
                    "currently running: 0 - Use the 'reset' special value to reset things",
                    editable=True,
                ),
                ExtraFlowNodeInfo(
                    "limit",
                    "running",
                    "3",
                    "currently running: 1 - Use the 'reset' special value to reset things",
                    editable=True,
                ),
                ExtraFlowNodeInfo("flowspecific", "CurrentTryNumber", "1"),
                ExtraFlowNodeInfo(
                    "meter",
                    "work",
                    "3",
                    "limits are [0 - 6]",
                    editable=True,
                ),
                ExtraFlowNodeInfo("label", "jobid", "beaufixcn:85583522--mtool:407991"),
                ExtraFlowNodeInfo(
                    "repeat",
                    "YMD",
                    "20210616",
                    "type: date. info: from 20210616 to 20211231 step 1",
                    editable=True,
                ),
                ExtraFlowNodeInfo(
                    "trigger",
                    "/leffe/B9GN/20190228/00/production/fc/topbd",
                    "[complete]",
                ),
                ExtraFlowNodeInfo(
                    "trigger",
                    "/leffe/B9GN/20190227/00/production/fc_init/control_guess/clim_restart",
                    "[complete]",
                ),
                ExtraFlowNodeInfo(
                    "flowspecific",
                    "MaxTries",
                    "2",
                    "inherited from '/leffe'",
                    editable=True,
                ),
            ],
        )

    @contextmanager
    def _create_tmp_smsrc(self, content: str):
        """Create a fake .smsrc file"""
        tmp_fh = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", delete=False
            ) as tmp_fh:
                tmp_fh.write(content)
            yield tmp_fh.name
        finally:
            if tmp_fh:
                os.remove(tmp_fh.name)

    def test_sms_rc_reader(self):
        """Test the .smsrc file reader."""
        # Empty file...
        with self._create_tmp_smsrc("") as rc_file:
            for mode in (0o644, 0o640, 0o722):
                os.chmod(rc_file, mode)
                with self.assertRaises(SmsRcPermissionsError):
                    assert SmsRcReader(rc_file)
            os.chmod(rc_file, 0o600)
            with self.assertRaises(KeyError):
                assert SmsRcReader(rc_file).get_password("any_host", "any_user")
        # Real life...
        with self._create_tmp_smsrc(_SMSRC_EXAMPLE) as rc_file:
            os.chmod(rc_file, 0o600)
            s_rc = SmsRcReader(rc_file)
            self.assertEqual(
                s_rc.get_password("thehost.meteo.fr", "test"), "fancy_password"
            )
            self.assertEqual(s_rc.get_password("thehost", "test"), "fancy_password")
            with self.assertRaises(KeyError):
                assert s_rc.get_password("thehost", "other")


if __name__ == "__main__":
    unittest.main()
