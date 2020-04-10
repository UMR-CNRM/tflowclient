# -*- coding: utf-8 -*-

from contextlib import contextmanager
import os
import tempfile
import unittest

from tflowclient.cdp_flow import SmsRcReader, SmsRcPermissionsError, CdpOutputParserMixin
from tflowclient.flow import RootFlowNode, FlowStatus


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

_SMSRC_EXAMPLE = "thehost.meteo.fr test fancy_password"


def _ini_cdp_static_full_flow():
    r_fn = RootFlowNode('A157', FlowStatus.ABORTED)
    f_d14 = r_fn.add('20200114', FlowStatus.ABORTED)
    f_00 = f_d14.add('00', FlowStatus.COMPLETE)
    for cutoff in ('production', 'assim'):
        f_cutoff = f_00.add(cutoff, FlowStatus.COMPLETE)
        f_cutoff.add('obsextract', FlowStatus.COMPLETE)
        f_cutoff.add('obsextract_surf', FlowStatus.COMPLETE)
    f_12 = f_d14.add('12', FlowStatus.ABORTED)
    f_prod = f_12.add('production', FlowStatus.ACTIVE)
    f_prod.add('obsextract', FlowStatus.COMPLETE)
    f_prod.add('obsextract_surf', FlowStatus.ACTIVE)
    f_assim = f_12.add('assim', FlowStatus.ABORTED)
    f_assim.add('obsextract', FlowStatus.ABORTED)
    f_assim.add('obsextract_surf', FlowStatus.SUBMITTED)
    f_d15 = r_fn.add('20200115', FlowStatus.QUEUED)
    for hh in ('00', '12'):
        f_hh = f_d15.add(hh, FlowStatus.QUEUED)
        for cutoff in ('production', 'assim'):
            f_cutoff = f_hh.add(cutoff, FlowStatus.QUEUED)
            f_cutoff.add('obsextract', FlowStatus.QUEUED)
            f_cutoff.add('obsextract_surf', FlowStatus.QUEUED)
    return r_fn


class TestCdpOutputParserMixin(CdpOutputParserMixin):

    @property
    def suite(self):
        return 'groucho'


class TestCdpFlow(unittest.TestCase):

    def test_cdp_output_parser(self):
        self.assertEqual(TestCdpOutputParserMixin()._parse_status_output(_CDP_STATIC_FULL_OUTPUT),
                         dict(A157=_ini_cdp_static_full_flow()))
        self.assertEqual(TestCdpOutputParserMixin()._parse_status_output(_CDP_STATIC_SMALL_OUTPUT),
                         dict(diagnostics=RootFlowNode('diagnostics', FlowStatus.ABORTED),
                              A157=RootFlowNode('A157', FlowStatus.ABORTED),
                              A158=RootFlowNode('A158', FlowStatus.QUEUED),))
        self.assertEqual(TestCdpOutputParserMixin()._parse_status_output(_CDP_STATIC_SMALL_OUTPUT
                                                                         + _CDP_STATIC_FULL_OUTPUT),
                         dict(diagnostics=RootFlowNode('diagnostics', FlowStatus.ABORTED),
                              A157=_ini_cdp_static_full_flow(),
                              A158=RootFlowNode('A158', FlowStatus.QUEUED), ))

    @contextmanager
    def _create_tmp_smsrc(self, content: str):
        tmp_fh = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as tmp_fh:
                tmp_fh.write(content)
            yield tmp_fh.name
        finally:
            if tmp_fh:
                os.remove(tmp_fh.name)

    def test_sms_rc_reader(self):
        # Empty file...
        with self._create_tmp_smsrc("") as rc_file:
            for mode in (0o644, 0o640, 0o722):
                os.chmod(rc_file, mode)
                with self.assertRaises(SmsRcPermissionsError):
                    assert SmsRcReader(rc_file)
            os.chmod(rc_file, 0o600)
            with self.assertRaises(KeyError):
                assert SmsRcReader(rc_file).get_password('any_host', 'any_user')
        # Real life...
        with self._create_tmp_smsrc(_SMSRC_EXAMPLE) as rc_file:
            os.chmod(rc_file, 0o600)
            s_rc = SmsRcReader(rc_file)
            self.assertEqual(s_rc.get_password('thehost.meteo.fr', 'test'),
                             'fancy_password')
            self.assertEqual(s_rc.get_password('thehost', 'test'),
                             'fancy_password')
            with self.assertRaises(KeyError):
                assert s_rc.get_password('thehost', 'other')


if __name__ == '__main__':
    unittest.main()
