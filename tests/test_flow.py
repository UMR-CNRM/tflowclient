# -*- coding: utf-8 -*-

import time
import unittest

from tflowclient.flow import FlowStatus, RootFlowNode
from tflowclient.observer import Observer, Subject

RES_STR_20200114_12 = """[ABORTED]_12
  [ACTIVE]_production
    [QUEUED]_obsextract
    [ACTIVE]_obsextract_surf
  [ABORTED]_assim
    [ABORTED]_obsextract
    [SUBMITTED]_obsextract_surf"""


class FlowTestObserver(Observer):

    def __init__(self):
        self.slurp = set()

    def update_obs_item(self, item: Subject, info: dict):
        if info['flagged']:
            self.slurp.add(id(item))
        else:
            self.slurp.remove(id(item))


class TestFlow(unittest.TestCase):

    @staticmethod
    def _build_demo_flow():
        r_fn = RootFlowNode('A157', FlowStatus.ABORTED)
        f_d14 = r_fn.add('20200114', FlowStatus.ABORTED)
        f_00 = f_d14.add('00', FlowStatus.COMPLETE)
        for cutoff in ('production', 'assim'):
            f_cutoff = f_00.add(cutoff, FlowStatus.COMPLETE)
            f_cutoff.add('obsextract', FlowStatus.COMPLETE)
        f_12 = f_d14.add('12', FlowStatus.ABORTED)
        f_prod = f_12.add('production', FlowStatus.ACTIVE)
        f_prod.add('obsextract', FlowStatus.QUEUED)
        f_prod.add('obsextract_surf', FlowStatus.ACTIVE)
        f_assim = f_12.add('assim', FlowStatus.ABORTED)
        f_assim.add('obsextract', FlowStatus.ABORTED)
        f_assim.add('obsextract_surf', FlowStatus.SUBMITTED)
        return r_fn

    def test_root_flow(self):
        rfn = self._build_demo_flow()
        time.sleep(0.05)
        self.assertTrue(rfn.age > 0.05)
        rfn_bis = self._build_demo_flow()
        rfn_bis_obs = FlowTestObserver()
        for cutoff in ('assim', 'production'):
            rfn_bis['20200114']['12'][cutoff]['obsextract'].observer_attach(rfn_bis_obs)
            rfn_bis['20200114']['12'][cutoff]['obsextract_surf'].observer_attach(rfn_bis_obs)
        self.assertEqual(rfn.name, 'A157')
        self.assertEqual(rfn.status, FlowStatus.ABORTED)
        self.assertIs(rfn.parent, None)
        self.assertTrue(rfn.expanded)
        self.assertIs(rfn['20200114'].parent, rfn)
        self.assertTrue(rfn['20200114'].expanded)
        self.assertFalse(rfn['20200114']['00'].expanded)
        self.assertTrue(rfn['20200114']['12'].expanded)
        self.assertTrue(rfn['20200114']['12']['production'].expanded)
        self.assertTrue(rfn['20200114']['12']['production']['obsextract_surf'].expanded)
        self.assertTrue(rfn['20200114']['12']['assim'].expanded)
        self.assertIs(rfn.first_expanded_leaf(),
                      rfn['20200114']['12']['production']['obsextract_surf'])
        self.assertEqual(rfn['20200114']['12']['assim'].path,
                         '20200114/12/assim')
        self.assertEqual(str(rfn['20200114']['12']), RES_STR_20200114_12)
        self.assertEqual(rfn, rfn_bis)
        self.assertNotEqual(rfn, 'toto')
        self.assertIn('00', rfn['20200114'])
        self.assertListEqual([f.name for f in rfn['20200114']],
                             ['00', '12'])
        self.assertEqual(len(rfn), 1)
        self.assertEqual(len(rfn['20200114']['12']), 2)
        self.assertIs(rfn.resolve_path('20200114/12/assim'),
                      rfn['20200114']['12']['assim'])
        self.assertIs(rfn.resolve_path(''), rfn)
        rfn_bis.flag_status(FlowStatus.ABORTED)
        rfn_bis.flag_status(FlowStatus.ACTIVE)
        self.assertNotEqual(rfn, rfn_bis)
        self.assertListEqual(rfn_bis.flagged_paths(),
                             ['A157/20200114/12/production/obsextract_surf',
                              'A157/20200114/12/assim/obsextract'])
        self.assertSetEqual(rfn_bis_obs.slurp,
                            {id(rfn_bis['20200114']['12']['production']['obsextract_surf']),
                             id(rfn_bis['20200114']['12']['assim']['obsextract'])})
        rfn_bis['20200114']['12']['assim']['obsextract'].flagged = False
        self.assertSetEqual(rfn_bis_obs.slurp,
                            {id(rfn_bis['20200114']['12']['production']['obsextract_surf'])})
        rfn_bis['20200114']['12']['production']['obsextract_surf'].observer_detach(rfn_bis_obs)
        rfn_bis.reset_flagged()
        self.assertEqual(rfn, rfn_bis)
        self.assertSetEqual(rfn_bis_obs.slurp,
                            {id(rfn_bis['20200114']['12']['production']['obsextract_surf'])})


if __name__ == '__main__':
    unittest.main()
