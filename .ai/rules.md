# Agent Rules

- Backlog sırayla işlenir
- Test başarısızsa ilerleme durur
- Her task sonunda progress güncellenir
- Yeni task üretilebilir
- Mimari değişiklik decisions.md'ye yazılır


### DÖNGÜ VE ÇIKIŞ KURALLARI (KRİTİK):
  1. Her döngü adımında YALNIZCA tek bir backlog görevine odaklan. Aynı anda birden fazla görevi kodlamaya çalışma.
  2. Eğer backlog'da açık (yapılmamış) hiçbir görev kalmadıysa, progress.md'deki status alanını "COMPLETED" yap, terminale "BACKLOG EMPTY - TERMINATING LOOP" yaz ve döngüyü hemen sonlandır (exit).
  3. Eğer üst üste 3 döngü boyunca aynı hatayı alıyor ve çözemiyorsan, kodu son stabil commit'e geri çek (git checkout), progress.md'ye hatayı not düş ve "BLOCKED - NEED HUMAN INTERVENTION" yazarak döngüden çık.
  4. Her başarılı adımdan sonra bir sonraki göreve geçmeden önce mutlaka `.ai/` altındaki tüm dosyaları (progress, decisions, rules) git'e commit'le.