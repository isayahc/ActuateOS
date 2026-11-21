"""Offline checks for the benchmark reconstruction boundary; no API calls."""
import copy
import unittest

from video_pipeline import validate_analysis


class AnalysisBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.analysis={"title":"test","summary":"visible procedure","uncertainties":["sampled frames"],"steps":[
            {"id":"s1","title":"join","start_s":0,"end_s":4,"objects":["beam"],"evidence":"visible at 2s","uncertainty":"occluded","depends_on":[]},
            {"id":"s2","title":"fasten","start_s":4,"end_s":8,"objects":["nut"],"evidence":"visible at 6s","uncertainty":"torque unknown","depends_on":["s1"]},
        ]}

    def test_valid_reconstruction(self):
        validate_analysis(self.analysis,10)

    def test_invalid_time_or_references(self):
        for field,value in [("start_s",-1),("end_s",11),("end_s",float("nan")),("depends_on",["missing"]),("id","s2")]:
            with self.subTest(field=field,value=value):
                invalid=copy.deepcopy(self.analysis)
                invalid["steps"][0][field]=value
                with self.assertRaises(ValueError):validate_analysis(invalid,10)

    def test_cycle(self):
        self.analysis["steps"][0]["depends_on"]=["s2"]
        with self.assertRaises(ValueError):validate_analysis(self.analysis,10)

    def test_evidence_is_required(self):
        del self.analysis["steps"][0]["evidence"]
        with self.assertRaises(ValueError):validate_analysis(self.analysis,10)


if __name__=="__main__":unittest.main()
