#!/usr/bin/env python3
"""Camiler ve mescitler: OpenStreetMap (Geofabrik kıta çıkarımları, bütün dünya) → 0,5°'lik kare dosyaları.

Uygulama yakın camileri anlık Overpass sorgusuyla arıyordu; herkese açık Overpass sunucuları sık sık yanıtsız
kaldığı için liste ya hiç gelmiyor ya da çok geç geliyordu (Endonezya'da 2026-11: uzun bekleme, sonra boş liste).
Burada ayda bir bütün dünyanın kayıtları çekilip konuma göre
karelere bölünür; cihaz yalnız çevresindeki kareleri indirir (konumu hiçbir yere gönderilmez), ayıklamayı
(cami mi mescit mi, dernek mi mezarlık mı) uygulamanın kendi kodu yapar.

Girdi: `osmium export -f geojsonseq --add-unique-id=type_id` çıktısı; kıtalarınki art arda eklenmiş tek dosya
(`.github/workflows/camiler.yml` hazırlar; kıtaların örtüştüğü yerlerdeki kopyalar elenir).
Çıktı iki yere:
  Dünya (v2, R2'ye yüklenir, https://video.seamus.tr/camiler/; uygulama 2.0.1 ve sonrası):
    <tarih>_<enlem>_<boylam>.json  {"v":2,"o":[[kimlik, enlem, boylam, {etiketler}], ...]}
    dizin.json                     {"v":2,"kapsam":"dunya","tarih":"YYYY-MM-DD","kare":0.5,"kareler":[...],"toplam":N}
      Kare adı tarihi taşır: kareler değişmez (CDN'de kalıcı önbellek), dizin her ay yeni tarihi gösterir.
      Dizinde olmayan kare o bölgede hiç kayıt olmadığı demektir (uygulama Overpass'a sormaz).
  Depo (v1, yalnız Türkiye ve Endonezya, GitHub Pages; eski uygulama sürümleri buradan okur):
    camiler/<enlem>_<boylam>.json, camiler/dizin.json  (eski biçim, değişmedi)
  Kare adı güneybatı köşesidir (ör. 37.0_35.0 = 37.0-37.5 K, 35.0-35.5 D).

Veri © OpenStreetMap katkıcıları, ODbL.

Çalıştırma: python3 -I betik/camiler.py <girdi.geojsonseq> <depo klasörü> [dünya klasörü]
"""
import datetime
import json
import math
import os
import sys

KARE = 0.5
SURUM = 1
DUNYA_SURUM = 2
# Uygulamanın ayıklaması (src/lib/camiler.ts → uygunMu, camileriAyikla) yalnız bunlara bakar
ETIKETLER = (
    'religion', 'amenity', 'building', 'name', 'name:tr', 'place_of_worship',
    'landuse', 'shop', 'historic', 'craft', 'healthcare', 'tourism',
)
# Bölgelerin kabaca sınırları (güney, kuzey, batı, doğu) ve en az kayıt sayısı. Sınır, Geofabrik çıkarımının kenarından
# taşan komşu ülke kayıtlarını da kapsar. Bir bölge bu sayının altına düşerse iş durur, eski dosyalar kalır
# (çıkarım bozuk ya da yarım inmiş olabilir). Yeni bölge: buraya bir satır + iş akışında bir çıkarım.
BOLGELER = {
    'tr': ((35.5, 42.5, 25.5, 45.0), 40000),  # 2026-10-31 çekim: 57.828
    'id': ((-11.5, 6.5, 94.5, 141.5), 20000),
}
# Dünyanın tamamı bunun altına düşerse (bir kıta yarım inmiş olabilir) iş durur, eski dosyalar kalır
DUNYA_EN_AZ = 200000


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


def bolge(enlem, boylam):
    for ad, ((g, k, b, d), _) in BOLGELER.items():
        if g <= enlem <= k and b <= boylam <= d:
            return ad
    return None


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
        gorulen.add(kimlik)
        kucuk = {a: str(etiket[a]) for a in ETIKETLER if a in etiket and a != 'religion'}
        kareler.setdefault(kare_adi(enlem, boylam), []).append([kimlik, round(enlem, 5), round(boylam, 5), kucuk])
    for liste in kareler.values():
        liste.sort(key=lambda o: o[0])
    return kareler


def sayilar(kareler):
    sayi = {ad: 0 for ad in BOLGELER}
    for liste in kareler.values():
        for o in liste:
            ad = bolge(o[1], o[2])
            if ad:
                sayi[ad] += 1
    return sayi


def denetle(kareler, dunya=False):
    """Bölgelerden biri (dünya çıktısında dünyanın tamamı da) en az sayının altındaysa durur."""
    sayi = sayilar(kareler)
    for ad, (_, en_az) in BOLGELER.items():
        if sayi[ad] < en_az:
            raise CamiHatasi(f'{ad}: yalnız {sayi[ad]} kayıt (en az {en_az} bekleniyordu)')
    toplam = sum(len(v) for v in kareler.values())
    if dunya and toplam < DUNYA_EN_AZ:
        raise CamiHatasi(f'dünya: yalnız {toplam} kayıt (en az {DUNYA_EN_AZ} bekleniyordu)')
    return sayi, toplam


def bolgelere_sinirla(kareler):
    """Eski uygulama sürümleri için yalnız BOLGELER içindeki kayıtlar."""
    sonuc = {}
    for ad, liste in kareler.items():
        icinde = [o for o in liste if bolge(o[1], o[2])]
        if icinde:
            sonuc[ad] = icinde
    return sonuc


def _dosya(yol, veri):
    with open(yol, 'w', encoding='utf-8') as d:
        json.dump(veri, d, ensure_ascii=False, separators=(',', ':'))


def yaz(kareler, klasor, tarih=None):
    """Depo çıktısı (v1, yalnız BOLGELER): eski biçim, eski uygulama sürümleri okur."""
    kareler = bolgelere_sinirla(kareler)
    sayi, toplam = denetle(kareler)
    os.makedirs(klasor, exist_ok=True)
    yeni = set()
    for ad, liste in kareler.items():
        yeni.add(f'{ad}.json')
        _dosya(os.path.join(klasor, f'{ad}.json'), {'v': SURUM, 'o': liste})
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
        'bolgeler': sayi,
        'kaynak': '© OpenStreetMap katkıcıları, ODbL',
    }
    _dosya(os.path.join(klasor, 'dizin.json'), dizin)
    return dizin


def yaz_dunya(kareler, klasor, tarih=None):
    """Dünya çıktısı (v2): boş klasöre `<tarih>_<kare>.json` + dizin.json."""
    sayi, toplam = denetle(kareler, dunya=True)
    tarih = tarih or datetime.date.today().isoformat()
    os.makedirs(klasor, exist_ok=True)
    if os.listdir(klasor):
        raise CamiHatasi(f'{klasor} boş değil')
    for ad, liste in kareler.items():
        _dosya(os.path.join(klasor, f'{tarih}_{ad}.json'), {'v': DUNYA_SURUM, 'o': liste})
    dizin = {
        'v': DUNYA_SURUM,
        'kapsam': 'dunya',
        'tarih': tarih,
        'kare': KARE,
        'kareler': sorted(kareler),
        'toplam': toplam,
        'bolgeler': sayi,
        'kaynak': '© OpenStreetMap katkıcıları, ODbL',
    }
    _dosya(os.path.join(klasor, 'dizin.json'), dizin)
    return dizin


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    klasor = sys.argv[2] if len(sys.argv) > 2 else 'camiler'
    with open(sys.argv[1], encoding='utf-8') as g:
        kareler = ayikla(g)
    if len(sys.argv) > 3:
        # Önce dünya: denetimi düşerse depodaki eski dosyalara da dokunulmaz
        d = yaz_dunya(kareler, sys.argv[3])
        print(f"dünya: {d['toplam']} kayıt {d['bolgeler']}, {len(d['kareler'])} kare → {sys.argv[3]}/")
    dizin = yaz(kareler, klasor)
    print(f"depo: {dizin['toplam']} kayıt {dizin['bolgeler']}, {len(dizin['kareler'])} kare → {klasor}/")


if __name__ == '__main__':
    main()
