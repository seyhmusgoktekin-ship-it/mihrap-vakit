#!/usr/bin/env python3
"""hutbe.py testleri (ağsız). Çalıştırma: python3 -I betik/hutbe_test.py"""
import datetime
import os
import sys
import unittest

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import hutbe  # noqa: E402

with open(os.path.join(BURASI, 'ornek', 'hutbe.doc'), 'rb') as f:
    ORNEK = f.read()  # 30.10.2026, "Birlik ve Beraberlik"

SATIR = {'Tarih': '30.10.2026', 'Title': 'Birlik ve  Beraberlik ', 'Word': '/Documents/x.doc', 'PDF': '/Documents/Birlik ve Beraberlik.pdf'}


class Word(unittest.TestCase):
    def test_metin_ve_dipnotlar(self):
        h = hutbe.hutbe_olustur(SATIR, ORNEK)
        self.assertEqual(h['baslik'], 'Birlik ve Beraberlik')
        self.assertEqual(h['tarih'], '2026-10-30')
        self.assertEqual(h['dipnotlar'], ['Ebû Dâvûd, Büyû’, (İcâre), 76.', 'Saff, 61/4.', 'Tirmizî, Fiten, 7.'])
        self.assertEqual(h['bolumler'][0], {'tur': 'hitap', 'metin': 'Muhterem Müslümanlar!'})
        self.assertIn({'tur': 'hitap', 'metin': 'Kıymetli Aileler! Sevgili Gençler!'}, h['bolumler'])
        metin = '\n'.join(b['metin'] for b in h['bolumler'])
        for n in (1, 2, 3):
            self.assertIn(f'[{n}]', metin)
        self.assertNotIn('Tarih:', metin)
        self.assertNotIn('BİRLİK VE BERABERLİK', metin)
        self.assertNotIn(hutbe.KAYNAK, metin)
        self.assertTrue(h['adres'].startswith('https://dinhizmetleri.diyanet.gov.tr/Documents/Birlik%20ve'))

    def test_word_degil(self):
        with self.assertRaises(hutbe.HutbeHatasi):
            hutbe.doc_metni(b'%PDF-1.7 ...')


class Tarih(unittest.TestCase):
    def test_bu_cuma(self):
        self.assertTrue(hutbe.bu_cuma_mi('30.10.2026', datetime.date(2026, 10, 29)))
        self.assertTrue(hutbe.bu_cuma_mi('30.10.2026', datetime.date(2026, 10, 30)))

    def test_gecmis_ya_da_cuma_degil(self):
        self.assertFalse(hutbe.bu_cuma_mi('30.10.2026', datetime.date(2026, 10, 31)))
        self.assertFalse(hutbe.bu_cuma_mi('23.10.2026', datetime.date(2026, 10, 29)))
        self.assertFalse(hutbe.bu_cuma_mi('29.10.2026', datetime.date(2026, 10, 29)))
        self.assertFalse(hutbe.bu_cuma_mi('', datetime.date(2026, 10, 29)))


class Dogrula(unittest.TestCase):
    def setUp(self):
        self.h = hutbe.hutbe_olustur(SATIR, ORNEK)

    def test_bos_baslik(self):
        with self.assertRaises(hutbe.HutbeHatasi):
            hutbe.dogrula(dict(self.h, baslik=' '))

    def test_az_paragraf(self):
        with self.assertRaises(hutbe.HutbeHatasi):
            hutbe.dogrula(dict(self.h, bolumler=[b for b in self.h['bolumler'] if b['tur'] == 'paragraf'][:2]))

    def test_kisa_metin(self):
        with self.assertRaises(hutbe.HutbeHatasi):
            hutbe.dogrula(dict(self.h, bolumler=[{'tur': 'paragraf', 'metin': 'kısa'}] * 4))

    def test_dipnot_eksik(self):
        with self.assertRaises(hutbe.HutbeHatasi):
            hutbe.dogrula(dict(self.h, dipnotlar=[]))


class Liste(unittest.TestCase):
    def test_ilk_satir(self):
        html = '<script>var x=1; ListData = { "Row" : [{"Tarih": "30.10.2026", "Title": "A"}, {"Tarih": "23.10.2026"}] };\nvar y;</script>'
        self.assertEqual(hutbe.ilk_satir(html)['Title'], 'A')
        with self.assertRaises(hutbe.HutbeHatasi):
            hutbe.ilk_satir('<html></html>')

    def test_tablo(self):
        satir = ('<tr class="{s}ms-itmhover" iid="2,1,0"><td class="ms-vb-itmcbx"></td><td class="ms-vb2"><nobr>{t}</nobr></td>'
                 '<td class="ms-vb2">{b}</td><td class="ms-vb2"><a href="/Documents/{b}.pdf">{b}</a></td>'
                 '<td class="ms-vb2"><a href="/Documents/{b}.doc">{b}</a></td><td class="ms-vb2"></td></tr>')
        html = 'ListData = null;' + satir.format(s='', t='23.10.2026', b='Aile') + satir.format(s='ms-alternating ', t='30.10.2026', b='Birlik &amp; Beraberlik')
        r = hutbe.ilk_satir(html)
        self.assertEqual((r['Tarih'], r['Title'], r['Word']), ('30.10.2026', 'Birlik & Beraberlik', '/Documents/Birlik & Beraberlik.doc'))


if __name__ == '__main__':
    unittest.main()
