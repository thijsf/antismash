# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

# for test files, silence irrelevant and noisy pylint warnings
# pylint: disable=no-self-use,protected-access,missing-docstring

import os
import unittest

from helperlibs.bio import seqio
from helperlibs.wrappers.io import TemporaryDirectory

import antismash
from antismash.common import path, record_processing
from antismash.common.test import helpers
from antismash.common.secmet import Record
from antismash.config import build_config, update_config, destroy_config
from antismash.modules import lanthipeptides
from antismash.modules.lanthipeptides import run_specific_analysis, LanthiResults
import antismash.modules.lanthipeptides.config as lanthi_config


class IntegrationLanthipeptides(unittest.TestCase):
    def setUp(self):
        self.options = build_config(["--minimal", "--enable-lanthipeptides"],
                                    isolated=True, modules=antismash.get_all_modules())
        self.set_fimo_enabled(True)

    def tearDown(self):
        destroy_config()

    def set_fimo_enabled(self, val):
        update_config({"without_fimo": not val})
        lanthi_config.get_config().fimo_present = val

    def gather_all_motifs(self, result):
        motifs = []
        for locii in result.clusters.values():
            for locus in locii:
                motifs.extend(result.motifs_by_locus[locus])
        return motifs

    def test_nisin_end_to_end(self):
        # skip fimo being disabled for this, we already test the computational
        # side elsewhere
        if self.options.without_fimo:
            return
        nisin = helpers.get_path_to_nisin_genbank()
        result = helpers.run_and_regenerate_results_for_module(nisin, lanthipeptides, self.options)
        assert list(result.motifs_by_locus) == ["nisB"]
        prepeptide = result.motifs_by_locus["nisB"][0]
        self.assertAlmostEqual(3336.0, prepeptide.molecular_weight, delta=0.05)

    def test_nisin(self):
        "Test lanthipeptide prediction for nisin A"
        rec = Record.from_biopython(seqio.read(helpers.get_path_to_nisin_with_detection()), taxon="bacteria")
        assert not rec.get_cds_motifs()
        result = run_specific_analysis(rec)
        assert len(result.clusters) == 1
        motifs = self.gather_all_motifs(result)
        assert len(motifs) == 1
        assert not rec.get_cds_motifs()
        result.add_to_record(rec)
        assert len(rec.get_cds_motifs()) == 1
        prepeptide = motifs[0]
        # real monoisotopic mass is 3351.51, but we overpredict a Dha
        self.assertAlmostEqual(3333.6, prepeptide.monoisotopic_mass, delta=0.05)
        # real mw is 3354.5, see above
        self.assertAlmostEqual(3336.0, prepeptide.molecular_weight, delta=0.05)
        for expected, calculated in zip([3354.0, 3372.1, 3390.1, 3408.1],
                                        prepeptide.alternative_weights):
            self.assertAlmostEqual(expected, calculated, delta=0.05)
        assert prepeptide.lan_bridges == 5
        self.assertEqual("MSTKDFNLDLVSVSKKDSGASPR", prepeptide.leader)
        self.assertEqual("ITSISLCTPGCKTGALMGCNMKTATCHCSIHVSK", prepeptide.core)
        self.assertEqual('Class I', prepeptide.peptide_subclass)

        initial_json = result.to_json()
        regenerated = LanthiResults.from_json(initial_json, rec)
        assert list(result.motifs_by_locus) == ["nisB"]
        assert str(result.motifs_by_locus) == str(regenerated.motifs_by_locus)
        assert result.clusters == regenerated.clusters
        assert initial_json == regenerated.to_json()

    def test_nisin_complete(self):
        with TemporaryDirectory() as output_dir:
            args = ["run_antismash.py", "--minimal", "--enable-lanthipeptides", "--output-dir", output_dir]
            options = build_config(args, isolated=True, modules=antismash.get_all_modules())
            antismash.run_antismash(helpers.get_path_to_nisin_genbank(), options)

            # make sure the html_output section was tested
            with open(os.path.join(output_dir, "index.html")) as handle:
                content = handle.read()
                assert "nisA leader / core peptide" in content

    def test_epidermin(self):
        "Test lanthipeptide prediction for epidermin"
        filename = path.get_full_path(__file__, 'data', 'epidermin.gbk')
        rec = Record.from_biopython(seqio.read(filename), taxon="bacteria")
        assert not rec.get_cds_motifs()
        result = run_specific_analysis(rec)
        motifs = self.gather_all_motifs(result)
        assert len(motifs) == 1
        assert not rec.get_cds_motifs()
        result.add_to_record(rec)
        assert len(rec.get_cds_motifs()) == 1
        prepeptide = motifs[0]
        self.assertAlmostEqual(2164, prepeptide.monoisotopic_mass, delta=0.5)
        self.assertAlmostEqual(2165.6, prepeptide.molecular_weight, delta=0.5)
        self.assertEqual(3, prepeptide.lan_bridges)
        self.assertEqual("MEAVKEKNDLFNLDVKVNAKESNDSGAEPR", prepeptide.leader)
        self.assertEqual("IASKFICTPGCAKTGSFNSYCC", prepeptide.core)
        self.assertEqual('Class I', prepeptide.peptide_subclass)
        self.assertEqual(['AviCys'], prepeptide.get_modifications())

    def test_microbisporicin(self):
        "Test lanthipeptide prediction for microbisporicin"
        filename = path.get_full_path(__file__, 'data', 'microbisporicin.gbk')
        rec = Record.from_biopython(seqio.read(filename), taxon="bacteria")
        assert not rec.get_cds_motifs()
        result = run_specific_analysis(rec)
        motifs = self.gather_all_motifs(result)
        assert len(motifs) == 1
        assert not rec.get_cds_motifs()
        result.add_to_record(rec)
        assert len(rec.get_cds_motifs()) == 1

        prepeptide = motifs[0]
        # NOTE: this is not the correct weight for microbisporicin
        # there are some additional modifications we do not predict yet
        self.assertAlmostEqual(2212.9, prepeptide.monoisotopic_mass, delta=0.5)
        self.assertAlmostEqual(2214.5, prepeptide.molecular_weight, delta=0.5)
        self.assertEqual(4, prepeptide.lan_bridges)
        self.assertEqual("MPADILETRTSETEDLLDLDLSIGVEEITAGPA", prepeptide.leader)
        self.assertEqual("VTSWSLCTPGCTSPGGGSNCSFCC", prepeptide.core)
        self.assertEqual('Class I', prepeptide.peptide_subclass)
        self.assertEqual(['AviCys', 'Cl', 'OH'], prepeptide.get_modifications())

    def test_epicidin(self):
        "Test lanthipeptide prediction for epicidin 280"
        filename = path.get_full_path(__file__, 'data', 'epicidin_280.gbk')
        rec = Record.from_biopython(seqio.read(filename), taxon="bacteria")
        assert len(rec.get_cds_motifs()) == 1
        result = run_specific_analysis(rec)
        motifs = self.gather_all_motifs(result)
        assert len(motifs) == 1
        assert len(rec.get_cds_motifs()) == 1
        result.add_to_record(rec)
        assert len(rec.get_cds_motifs()) == 2

        prepeptide = motifs[0]
        self.assertAlmostEqual(3115.7, prepeptide.monoisotopic_mass, delta=0.5)
        self.assertAlmostEqual(3117.7, prepeptide.molecular_weight, delta=0.5)
        for expected, calculated in zip([3135.7, 3153.7, 3171.7],
                                        prepeptide.alternative_weights):
            self.assertAlmostEqual(expected, calculated, delta=0.05)
        self.assertEqual(3, prepeptide.lan_bridges)
        self.assertEqual("MENKKDLFDLEIKKDNMENNNELEAQ", prepeptide.leader)
        self.assertEqual("SLGPAIKATRQVCPKATRFVTVSCKKSDCQ", prepeptide.core)
        self.assertEqual('Class I', prepeptide.peptide_subclass)
        self.assertEqual(['Lac'], prepeptide.get_modifications())

    def test_labyrinthopeptin(self):
        "Test lanthipeptide prediction for labyrinthopeptin"
        filename = path.get_full_path(__file__, 'data', 'labyrinthopeptin.gbk')
        rec = Record.from_biopython(seqio.read(filename), taxon="bacteria")
        assert not rec.get_cds_motifs()
        result = run_specific_analysis(rec)
        motifs = self.gather_all_motifs(result)
        assert len(motifs) == 2
        assert not rec.get_cds_motifs()
        result.add_to_record(rec)
        assert len(rec.get_cds_motifs()) == 2

    def test_sco_cluster3(self):
        "Test lanthipeptide prediction for SCO cluster #3"
        filename = path.get_full_path(__file__, 'data', 'sco_cluster3.gbk')
        rec = Record.from_biopython(seqio.read(filename), taxon="bacteria")
        assert not rec.get_cds_motifs()
        result = run_specific_analysis(rec)
        motifs = self.gather_all_motifs(result)
        assert len(motifs) == 1
        assert not rec.get_cds_motifs()
        result.add_to_record(rec)
        assert len(rec.get_cds_motifs()) == 1
        self.assertEqual('Class I', motifs[0].peptide_subclass)

    def test_lactocin_s(self):
        """Test lanthipeptide prediction for lactocin S"""
        filename = path.get_full_path(__file__, 'data', 'lactocin_s.gbk')
        rec = Record.from_biopython(seqio.read(filename), taxon="bacteria")
        assert not rec.get_cds_motifs()
        result = run_specific_analysis(rec)
        assert len(result.clusters) == 1
        assert result.clusters[1] == set(["lasM"])
        assert len(result.motifs_by_locus["lasM"]) == 1
        motifs = result.motifs_by_locus["lasM"]
        assert len(motifs) == 1
        assert not rec.get_cds_motifs()
        result.add_to_record(rec)
        assert len(rec.get_cds_motifs()) == 1
        self.assertEqual('Class II', motifs[0].peptide_subclass)

    def test_multiple_biosynthetic_enzymes(self):
        # TODO: find/create an input with both class II and class III lanthipeptides
        # this was the case in CP013129.1, in a nrps-lanthipeptide hybrid, but
        # the hybrid was only created due to a bug in cluster formation
        pass

class IntegrationLanthipeptidesWithoutFimo(IntegrationLanthipeptides):
    def setUp(self):
        self.options = build_config(["--minimal", "--enable-lanthipeptides"],
                                    isolated=True, modules=antismash.get_all_modules())
        self.set_fimo_enabled(False)
        assert lanthi_config.get_config().fimo_present is False
