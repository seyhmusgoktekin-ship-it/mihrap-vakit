#!/usr/bin/env python3
"""
Diyanet Awqat Salah API'sinden Türkiye ilçelerinin vakitlerini çekip
Mihrap uygulamasının okuyacağı durağan dosyalara yazar (GitHub Pages).

Kullanıcı adı/şifre yalnız ortam değişkeninden gelir (DIYANET_KULLANICI,
DIYANET_SIFRE: GitHub secret). Hiçbir yere yazılmaz, günlüğe basılmaz.

Kota: her servis, her parametre için ayrı ayrı 10 istek (ilk 15 gün 100).
Bu yüzden her ilçe için haftada bir tek `Monthly` isteği atılır.

Kipler:
  kesif  yer listelerini ham/ altına yazar, tek ilçenin aylık yanıtını örnek alır
  vakit  eslesme.json'daki her ilçe için vakit/<ezanvakti-id>.json yazar
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

KOK = 'https://awqatsalah.diyanet.gov.tr'
DIZIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Istemci:
    def __init__(self):
        self.kullanici = os.environ['DIYANET_KULLANICI']
        self.sifre = os.environ['DIYANET_SIFRE']
        self.token = None
        self.giris()

    def _istek(self, yol, govde=None, token=True):
        basliklar = {'Accept': 'application/json'}
        veri = None
        if govde is not None:
            veri = json.dumps(govde).encode()
            basliklar['Content-Type'] = 'application/json'
        if token:
            basliklar['Authorization'] = 'Bearer ' + self.token
        q = urllib.request.Request(KOK + yol, data=veri, headers=basliklar,
                                   method='POST' if veri else 'GET')
        with urllib.request.urlopen(q, timeout=60) as r:
            return json.load(r)

    def giris(self):
        y = self._istek('/Auth/Login', {'email': self.kullanici, 'password': self.sifre}, token=False)
        if not y.get('success'):
            sys.exit('Giriş başarısız: ' + str(y.get('message')))
        self.token = y['data']['accessToken']
        self.alindi = time.time()

    def getir(self, yol):
        # Token 45 dk geçerli; 40 dk'da bir yenile.
        if time.time() - self.alindi > 40 * 60:
            self.giris()
        for deneme in range(4):
            try:
                y = self._istek(yol)
                if not y.get('success', True):
                    raise RuntimeError(f'{yol}: {y.get("message")}')
                return y.get('data', y)
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    self.giris()
                elif e.code in (429, 500, 502, 503, 504) and deneme < 3:
                    time.sleep(10 * (deneme + 1))
                else:
                    govde = e.read()[:300].decode('utf-8', 'replace')
                    raise RuntimeError(f'{yol}: HTTP {e.code} {govde}') from None
        raise RuntimeError(f'{yol}: denemeler bitti')


def yaz(yol, veri, girinti=None):
    tam = os.path.join(DIZIN, yol)
    os.makedirs(os.path.dirname(tam), exist_ok=True)
    with open(tam, 'w', encoding='utf-8') as f:
        json.dump(veri, f, ensure_ascii=False, indent=girinti, separators=None if girinti else (',', ':'))


def kota(ist):
    try:
        print('Kota:', json.dumps(ist.getir('/api/Quota/My'), ensure_ascii=False)[:3000])
    except Exception as e:  # kota bilgisi olmasa da sürsün
        print('Kota okunamadı:', e)


def kesif(ist):
    kota(ist)
    iller = ist.getir('/api/Place/States/2')
    yaz('ham/awqat-iller.json', iller, 1)
    ilceler = {}
    for il in iller:
        ilceler[str(il['id'])] = ist.getir(f'/api/Place/Cities/{il["id"]}')
        time.sleep(0.3)
    yaz('ham/awqat-ilceler.json', ilceler, 1)
    ornek = os.environ.get('ORNEK_ILCE', '9541')
    yaz('ham/ornek-aylik.json', ist.getir(f'/api/PrayerTime/Monthly/{ornek}'), 1)
    print(len(iller), 'il,', sum(len(v) for v in ilceler.values()), 'ilçe')
    kota(ist)


def gun_satiri(s):
    """Awqat satırı → uygulamanın DiyanetGun biçimi (src/lib/vakit/diyanet.ts)."""
    g, a, y = s['gregorianDateShort'].split('.')
    return {
        'g': f'{y}-{a}-{g}',
        'v': [s['fajr'], s['sunrise'], s['dhuhr'], s['asr'], s['maghrib'], s['isha']],
        'z': s['greenwichMeanTimeZone'],
        'h': s['hijriDateShort'],
    }


def vakit(ist):
    eslesme = json.load(open(os.path.join(DIZIN, 'eslesme.json'), encoding='utf-8'))
    hatalar = []
    for eski, yeni in sorted(eslesme.items()):
        try:
            satirlar = [gun_satiri(s) for s in ist.getir(f'/api/PrayerTime/Monthly/{yeni}')]
            if not satirlar:
                raise RuntimeError('boş yanıt')
            yaz(f'vakit/{eski}.json', satirlar)
        except Exception as e:
            hatalar.append(f'{eski}→{yeni}: {e}')
        time.sleep(0.3)
    print(len(eslesme) - len(hatalar), 'ilçe yazıldı,', len(hatalar), 'hata')
    for h in hatalar[:30]:
        print('  ', h)
    kota(ist)
    # Yarıdan fazlası düştüyse işi başarısız say (yayına bozuk veri gitmesin).
    if len(hatalar) > len(eslesme) // 2:
        sys.exit(1)


if __name__ == '__main__':
    kip = sys.argv[1] if len(sys.argv) > 1 else 'vakit'
    {'kesif': kesif, 'vakit': vakit}[kip](Istemci())
