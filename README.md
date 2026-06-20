# AI Agent Kit — Kullanım Kılavuzu

Bu kit, bir projeye autonomous Claude Code agent'ı entegre etmek için gereken dosyaların şablonudur.
Agent `auto_agent_mode.py` tarafından yönetilir — `/loop` veya manuel Claude komutlarıyla çalışmaz, verilen görevler bitene kadar kendisini döngüye sokar ve limitlere takılmaz.

---

## Kurulum

1. Bu klasördeki dosyaları yeni projenizin köküne kopyalayın
2. `.ai/` klasörünü de kopyalayın
3. Aşağıdaki sırayla doldurun:

| Dosya                 | Ne yapılacak                                                             |
| --------------------- | ------------------------------------------------------------------------ |
| `.ai/rules.md`        | "Proje Özelinde Eklenecek Kurallar" bölümünü doldurun                    |
| `.ai/backlog.md`      | Görevleri yazın                                                          |
| `.ai/architecture.md` | **Boş bırakın** — agent ilk çalışmada projeyi tarayıp kendisi dolduracak |
| `.ai/decisions.md`    | Boş bırakın — agent dolduracak                                           |
| `.ai/progress.md`     | Boş bırakın — agent dolduracak                                           |
| `.ai/completed.md`    | Boş bırakın — agent/siz dolduracaksınız                                  |
| `prompt.txt`          | Hazır, değiştirmeye gerek yok                                            |

---

## Dosyaların Rolü

```
auto_agent_mode.py  → Agent'ı başlatan ve yöneten Python scripti
prompt.txt          → Agent'a verilen ana direktif (auto_agent_mode.py tarafından okunur)
agent_output.log    → Tüm agent çıktısının kaydedildiği log dosyası (otomatik oluşur)

.ai/
  rules.md          → Çalışma kuralları (commit, test, döngü mantığı, BOM uyarısı)
  architecture.md   → Projenin yapısı, stack, bileşen kılavuzu (agent referans alır)
  backlog.md        → Yapılacaklar listesi + tamamlanan tasklara feedback bölümü
  completed.md      → Tamamlanan tasklar (FB-XXX ID ile etiketli)
  progress.md       → Agent'ın güncel durumu, aktif görev, tamamlananlar
  decisions.md      → Mimari kararlar logu
```

---

## Çalıştırma

Projenizin kök dizininde:

```bash
python auto_agent_mode.py
```

### Ne yapar?
1. `prompt.txt`'i okur, Claude'a stdin üzerinden gönderir
2. Claude'un çıktısını satır satır parse edip renkli olarak terminale basar
3. Oturum bitince (`### AGENT_TASK_COMPLETED ###` görmeden) `--continue` ile devam eder
4. **Rate limit vurulursa** reset zamanını otomatik tespit eder, bekler, uyandığında devam eder
5. `agent_output.log` dosyasına her şeyi yazar

### Durma Koşulları
| Durum                 | Agent'ın yazdığı                                                     | Script'in davranışı |
| --------------------- | -------------------------------------------------------------------- | ------------------- |
| Backlog tamamen bitti | `BACKLOG EMPTY - TERMINATING LOOP` + `### AGENT_TASK_COMPLETED ###`  | Durur               |
| 3 döngü aynı hata     | `BLOCKED - NEED HUMAN INTERVENTION` + `### AGENT_TASK_COMPLETED ###` | Durur               |
| Kullanıcı             | `Ctrl+C`                                                             | Durur               |

---

## Feedback Sistemi

Tamamlanan bir göreve geri bildirim vermek için `.ai/backlog.md`'deki Feedback bölümüne:

```
[FB-007] Bu özellikte X sorunu var, tekrar bak
```

yazın ve `python auto_agent_mode.py` ile agent'ı yeniden başlatın.
ID'leri `.ai/completed.md`'den bulabilirsiniz. Yeni ID'ler son ID'den devam eder.

---

## İlk Çalışmada Ne Olur?

`.ai/architecture.md` boş olduğu için agent önce projeyi baştan aşağı tarar:
klasör yapısı, framework, route sistemi, DB modelleri, global CSS/JS, config dosyaları.
Tarama tamamlanınca `architecture.md`'yi doldurur, commit atar ve backlog görevlerine geçer.
