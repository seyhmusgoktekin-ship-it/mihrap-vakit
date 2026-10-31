#!/usr/bin/env python3
"""camiler.py doğrulama testleri (ağsız). Çalıştırma: python3 -I betik/camiler_test.py"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camiler  # noqa: E402


def satir(kimlik, geometri, **etiket):
    return '\x1e' + json.dumps({'type': 'Feature', 'id': kimlik, 'geometry': geometri, 'properties': etiket})


NOKTA = {'type': 'Point', 'coordinates': [35.3201, 37.0003]}
BINA = {
    'type': 'Polygon',
    'coordinates': [[[35.3, 37.0], [35.302, 37.0], [35.302, 37.002], [35.3, 37.002], [35.3, 37.0]]],
}


class Ayikla(unittest.TestCase):
    def test_cami_noktasi_ve_bina(self):
        k = camiler.ayikla([
            satir('n1', NOKTA, amenity='place_of_worship', religion='muslim', name='Alidede Camii', wheelchair='yes'),
            satir('w2', BINA, building='mosque'),
        ])
        self.assertEqual(list(k), ['37.0_35.0'])
        n1, w2 = k['37.0_35.0']
        self.assertEqual(n1, ['n1', 37.0003, 35.3201, {'amenity': 'place_of_worship', 'name': 'Alidede Camii'}])
        # Kapalı halkanın tekrar eden son noktası ortalamaya girmez
        self.assertEqual(w2[1:3], [37.001, 35.301])
        self.assertEqual(w2[3], {'building': 'mosque'})

    def test_ilgisiz_ve_kopya_elenir(self):
        k = camiler.ayikla([
            satir('n3', NOKTA, amenity='place_of_worship', religion='christian', name='Kilise'),
            satir('n4', NOKTA, entrance='main'),
            satir('n5', NOKTA, religion='muslim', landuse='cemetery'),
            satir('n5', NOKTA, religion='muslim', landuse='cemetery'),
            '',
        ])
        # Mezarlık burada elenmez (uygulama eler); yalnız ilgisizler ve kopya
        self.assertEqual([o[0] for o in k['37.0_35.0']], ['n5'])

    def test_sinir_disi(self):
        k = camiler.ayikla([satir('n6', {'type': 'Point', 'coordinates': [44.5, 33.3]}, religion='muslim')])
        self.assertEqual(k, {})

    def test_alan_kimligi_yol_ya_da_iliski(self):
        self.assertEqual(camiler.osm_kimligi('a2042'), 'w1021')
        self.assertEqual(camiler.osm_kimligi('a2043'), 'r1021')
        self.assertEqual(camiler.osm_kimligi('n7'), 'n7')
        k = camiler.ayikla([satir('a20', BINA, building='mosque'), satir('w10', BINA, building='mosque')])
        self.assertEqual([o[0] for o in k['37.0_35.0']], ['w10'])

    def test_kare_adi_eksi_ve_sinir(self):
        self.assertEqual(camiler.kare_adi(37.49, 35.5), '37.0_35.5')
        self.assertEqual(camiler.kare_adi(41.0, 28.99), '41.0_28.5')
        self.assertEqual(camiler.kare_adi(-0.1, -0.1), '-0.5_-0.5')

    def test_cokgen_cok_parcali(self):
        g = {'type': 'MultiPolygon', 'coordinates': [BINA['coordinates']]}
        enlem, boylam = camiler.merkez(g)
        self.assertAlmostEqual(enlem, 37.001)
        self.assertAlmostEqual(boylam, 35.301)


class Yaz(unittest.TestCase):
    def test_az_kayitta_durur_eskiye_dokunmaz(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'eski.json'), 'w').close()
            with self.assertRaises(camiler.CamiHatasi):
                camiler.yaz({'37.0_35.0': [['n1', 37, 35, {}]]}, d)
            self.assertTrue(os.path.exists(os.path.join(d, 'eski.json')))

    def test_dizin_ve_eski_kare_silinir(self):
        eski = camiler.EN_AZ
        camiler.EN_AZ = 1
        try:
            with tempfile.TemporaryDirectory() as d:
                open(os.path.join(d, '10.0_10.0.json'), 'w').close()
                dizin = camiler.yaz({'37.0_35.0': [['n1', 37.1, 35.2, {'building': 'mosque'}]]}, d, '2026-11-01')
                self.assertEqual(sorted(os.listdir(d)), ['37.0_35.0.json', 'dizin.json'])
                self.assertEqual(dizin['kareler'], ['37.0_35.0'])
                self.assertEqual(dizin['tarih'], '2026-11-01')
                with open(os.path.join(d, '37.0_35.0.json'), encoding='utf-8') as g:
                    self.assertEqual(json.load(g), {'v': 1, 'o': [['n1', 37.1, 35.2, {'building': 'mosque'}]]})
        finally:
            camiler.EN_AZ = eski


if __name__ == '__main__':
    unittest.main()
