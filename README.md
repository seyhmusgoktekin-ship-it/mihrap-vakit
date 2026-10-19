# mihrap-vakit

Mihrap uygulamasının Türkiye ilçe namaz vakitleri önbelleği.

Vakitler Diyanet İşleri Başkanlığı **Awqat Salah API** servisinden haftada bir
alınır (`betik/cek.py`, `.github/workflows/cek.yml`) ve GitHub Pages ile
durağan dosya olarak sunulur. Uygulamayı kullananların cihazları Diyanet'in
servisine doğrudan bağlanmaz.

- `vakit/<ilçe>.json`: ~30 günlük satırlar `{g, v:[imsak,güneş,öğle,ikindi,akşam,yatsı], z, h}`
- `eslesme.json`: uygulamadaki ilçe kimliği → Awqat Salah kimliği

Vakit verisinin kaynağı: T.C. Diyanet İşleri Başkanlığı.
