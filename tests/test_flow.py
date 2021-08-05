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
Test the FlowNode class and related tools.
"""

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
    """Fake observer for test purposes."""

    def __init__(self):
        """Initialise the slurp set of messages"""
        self.slurp = set()

    def update_obs_item(self, item: Subject, info: dict):
        """Listen to flagged nodes."""
        if info["flagged"]:
            self.slurp.add(id(item))
        else:
            self.slurp.remove(id(item))


class TestFlow(unittest.TestCase):
    """Unit-test class for FlowNode."""

    @staticmethod
    def _build_demo_flow(failed=True, minor=False, fulltree=True) -> RootFlowNode:
        """Build a demonstration FlowNode object hierarchy."""
        r_fn = RootFlowNode(
            "A157", FlowStatus.ABORTED if (failed and fulltree) else FlowStatus.ACTIVE
        )
        f_d14 = r_fn.add(
            "20200114",
            FlowStatus.ABORTED if (failed and fulltree) else FlowStatus.ACTIVE,
        )
        f_00 = f_d14.add("00", FlowStatus.COMPLETE)
        for cutoff in ("production", "assim"):
            f_cutoff = f_00.add(cutoff, FlowStatus.COMPLETE)
            f_cutoff.add("obsextract", FlowStatus.COMPLETE)
        f_12 = f_d14.add(
            "12", FlowStatus.ABORTED if (failed and fulltree) else FlowStatus.ACTIVE
        )
        f_prod = f_12.add("production", FlowStatus.ACTIVE)
        f_prod.add("obsextract", FlowStatus.QUEUED)
        f_prod.add("obsextract_surf", FlowStatus.ACTIVE)
        if fulltree:
            f_assim = f_12.add(
                "assim", FlowStatus.ABORTED if failed else FlowStatus.ACTIVE
            )
            f_assim.add(
                "obsextract", FlowStatus.ABORTED if failed else FlowStatus.ACTIVE
            )
            f_assim.add(
                "obsextract_surf", FlowStatus.ACTIVE if minor else FlowStatus.SUBMITTED
            )
        return r_fn

    def test_root_flow(self):
        """Test the FlowNode objects."""
        rfn = self._build_demo_flow()
        time.sleep(0.05)
        self.assertTrue(rfn.age > 0.05)
        rfn_bis = self._build_demo_flow()
        rfn_bis_obs = FlowTestObserver()
        for cutoff in ("assim", "production"):
            rfn_bis["20200114"]["12"][cutoff]["obsextract"].observer_attach(rfn_bis_obs)
            rfn_bis["20200114"]["12"][cutoff]["obsextract_surf"].observer_attach(
                rfn_bis_obs
            )
        self.assertEqual(rfn.name, "A157")
        self.assertEqual(rfn.status, FlowStatus.ABORTED)
        self.assertIs(rfn.parent, None)
        self.assertTrue(rfn.expanded)
        self.assertIs(rfn["20200114"].parent, rfn)
        self.assertTrue(rfn["20200114"].expanded)
        self.assertFalse(rfn["20200114"]["00"].expanded)
        self.assertTrue(rfn["20200114"]["12"].expanded)
        self.assertTrue(rfn["20200114"]["12"]["production"].expanded)
        self.assertTrue(rfn["20200114"]["12"]["production"]["obsextract_surf"].expanded)
        self.assertTrue(rfn["20200114"]["12"]["assim"].expanded)
        self.assertIs(
            rfn.first_expanded_leaf(),
            rfn["20200114"]["12"]["production"]["obsextract_surf"],
        )
        self.assertEqual(rfn["20200114"]["12"]["assim"].path, "20200114/12/assim")
        self.assertEqual(
            rfn["20200114"]["12"]["assim"].full_path, "A157/20200114/12/assim"
        )
        self.assertEqual(str(rfn["20200114"]["12"]), RES_STR_20200114_12)
        self.assertEqual(rfn, rfn_bis)
        self.assertNotEqual(rfn, "toto")
        self.assertIn("00", rfn["20200114"])
        self.assertListEqual([f.name for f in rfn["20200114"]], ["00", "12"])
        self.assertEqual(len(rfn), 1)
        self.assertEqual(len(rfn["20200114"]["12"]), 2)
        self.assertIs(
            rfn.resolve_path("20200114/12/assim"), rfn["20200114"]["12"]["assim"]
        )
        self.assertIs(rfn.resolve_path(""), rfn)
        rfn_bis.flag_status(FlowStatus.ABORTED)
        rfn_bis.flag_status(FlowStatus.ACTIVE)
        self.assertEqual(rfn, rfn_bis)
        self.assertListEqual(
            rfn_bis.flagged_paths(),
            [
                "20200114/12/production/obsextract_surf",
                "20200114/12/assim/obsextract",
            ],
        )
        self.assertSetEqual(
            rfn_bis_obs.slurp,
            {
                id(rfn_bis["20200114"]["12"]["production"]["obsextract_surf"]),
                id(rfn_bis["20200114"]["12"]["assim"]["obsextract"]),
            },
        )
        rfn_bis["20200114"]["12"]["assim"]["obsextract"].flagged = False
        self.assertSetEqual(
            rfn_bis_obs.slurp,
            {id(rfn_bis["20200114"]["12"]["production"]["obsextract_surf"])},
        )
        rfn_bis["20200114"]["12"]["production"]["obsextract_surf"].observer_detach(
            rfn_bis_obs
        )
        rfn_bis.reset_flagged()
        self.assertEqual(rfn, rfn_bis)
        self.assertSetEqual(
            rfn_bis_obs.slurp,
            {id(rfn_bis["20200114"]["12"]["production"]["obsextract_surf"])},
        )

    @staticmethod
    def _rfn_update(rfn: RootFlowNode, new_rfn: RootFlowNode) -> RootFlowNode:
        if rfn.focused is not None:
            new_rfn.ingest_focused(
                rfn.focused.path,
                rfn.blink_paths(),
            )
        new_rfn.ingest_flagged(rfn.flagged_paths())
        new_rfn.ingest_user_expanded(rfn.user_expanded_paths())
        return new_rfn

    def test_root_flow_update(self):
        rfn = self._build_demo_flow()
        rfn.focused = rfn["20200114"]["12"]["production"]["obsextract_surf"]
        rfn["20200114"]["12"]["production"]["obsextract_surf"].flagged = True
        rfn["20200114"].user_expanded = True
        rfn["20200114"]["12"].user_expanded = True
        rfn["20200114"]["12"]["production"].user_expanded = True
        rfn["20200114"]["12"]["assim"].user_expanded = False

        rfn = self._rfn_update(rfn, self._build_demo_flow())
        # No change -> focus sticks
        self.assertIs(
            rfn.focused, rfn["20200114"]["12"]["production"]["obsextract_surf"]
        )
        self.assertTrue(rfn["20200114"]["12"]["production"]["obsextract_surf"].flagged)
        rfn.flagged = True
        self.assertTrue(rfn["20200114"].user_expanded)
        self.assertTrue(rfn["20200114"]["12"].user_expanded)
        self.assertTrue(rfn["20200114"]["12"]["production"].user_expanded)
        # No change, consequently it remains folded
        self.assertFalse(rfn["20200114"]["12"]["assim"].user_expanded)

        # Minor change
        rfn = self._rfn_update(rfn, self._build_demo_flow(minor=True))
        self.assertTrue(rfn["20200114"]["12"]["production"]["obsextract_surf"].flagged)
        self.assertTrue(rfn.flagged)
        # This is a minor/neutral change, focus sticks
        self.assertIs(
            rfn.focused, rfn["20200114"]["12"]["production"]["obsextract_surf"]
        )
        # No changes in expansion
        self.assertDictEqual(
            rfn["20200114"].user_expanded_paths(),
            {
                "": (True, FlowStatus.ABORTED),
                "12": (True, FlowStatus.ABORTED),
                "12/production": (True, FlowStatus.ACTIVE),
                "12/assim": (False, FlowStatus.ABORTED),
            },
        )
        self.assertSetEqual(
            rfn["20200114"]["12"]["assim"]["obsextract"].blink_paths(), {""}
        )

        # Imporvement
        rfn = self._rfn_update(rfn, self._build_demo_flow(failed=False))
        self.assertTrue(rfn["20200114"]["12"]["production"]["obsextract_surf"].flagged)
        # This is an improvement, focus sticks
        self.assertIs(
            rfn.focused, rfn["20200114"]["12"]["production"]["obsextract_surf"]
        )
        # User expanded families remain...
        self.assertTrue(rfn["20200114"].user_expanded)
        self.assertTrue(rfn["20200114"]["12"].user_expanded)
        self.assertTrue(rfn["20200114"]["12"]["production"].user_expanded)
        del rfn["20200114"]["12"]["production"].user_expanded
        self.assertIsNone(rfn["20200114"]["12"]["production"].user_expanded)
        # However, user_expanded is reseted for changed items
        self.assertIsNone(rfn["20200114"]["12"]["assim"].user_expanded)
        rfn["20200114"]["12"]["assim"].user_expanded = False

        # Deterioration
        rfn = self._rfn_update(rfn, self._build_demo_flow())
        self.assertTrue(rfn["20200114"]["12"]["production"]["obsextract_surf"].flagged)
        # Focus and user_expanded are reseted !
        self.assertIsNone(rfn.focused)
        self.assertIsNone(rfn["20200114"]["12"]["assim"].user_expanded)
        rfn["20200114"]["12"]["assim"].user_expanded = True
        rfn["20200114"]["12"]["assim"].flagged = True
        rfn.focused = rfn.first_blink_leaf()
        self.assertIs(rfn.focused, rfn["20200114"]["12"]["assim"]["obsextract"])

        # Remove aborted elemnts from the Tree
        rfn = self._rfn_update(rfn, self._build_demo_flow(fulltree=False))
        self.assertNotIn("assim", rfn["20200114"]["12"])
        self.assertTrue(rfn["20200114"]["12"]["production"]["obsextract_surf"].flagged)
        self.assertTrue(rfn["20200114"].user_expanded)
        self.assertTrue(rfn["20200114"]["12"].user_expanded)


if __name__ == "__main__":
    unittest.main()
