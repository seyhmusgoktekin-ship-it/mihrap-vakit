#!/usr/bin/env python3
"""
Mihrap'ın döviz dönüştürücüsü (Hac ve Umre Rehberi) için USD tabanlı günlük kurlar.
Yalnız standart kütüphane; anahtar/şifre gerekmez.

Kaynaklar (sırayla):
  1. ExchangeRate-API açık uç noktası  https://open.er-api.com/v6/latest/USD
     (kullanım koşulu: atıf. "Rates By Exchange Rate API" + https://www.exchangerate-api.com;
     uygulama `kaynak` ve `kaynakAdres` alanlarını ekranda gösterir.)
  2. fawazahmed0/exchange-api (CC0)    https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json
     (yedek adres: https://latest.currency-api.pages.dev/v1/currencies/usd.json)

Çıktı: kur/usd.json
  {"taban": "USD", "tarih": "YYYY-MM-DD", "guncellendi": ISO, "kaynak": "...", "kaynakAdres": "...", "kurlar": {"SAR": 3.75, ...}}

Doğrulama: SAR 3,70–3,80 dışında, zorunlu birim eksik, sıfır/negatif/sayı olmayan değer ya da önceki
dosyaya göre %50'den fazla sapma varsa kaynak reddedilir. İki kaynak da reddedilirse eski dosya
korunur ve betik 1 ile çıkar (görev başarısız görünür).

Kullanım: python3 -I betik/kur.py
"""
import datetime
import json
import os
import sys
import urllib.request

DIZIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIKTI = os.path.join(DIZIN, 'kur', 'usd.json')

# Uygulamanın dillerinin, hac/umre yolcusu gönderen başlıca ülkelerin ve başlıca para birimleri.
BIRIMLER = [
    'USD', 'EUR', 'GBP', 'SAR', 'TRY', 'AED', 'QAR', 'KWD', 'BHD', 'OMR', 'JOD', 'EGP', 'IQD', 'LBP',
    'MAD', 'DZD', 'TND', 'LYD', 'SDG', 'PKR', 'INR', 'BDT', 'LKR', 'MVR', 'AFN', 'IRR', 'IDR', 'MYR',
    'SGD', 'BND', 'THB', 'PHP', 'CNY', 'HKD', 'JPY', 'KRW', 'RUB', 'KZT', 'UZS', 'KGS', 'TJS', 'TMT',
    'AZN', 'GEL', 'NGN', 'XOF', 'GHS', 'KES', 'TZS', 'ZAR', 'SEK', 'NOK', 'DKK', 'CHF', 'PLN', 'BAM',
    'ALL', 'MKD', 'RSD', 'CAD', 'AUD', 'NZD', 'BRL', 'MXN',
]
ZORUNLU = {'USD', 'EUR', 'GBP', 'SAR', 'TRY'}
SAR_ARALIK = (3.70, 3.80)
AZAMI_SAPMA = 0.5
ZAMAN_ASIMI = 30

ER_API = 'https://open.er-api.com/v6/latest/USD'
FAWAZ = [
    'https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json',
    'https://latest.currency-api.pages.dev/v1/currencies/usd.json',
]


class KurHatasi(Exception):
    pass


def getir(adres):
    q = urllib.request.Request(adres, headers={'Accept': 'application/json', 'User-Agent': 'mihrap-vakit'})
    with urllib.request.urlopen(q, timeout=ZAMAN_ASIMI) as r:
        return json.load(r)


def er_api(y):
    """{"result":"success","base_code":"USD","time_last_update_unix":…,"rates":{"SAR":3.75,…}}"""
    if y.get('result') != 'success' or y.get('base_code') != 'USD' or not isinstance(y.get('rates'), dict):
        raise KurHatasi('er-api: beklenmeyen yanıt')
    tarih = datetime.datetime.fromtimestamp(int(y['time_last_update_unix']), datetime.timezone.utc).date().isoformat()
    return tarih, y['rates'], 'ExchangeRate-API', 'https://www.exchangerate-api.com'


def fawaz(y):
    """{"date":"YYYY-MM-DD","usd":{"sar":3.75,…}} (küçük harf kodlar)"""
    if not isinstance(y.get('usd'), dict) or not isinstance(y.get('date'), str):
        raise KurHatasi('fawazahmed0: beklenmeyen yanıt')
    return y['date'], {k.upper(): v for k, v in y['usd'].items()}, 'fawazahmed0/exchange-api', 'https://github.com/fawazahmed0/exchange-api'


def sayi_mi(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v not in (float('inf'), float('-inf'))


def suz(ham, onceki=None):
    """Gerekli birimleri seçer ve doğrular. `onceki`: eski dosyanın kurları (sapma denetimi)."""
    kurlar = {}
    for b in BIRIMLER:
        v = ham.get(b)
        if v is None:
            if b in ZORUNLU:
                raise KurHatasi(f'{b} eksik')
            continue
        if not sayi_mi(v) or v <= 0:
            raise KurHatasi(f'{b} geçersiz: {v!r}')
        kurlar[b] = float(f'{v:.6g}') if v < 1000 else round(v, 2)
    if abs(kurlar['USD'] - 1) > 1e-9:
        raise KurHatasi(f"USD 1 değil: {kurlar['USD']}")
    if not SAR_ARALIK[0] <= kurlar['SAR'] <= SAR_ARALIK[1]:
        raise KurHatasi(f"SAR {kurlar['SAR']} ({SAR_ARALIK[0]}–{SAR_ARALIK[1]} dışında)")
    if len(kurlar) < len(BIRIMLER) * 0.8:
        raise KurHatasi(f'çok az birim: {len(kurlar)}')
    for b, v in (onceki or {}).items():
        if b in kurlar and sayi_mi(v) and v > 0 and abs(kurlar[b] / v - 1) > AZAMI_SAPMA:
            raise KurHatasi(f'{b} önceki güne göre çok saptı: {v} → {kurlar[b]}')
    return kurlar


def tarih_mi(s):
    try:
        datetime.date.fromisoformat(s)
        return True
    except (TypeError, ValueError):
        return False


def onceki_kurlar():
    try:
        with open(CIKTI, encoding='utf-8') as f:
            return json.load(f).get('kurlar') or {}
    except (OSError, ValueError):
        return {}


def kaynaklar():
    yield ER_API, er_api
    for a in FAWAZ:
        yield a, fawaz


def main():
    onceki = onceki_kurlar()
    hatalar = []
    for adres, coz in kaynaklar():
        try:
            tarih, ham, kaynak, kaynak_adres = coz(getir(adres))
            if not tarih_mi(tarih):
                raise KurHatasi(f'tarih geçersiz: {tarih!r}')
            kurlar = suz(ham, onceki)
        except Exception as e:  # ağ, JSON ya da doğrulama: sonraki kaynağa geç
            hatalar.append(f'{adres}: {e}')
            print('Reddedildi:', hatalar[-1], file=sys.stderr)
            continue
        veri = {
            'taban': 'USD',
            'tarih': tarih,
            'guncellendi': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
            'kaynak': kaynak,
            'kaynakAdres': kaynak_adres,
            'kurlar': kurlar,
        }
        os.makedirs(os.path.dirname(CIKTI), exist_ok=True)
        gecici = CIKTI + '.tmp'
        with open(gecici, 'w', encoding='utf-8') as f:
            json.dump(veri, f, ensure_ascii=False, separators=(',', ':'))
            f.write('\n')
        os.replace(gecici, CIKTI)
        print(f'{kaynak} {tarih}: {len(kurlar)} birim, 1 USD = {kurlar["SAR"]} SAR, {kurlar["TRY"]} TRY')
        return 0
    print('Hiçbir kaynak kullanılamadı; eski dosya korundu.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
