#!/usr/bin/env python3
"""Türkiye'deki camiler ve mescitler: OpenStreetMap (Geofabrik Türkiye çıkarımı) → 0,5°'lik kare dosyaları.

Uygulama yakın camileri anlık Overpass sorgusuyla arıyordu; herkese açık Overpass sunucuları sık sık yanıtsız
kaldığı için liste ya hiç gelmiyor ya da çok geç geliyordu. Burada ayda bir bütün Türkiye çekilip konuma göre
karelere bölünür; cihaz yalnız çevresindeki kareleri indirir (konumu hiçbir yere gönderilmez), ayıklamayı
(cami mi mescit mi, dernek mi mezarlık mı) uygulamanın kendi kodu yapar.

Girdi: `osmium export -f geojsonseq --add-unique-id=type_id` çıktısı (betik/camiler.sh hazırlar).
Çıktı:
  camiler/<enlem>_<boylam>.json  {"v":1,"o":[[kimlik, enlem, boylam, {etiketler}], ...]}
      kare adı güneybatı köşesidir (ör. 37.0_35.0 = 37.0-37.5 K, 35.0-35.5 D)
  camiler/dizin.json             {"v":1,"tarih":"YYYY-MM-DD","kare":0.5,"kareler":["37.0_35.0", ...],"toplam":N}

Veri © OpenStreetMap katkıcıları, ODbL.

Çalıştırma: python3 -I betik/camiler.py <girdi.geojsonseq> [çıktı klasörü]
"""
import datetime
import json
import math
import os
import sys

KARE = 0.5
SURUM = 1
# Uygulamanın ayıklaması (src/lib/camiler.ts → uygunMu, camileriAyikla) yalnız bunlara bakar
ETIKETLER = (
    'religion', 'amenity', 'building', 'name', 'name:tr', 'place_of_worship',
    'landuse', 'shop', 'historic', 'craft', 'healthcare', 'tourism',
)
# Türkiye'nin kabaca sınırları; Geofabrik çıkarımının kenarından taşan komşu ülke kayıtlarını da kapsar
SINIR = (35.5, 42.5, 25.5, 45.0)  # güney, kuzey, batı, doğu
# Bunun altına düşerse iş durur, eski dosyalar kalır (çıkarım bozuk ya da yarım inmiş olabilir)
EN_AZ = 80000  # 2026-10-31 ilk çekim: 113.735


class CamiHatasi(Exception):
    pass


def ilgili_mi(etiket):
    return etiket.get('religion') == 'muslim' or etiket.get('building') == 'mosque'


def noktalar(geometri):
    """Geometrinin bütün köşeleri (iç halkalar hariç)."""
    tur = geometri.get('type')
    k = geometri.get('coordinates')
    if tur == 'Point':
        return [k]
    if tur in ('LineString', 'MultiPoint'):
        return k
    if tur == 'Polygon':
        return k[0] if k else []
    if tur == 'MultiPolygon':
        return [n for p in k if p for n in p[0]]
    if tur == 'MultiLineString':
        return [n for c in k for n in c]
    return []


def merkez(geometri):
    """Köşelerin ortalaması; bina ölçeğinde (onlarca metre) gerçek ağırlık merkezinden farkı önemsiz."""
    n = noktalar(geometri)
    # Kapalı halkanın son noktası ilkinin tekrarıdır
    if len(n) > 1 and n[0] == n[-1]:
        n = n[:-1]
    if not n:
        return None
    boylam = sum(p[0] for p in n) / len(n)
    enlem = sum(p[1] for p in n) / len(n)
    return enlem, boylam


def kare_adi(enlem, boylam):
    return f'{math.floor(enlem / KARE) * KARE:.1f}_{math.floor(boylam / KARE) * KARE:.1f}'


def osm_kimligi(kimlik):
    """osmium kapalı yolu/ilişkiyi alan (a<2·id>, ilişkiyse +1) olarak verir; uygulama n/w/r bekler."""
    if kimlik[:1] == 'a' and kimlik[1:].isdigit():
        n = int(kimlik[1:])
        return f"{'r' if n % 2 else 'w'}{n // 2}"
    return kimlik


def ayikla(satirlar):
    """GeoJSON satırları → {kare adı: [[kimlik, enlem, boylam, etiketler], ...]}"""
    kareler = {}
    gorulen = set()
    for satir in satirlar:
        satir = satir.strip().lstrip('\x1e')
        if not satir:
            continue
        f = json.loads(satir)
        etiket = f.get('properties') or {}
        if not ilgili_mi(etiket):
            continue
        kimlik = osm_kimligi(str(f.get('id') or etiket.get('@id') or ''))
        # type_id kimliği: n123 / w123 / r123 (alanlar a… gelir, çevrilir)
        if not kimlik or kimlik in gorulen:
            continue
        m = merkez(f.get('geometry') or {})
        if not m:
            continue
        enlem, boylam = m
        if not (SINIR[0] <= enlem <= SINIR[1] and SINIR[2] <= boylam <= SINIR[3]):
            continue
        gorulen.add(kimlik)
        kucuk = {a: str(etiket[a]) for a in ETIKETLER if a in etiket and a != 'religion'}
        kareler.setdefault(kare_adi(enlem, boylam), []).append([kimlik, round(enlem, 5), round(boylam, 5), kucuk])
    for liste in kareler.values():
        liste.sort(key=lambda o: o[0])
    return kareler


def yaz(kareler, klasor, tarih=None):
    toplam = sum(len(v) for v in kareler.values())
    if toplam < EN_AZ:
        raise CamiHatasi(f'yalnız {toplam} kayıt (en az {EN_AZ} bekleniyordu)')
    os.makedirs(klasor, exist_ok=True)
    yeni = set()
    for ad, liste in kareler.items():
        yeni.add(f'{ad}.json')
        with open(os.path.join(klasor, f'{ad}.json'), 'w', encoding='utf-8') as d:
            json.dump({'v': SURUM, 'o': liste}, d, ensure_ascii=False, separators=(',', ':'))
    # Artık boş kalan eski kareler silinir
    for eski in os.listdir(klasor):
        if eski.endswith('.json') and eski != 'dizin.json' and eski not in yeni:
            os.remove(os.path.join(klasor, eski))
    dizin = {
        'v': SURUM,
        'tarih': tarih or datetime.date.today().isoformat(),
        'kare': KARE,
        'kareler': sorted(kareler),
        'toplam': toplam,
        'kaynak': '© OpenStreetMap katkıcıları, ODbL',
    }
    with open(os.path.join(klasor, 'dizin.json'), 'w', encoding='utf-8') as d:
        json.dump(dizin, d, ensure_ascii=False, separators=(',', ':'))
    return dizin


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    klasor = sys.argv[2] if len(sys.argv) > 2 else 'camiler'
    with open(sys.argv[1], encoding='utf-8') as g:
        kareler = ayikla(g)
    dizin = yaz(kareler, klasor)
    print(f"{dizin['toplam']} kayıt, {len(dizin['kareler'])} kare → {klasor}/")


if __name__ == '__main__':
    main()
