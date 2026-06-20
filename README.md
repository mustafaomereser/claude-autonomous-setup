# AI Agent Kit — Kullanım Kılavuzu

Bu kit, bir projeye autonomous Claude Code agent'ı entegre etmek için gereken dosyaların şablonudur.

## Kurulum

1. Bu klasördeki tüm dosyaları yeni projenizde `.ai/` klasörüne kopyalayın
2. `prompt.txt`'i proje kökünde bırakın (veya claude `/loop` komutunda referans verin)
3. Aşağıdaki sırayla doldurun:

| Dosya | Ne yapılacak |
|---|---|
| `architecture.md` | Projenizin stack, klasör yapısı, modüller ve kritik teknik notlarını yazın |
| `rules.md` | "Proje Özelinde Eklenecek Kurallar" bölümünü doldurun |
| `backlog.md` | Görevleri yazın |
| `decisions.md` | Boş bırakın — agent dolduracak |
| `progress.md` | Boş bırakın — agent dolduracak |
| `completed.md` | Boş bırakın — agent/siz dolduracaksınız |

## Dosyaların Rolü

```
prompt.txt      → Agent'a verilen ana direktif (claude /loop içinde çalışır)
.ai/
  rules.md      → Çalışma kuralları (commit, test, döngü mantığı, BOM uyarısı)
  architecture.md → Projenin yapısı, stack, bileşen kılavuzu (agent referans alır)
  backlog.md    → Yapılacaklar listesi + tamamlanan tasklara feedback bölümü
  completed.md  → Tamamlanan tasklar (FB-XXX ID ile etiketli)
  progress.md   → Agent'ın güncel durumu, aktif görev, tamamlananlar
  decisions.md  → Mimari kararlar logu
```

## Çalıştırma

```bash
# Claude Code CLI ile
claude "/loop prompt.txt"

# Veya Claude Code'da
/loop prompt.txt
```

## Feedback Sistemi

Tamamlanan bir göreve geri bildirim vermek için `backlog.md`'deki Feedback bölümüne:

```
[FB-007] Bu özellikte X sorunu var, tekrar bak
```

yazın. Agent bir sonraki döngüde bunu okuyup ilgili taski yeniden ele alır.

Yeni FB-XXX ID'lerini `completed.md`'deki son ID'den devam ettirin.

## Döngü Çıkış Koşulları

- Backlog tamamen bitince: `BACKLOG EMPTY - TERMINATING LOOP`
- 3 döngü üst üste aynı hata: `BLOCKED - NEED HUMAN INTERVENTION`
- Her görev sonunda: `### AGENT_TASK_COMPLETED ###`
