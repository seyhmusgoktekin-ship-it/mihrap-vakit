#!/usr/bin/env python3
"""
Mihrap'ın "Cuma hutbesi" ekranı için Diyanet'in o haftaki Türkçe cuma hutbesi.
Yalnız standart kütüphane; anahtar/şifre gerekmez. Telefonlar Diyanet'e bağlanmaz, bu dosyayı okur.

Kaynak: https://dinhizmetleri.diyanet.gov.tr/kategoriler/yayinlarimiz/hutbeler/türkçe
  Sayfadaki `ListData = {"Row": [...]}` listesinin ilk satırı en yeni hutbedir
  (`Tarih` "30.10.2026", `Title`, `Word` = .doc, `PDF`). Metin Word dosyasından çıkarılır
  (eski ikili .doc: OLE + Word piece table; dipnot numaraları korunur).

Çıktı: hutbe/guncel.json
  {"tarih": "YYYY-MM-DD", "baslik": "...", "bolumler": [{"tur": "hitap"|"paragraf", "metin": "..."}],
   "dipnotlar": ["..."], "kaynak": "Din Hizmetleri Genel Müdürlüğü", "adres": "<PDF adresi>"}
  Paragraflardaki dipnot başvuruları `[1]`, `[2]`… biçimindedir; `dipnotlar[n-1]` karşılığıdır.

İlk satırın tarihi bu haftanın (TSİ bugünden 0–6 gün ilerideki) cuması değilse dosyaya dokunulmaz.
Doğrulama geçmezse eski dosya korunur ve betik 1 ile çıkar (görev başarısız görünür).

Kullanım: python3 -I betik/hutbe.py [YYYY-AA-GG]   (tarih verilirse o gün çalışmış gibi)
"""
import datetime
import html as html_mod
import json
import os
import re
import struct
import sys
import urllib.parse
import urllib.request

DIZIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIKTI = os.path.join(DIZIN, 'hutbe', 'guncel.json')

KOK = 'https://dinhizmetleri.diyanet.gov.tr'
LISTE = KOK + '/kategoriler/yayinlarimiz/hutbeler/' + urllib.parse.quote('türkçe')
KAYNAK = 'Din Hizmetleri Genel Müdürlüğü'
ZAMAN_ASIMI = 60
TSI = datetime.timezone(datetime.timedelta(hours=3))


class HutbeHatasi(Exception):
    pass


# --- Eski Word (.doc) ikili biçimi -------------------------------------------------------------

def _ole_akislari(veri):
    """Compound File Binary: akış adı → bayt."""
    if veri[:8] != b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        raise HutbeHatasi('Word dosyası değil')
    sektor = 1 << struct.unpack_from('<H', veri, 30)[0]
    mini = 1 << struct.unpack_from('<H', veri, 32)[0]
    dizin_ilk, = struct.unpack_from('<I', veri, 48)
    mini_sinir, mini_fat_ilk, _, difat_ilk, difat_sayi = struct.unpack_from('<IIIII', veri, 56)

    def sek(n):
        return veri[(n + 1) * sektor:(n + 2) * sektor]

    fat_sektorleri = [s for s in struct.unpack_from('<109I', veri, 76) if s < 0xFFFFFFFA]
    s = difat_ilk
    for _ in range(difat_sayi):
        if s >= 0xFFFFFFFA:
            break
        d = struct.unpack(f'<{sektor // 4}I', sek(s))
        fat_sektorleri += [x for x in d[:-1] if x < 0xFFFFFFFA]
        s = d[-1]
    fat = []
    for f in fat_sektorleri:
        fat += struct.unpack(f'<{sektor // 4}I', sek(f))

    def zincir(ilk, tablo):
        n, gorulen = ilk, set()
        while n < 0xFFFFFFFA and n not in gorulen and n < len(tablo):
            gorulen.add(n)
            yield n
            n = tablo[n]

    def oku(ilk):
        return b''.join(sek(n) for n in zincir(ilk, fat))

    dizin = oku(dizin_ilk)
    girdiler = []
    for i in range(0, len(dizin), 128):
        g = dizin[i:i + 128]
        ad_uz, = struct.unpack_from('<H', g, 64)
        ad = g[:max(ad_uz - 2, 0)].decode('utf-16-le', 'ignore')
        tur = g[66]
        ilk, boy = struct.unpack_from('<IQ', g, 116)
        girdiler.append((ad, tur, ilk, boy & 0xFFFFFFFF))
    kok = next(g for g in girdiler if g[1] == 5)
    mini_akis = oku(kok[2])
    mini_fat = []
    for n in zincir(mini_fat_ilk, fat):
        mini_fat += struct.unpack(f'<{sektor // 4}I', sek(n))

    akislar = {}
    for ad, tur, ilk, boy in girdiler:
        if tur != 2:
            continue
        if boy < mini_sinir:
            b = b''.join(mini_akis[n * mini:(n + 1) * mini] for n in zincir(ilk, mini_fat))
        else:
            b = oku(ilk)
        akislar[ad] = b[:boy]
    return akislar


def _cp1252(b):
    return bytes([b]).decode('cp1252', 'replace')


def doc_metni(veri):
    """(ana metin, dipnot + sonnot metni) — Word'ün özel karakterleri olduğu gibi (\\r paragraf, \\x02 dipnot)."""
    akislar = _ole_akislari(veri)
    wd = akislar.get('WordDocument')
    if not wd or struct.unpack_from('<H', wd, 0)[0] != 0xA5EC:
        raise HutbeHatasi('WordDocument akışı yok')
    bayrak, = struct.unpack_from('<H', wd, 10)
    tablo = akislar.get('1Table' if bayrak & 0x0200 else '0Table')
    if tablo is None:
        raise HutbeHatasi('tablo akışı yok')
    # fibRgLw: ccpText, ccpFtn, ccpHdd, (ayrılmış), ccpAtn, ccpEdn. Diyanet dipnotları sonnot (ccpEdn) olarak yazıyor.
    ccp_metin, ccp_dipnot, ccp_ust, _, ccp_aciklama, ccp_sonnot = struct.unpack_from('<6i', wd, 64 + 3 * 4)
    fc_clx, lcb_clx = struct.unpack_from('<II', wd, 154 + 33 * 8)
    clx = tablo[fc_clx:fc_clx + lcb_clx]
    i = 0
    while i < len(clx) and clx[i] == 1:  # Prc
        i += 3 + struct.unpack_from('<H', clx, i + 1)[0]
    if i >= len(clx) or clx[i] != 2:
        raise HutbeHatasi('parça tablosu yok')
    boy, = struct.unpack_from('<I', clx, i + 1)
    plc = clx[i + 5:i + 5 + boy]
    n = (boy - 4) // 12
    cpler = struct.unpack_from(f'<{n + 1}i', plc, 0)
    parcalar = []
    for k in range(n):
        fc, = struct.unpack_from('<I', plc, (n + 1) * 4 + k * 8 + 2)
        say = cpler[k + 1] - cpler[k]
        if fc & 0x40000000:
            bas = (fc & 0x3FFFFFFF) // 2
            parcalar.append(''.join(_cp1252(b) for b in wd[bas:bas + say]))
        else:
            parcalar.append(wd[fc:fc + 2 * say].decode('utf-16-le', 'replace'))
    tum = ''.join(parcalar)
    sonnot = ccp_metin + ccp_dipnot + ccp_ust + ccp_aciklama
    return tum[:ccp_metin], tum[ccp_metin:ccp_metin + ccp_dipnot] + tum[sonnot:sonnot + ccp_sonnot]


def _temizle(metin, isaret):
    """Alan kodlarını atar (sonuç kalır), dipnot başvurularını `isaret(n)` ile değiştirir; paragraflar."""
    cikti, derinlik, kod, sayac = [], 0, [], 0
    for c in metin:
        if c == '\x13':
            derinlik += 1
            kod.append(True)
            continue
        if c == '\x14':
            if kod:
                kod[-1] = False
            continue
        if c == '\x15':
            if kod:
                kod.pop()
                derinlik -= 1
            continue
        if any(kod):
            continue
        if c == '\x02':
            sayac += 1
            cikti.append(isaret(sayac))
        elif c in '\r\x07\x0c':
            cikti.append('\n')
        elif c == '\x0b':
            cikti.append(' ')
        elif c in '\x01\x08\x05' or ord(c) < 9:
            continue
        elif c == '\xa0':
            cikti.append(' ')
        else:
            cikti.append(c)
    satirlar = [re.sub(r'[ \t]+', ' ', s).strip() for s in ''.join(cikti).split('\n')]
    return [s for s in satirlar if s]


# "Aziz Müminler!", "Kıymetli Aileler! Sevgili Gençler!"
HITAP = re.compile(r'^(?:[^.!?:;“”"‘’…]{2,40}! ?){1,3}$')


def ayristir(ana, dipnot, baslik):
    """Word metni → bölümler + dipnotlar. Başlık (BÜYÜK HARF satır), `Tarih:` ve imza bölüme girmez."""
    satirlar = _temizle(ana, lambda n: f'[{n}]')
    bolumler = []
    buyuk = baslik.upper().replace('İ', 'İ').replace('I', 'I')
    for s in satirlar:
        if s.startswith('Tarih:') or s == KAYNAK or s.upper() == KAYNAK.upper():
            continue
        if not bolumler and (s == buyuk or s.upper() == baslik.upper() or s.upper() == s and len(s) < 80 and not s.endswith('!')):
            continue  # başlık satırı
        if HITAP.match(s) and len(s.split()) <= 8:
            bolumler.append({'tur': 'hitap', 'metin': s})
        else:
            bolumler.append({'tur': 'paragraf', 'metin': s})
    dipnotlar = []
    # Her not kendi başvuru işaretiyle başlar; işaretsiz satırlar (sondaki imza) not değildir.
    for s in _temizle(dipnot, lambda n: '\x00'):
        if s.startswith('\x00'):
            dipnotlar.append(s.replace('\x00', '').strip())
        elif dipnotlar and s != KAYNAK:
            dipnotlar[-1] += ' ' + s
    return bolumler, dipnotlar


def dogrula(h):
    if not isinstance(h.get('baslik'), str) or not h['baslik'].strip():
        raise HutbeHatasi('başlık boş')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', h.get('tarih', '')):
        raise HutbeHatasi('tarih bozuk')
    paragraflar = [b for b in h.get('bolumler', []) if b['tur'] == 'paragraf']
    if len(paragraflar) < 3:
        raise HutbeHatasi(f'yalnız {len(paragraflar)} paragraf')
    uzunluk = sum(len(b['metin']) for b in h['bolumler'])
    if not 1500 <= uzunluk <= 30000:
        raise HutbeHatasi(f'metin uzunluğu makul değil: {uzunluk}')
    atiflar = {int(x) for b in paragraflar for x in re.findall(r'\[(\d+)\]', b['metin'])}
    if atiflar and max(atiflar) > len(h.get('dipnotlar', [])):
        raise HutbeHatasi('dipnot sayısı tutmuyor')


def bu_cuma_mi(tarih, bugun):
    """Diyanet tarihi ("30.10.2026") bugünden 0–6 gün ilerideki bir cuma mı?"""
    try:
        g = datetime.datetime.strptime(tarih.strip(), '%d.%m.%Y').date()
    except ValueError:
        return False
    return g.weekday() == 4 and 0 <= (g - bugun).days <= 6


def _gun(tarih):
    try:
        return datetime.datetime.strptime(tarih.strip(), '%d.%m.%Y').date()
    except (AttributeError, ValueError):
        return datetime.date.min


def _tablo_satirlari(html):
    """Sayfa, betik dışı istemcilere listeyi düz HTML tablosu olarak verir (ListData = null)."""
    satirlar = []
    for tr in re.findall(r'<tr[^>]*\bms-itmhover\b[^>]*>(.*?)</tr>', html, re.S):
        hucre = re.findall(r'<td class="ms-vb2">(.*?)</td>', tr, re.S)
        if len(hucre) < 4:
            continue
        yazi = lambda h: html_mod.unescape(re.sub(r'<[^>]+>', '', h)).strip()  # noqa: E731
        bag = lambda h: html_mod.unescape((re.search(r'href="([^"]+)"', h) or [None, ''])[1])  # noqa: E731
        satirlar.append({'Tarih': yazi(hucre[0]), 'Title': yazi(hucre[1]), 'PDF': bag(hucre[2]), 'Word': bag(hucre[3])})
    return satirlar


def ilk_satir(html):
    """Listedeki en yeni hutbe (tarihe göre)."""
    satirlar = []
    m = re.search(r'ListData\s*=\s*(\{.*?\})\s*;\s*(?:var|\n|</script>)', html, re.S)
    if m:
        satirlar = json.loads(m.group(1)).get('Row') or []
    if not satirlar:
        satirlar = _tablo_satirlari(html)
    if not satirlar:
        raise HutbeHatasi('hutbe listesi bulunamadı')
    return max(satirlar, key=lambda r: _gun(r.get('Tarih', '')))


def _adres(yol):
    yol = (yol or '').strip()
    if not yol:
        return ''
    if yol.startswith('http'):
        return yol
    return KOK + urllib.parse.quote(yol, safe='/%')  # liste yolları çoğu zaman zaten kodlanmış


def getir(adres):
    istek = urllib.request.Request(adres, headers={'User-Agent': 'mihrap-vakit'})
    with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as y:
        return y.read()


def hutbe_olustur(satir, word):
    tarih = datetime.datetime.strptime(satir['Tarih'].strip(), '%d.%m.%Y').date().isoformat()
    baslik = re.sub(r'\s+', ' ', satir['Title']).strip()
    ana, dipnot = doc_metni(word)
    bolumler, dipnotlar = ayristir(ana, dipnot, baslik)
    h = {'tarih': tarih, 'baslik': baslik, 'bolumler': bolumler, 'dipnotlar': dipnotlar,
         'kaynak': KAYNAK, 'adres': _adres(satir.get('PDF'))}
    dogrula(h)
    return h


def main():
    # Elle deneme: `python3 -I betik/hutbe.py 2026-10-30` o gün çalışmış gibi davranır.
    bugun = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.datetime.now(TSI).date()
    satir = ilk_satir(getir(LISTE).decode('utf-8', 'replace'))
    if not bu_cuma_mi(satir.get('Tarih', ''), bugun):
        print(f"Bu haftanın hutbesi henüz yok (ilk satır: {satir.get('Tarih')}).")
        return 0
    try:
        h = hutbe_olustur(satir, getir(_adres(satir.get('Word'))))
    except (HutbeHatasi, KeyError, ValueError, struct.error, OSError) as e:
        print(f'Hutbe alınamadı, eski dosya korunuyor: {e}', file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(CIKTI), exist_ok=True)
    gecici = CIKTI + '.tmp'
    with open(gecici, 'w', encoding='utf-8') as f:
        json.dump(h, f, ensure_ascii=False, indent=1)
        f.write('\n')
    os.replace(gecici, CIKTI)
    print(f"{h['tarih']} {h['baslik']}: {len(h['bolumler'])} bölüm, {len(h['dipnotlar'])} dipnot")
    return 0


if __name__ == '__main__':
    sys.exit(main())
