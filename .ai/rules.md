# Agent Rules

- backlog.md sırayla işlenir, üstten alta
- Her task sonunda progress.md güncellenir (completed'a ekle, current task güncelle)
- Mimari/kritik karar alınınca decisions.md'ye yaz
- Görev belirsizse architecture.md'yi referans al, sormadan en mantıklı kararı ver
- Kullanıcıya soru sormadan ilerle

### KOD KALİTESİ VE ÖNEMİ (KRİTİK):
- Yapıya sadık kal ve gerekirse diğer sayfalardan/modüllerden örnek bak.
- Yapıya sadık kalmadığın her an teknik borç doğurur.
- Eğer yeni bir yapı da gerekiyorsa projenin mevcut yapısına en uygun şekilde yap.

## BOM (Byte Order Mark) Kuralı — KRİTİK
- PHP (ve diğer) dosyaları **ASLA** UTF-8 BOM (`0xEF 0xBB 0xBF`) ile kaydedilmemeli. BOM, HTML çıktısında `&#xFEFF;` karakteri olarak görünür ve sayfa düzenini bozar.
- PowerShell ile dosya yazarken: `[System.IO.File]::WriteAllBytes(...)` veya `Out-File -Encoding utf8NoBOM` kullan. `Set-Content` ve `Out-File -Encoding utf8` Windows'ta BOM ekler — KULLANMA.
- BOM şüphesi kontrolü: `$b = [System.IO.File]::ReadAllBytes($f); $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF`
- Toplu temizleme:
  ```powershell
  Get-ChildItem -Recurse -Include "*.php" | Where-Object { $_.FullName -notmatch '\\vendor\\' } | ForEach-Object {
      $b = [System.IO.File]::ReadAllBytes($_.FullName)
      if ($b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) {
          [System.IO.File]::WriteAllBytes($_.FullName, $b[3..($b.Length-1)])
      }
  }
  ```

## Test Kuralları
- Her görev sonunda değiştirilen dosyaları syntax kontrolünden geçir
- İlgili route → controller → view zincirini oku ve tutarlılığını doğrula
- JS değişikliklerinde event listener, fonksiyon çağrısı ve syntax hatalarını kontrol et
- SCSS varsa derle; watch komutuna güvenme
- Hata bulunursa düzelt, sonra commit at
- Her migration güncellemesinden sonra migrate komutunu çalıştır

## Bütünlük Kontrol Kuralları
- Değiştirilen her view için route'un var olduğunu doğrula
- Kullanılan controller metodunun gerçekten tanımlı olduğunu kontrol et
- View'da kullanılan CSS sınıflarının global stylesheet'te tanımlı olduğunu doğrula
- JS'de kullanılan global fonksiyon/modüllerin ilgili dosyalarda tanımlı olduğunu doğrula
- Model'de kullanılan kolon isimlerinin migration ile eşleştiğini kontrol et
- Hata bulunursa düzelt, sonra devam et

## Commit Kuralları
- Her tamamlanan görev sonunda commit at
- Mesaj formatı: `[automated] <değişiklik özeti (İngilizce)>`
- Son satır: `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
- Dokümantasyon / .ai dosya değişikliklerini commit mesajına yaz
- `git add` ile sadece değiştirilen dosyaları stage'e al, `git add -A` kullanma
- `git push` at

### DÖNGÜ VE ÇIKIŞ KURALLARI (KRİTİK):
1. Her döngü adımında YALNIZCA tek bir backlog görevine odaklan. Aynı anda birden fazla görevi kodlamaya çalışma.
2. Eğer backlog'da açık (yapılmamış) hiçbir görev kalmadıysa, progress.md'deki status alanını "COMPLETED" yap, terminale "BACKLOG EMPTY - TERMINATING LOOP" yaz ve döngüyü hemen sonlandır.
3. Eğer üst üste 3 döngü boyunca aynı hatayı alıyor ve çözemiyorsan, kodu son stabil commit'e geri çek, progress.md'ye hatayı not düş ve "BLOCKED - NEED HUMAN INTERVENTION" yazarak döngüden çık.
4. Her başarılı adımdan sonra bir sonraki göreve geçmeden önce mutlaka `.ai/` altındaki tüm dosyaları (progress, decisions, rules) git'e commit'le.

## Proje Özelinde Eklenecek Kurallar
<!-- Bu bölümü kendi projenize göre doldurun -->
<!-- Örnek: framework-spesifik kurallar, tasarım sistemi kuralları, API kullanım kuralları vb. -->
