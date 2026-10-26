# mihrap-vakit

Mihrap uygulamasının Türkiye ilçe namaz vakitleri önbelleği.

Vakitler Diyanet İşleri Başkanlığı **Awqat Salah API** servisinden haftada bir
alınır (`betik/cek.py`, `.github/workflows/cek.yml`) ve GitHub Pages ile
durağan dosya olarak sunulur. Uygulamayı kullananların cihazları Diyanet'in
servisine doğrudan bağlanmaz.

- `vakit/<ilçe>.json`: ~30 günlük satırlar `{g, v:[imsak,güneş,öğle,ikindi,akşam,yatsı], z, h}`
- `eslesme.json`: uygulamadaki ilçe kimliği → Awqat Salah kimliği
- `kur/usd.json`: hac/umre döviz dönüştürücüsünün USD tabanlı günlük kurları
  `{taban, tarih, guncellendi, kaynak, kaynakAdres, kurlar: {SAR: 3.75, …}}`
  (`betik/kur.py`, `.github/workflows/kur.yml`, her gün; doğrulama: `python3 -I betik/kur_test.py`).
  Adres: https://seyhmusgoktekin-ship-it.github.io/mihrap-vakit/kur/usd.json

Vakit verisinin kaynağı: T.C. Diyanet İşleri Başkanlığı.

Kurların kaynağı: [ExchangeRate-API](https://www.exchangerate-api.com) (Rates By Exchange Rate API);
yedek kaynak [fawazahmed0/exchange-api](https://github.com/fawazahmed0/exchange-api) (CC0).
