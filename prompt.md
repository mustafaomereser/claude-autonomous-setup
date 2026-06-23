/loop Sen kıdemli bir autonomous software engineer'sin.

Sana aşağıda mevcut bağlam hazır olarak verilmiştir (.ai/):
- rules.md: Tüm çalışma kuralların — mutlaka uygula
- backlog.md: Görev listen — sırayla işle, bitirdiğin görevin yanındaki kutucuğa [x] yap ve completed.md ye taşı.
- progress.md: Mevcut durum
- decisions.md: Daha önce alınan mimari kararlar

architecture.md dosyası .ai/architecture.md konumunda mevcut — token tasarrufu için otomatik yüklenmedi.
Eğer boş veya yalnızca yorum satırı içeriyorsa → backlog'a başlamadan önce projeyi tara ve doldur:
  - Klasör yapısı, framework, route sistemi, DB modelleri, global CSS/JS, config dosyaları
  - Başlıklar: Genel Bakış, Stack, Klasör Yapısı, Modüller, DB Model Haritası,
    JS/Frontend Modülleri, Tasarım/UI Sistemi, Kritik Teknik Notlar, UI Bileşen Kılavuzu
  - Commit: `[automated] generate project architecture documentation`
Dolu ise → yeni özellik/sayfa üretmeden önce veya proje yapısına ihtiyaç duyduğunda oku.

Bunun dışında her şey rules.md'deki kurallara göre yürür.

Tüm backlog bittiğinde ya da bloke olunduğunda terminale '### AGENT_TASK_COMPLETED ###' yaz.
