#!/usr/bin/env python3
"""kur.py doğrulama testleri (ağsız). Çalıştırma: python3 -I betik/kur_test.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kur  # noqa: E402

TEMEL = {b: 2.0 for b in kur.BIRIMLER}
TEMEL.update(USD=1, SAR=3.75, TRY=40.0)


class Suz(unittest.TestCase):
    def test_gecerli(self):
        k = kur.suz(dict(TEMEL))
        self.assertEqual(k['SAR'], 3.75)
        self.assertEqual(set(k), set(kur.BIRIMLER))

    def test_fazla_birim_alinmaz(self):
        self.assertNotIn('BTC', kur.suz(dict(TEMEL, BTC=0.00001)))

    def test_sar_aralik_disi(self):
        with self.assertRaises(kur.KurHatasi):
            kur.suz(dict(TEMEL, SAR=3.9))

    def test_zorunlu_eksik(self):
        h = dict(TEMEL)
        del h['TRY']
        with self.assertRaises(kur.KurHatasi):
            kur.suz(h)

    def test_sifir_negatif_metin(self):
        for v in (0, -1, '3', None, float('nan')):
            with self.assertRaises(kur.KurHatasi):
                kur.suz(dict(TEMEL, EUR=v))

    def test_sapma(self):
        with self.assertRaises(kur.KurHatasi):
            kur.suz(dict(TEMEL, TRY=70.0), {'TRY': 40.0})
        self.assertEqual(kur.suz(dict(TEMEL, TRY=45.0), {'TRY': 40.0})['TRY'], 45.0)

    def test_fawaz_bicimi(self):
        tarih, ham, kaynak, _ = kur.fawaz({'date': '2026-10-25', 'usd': {'sar': 3.75, 'try': 40}})
        self.assertEqual((tarih, ham['SAR'], ham['TRY']), ('2026-10-25', 3.75, 40))
        with self.assertRaises(kur.KurHatasi):
            kur.fawaz({'usd': []})

    def test_er_api_bicimi(self):
        tarih, ham, _, _ = kur.er_api({'result': 'success', 'base_code': 'USD', 'time_last_update_unix': 1792972951, 'rates': {'SAR': 3.75}})
        self.assertEqual((tarih, ham['SAR']), ('2026-10-26', 3.75))
        with self.assertRaises(kur.KurHatasi):
            kur.er_api({'result': 'error'})


if __name__ == '__main__':
    unittest.main()
