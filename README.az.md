# Wedding Mix Maker

[English](README.md) · **Azərbaycanca**

> DJ xidməti bahadır. Wedding Mix Maker öz DJ setinizi hazırlamaq üçün sadə
> tətbiqdir: mahnıları və ya YouTube linklərini əlavə edin, kəsin, rəvan
> keçidlər qurun və hazır miksi bir fayl kimi ixrac edin.

Toy musiqisini bir noutbukda, DJ və ya DJ proqramı olmadan hazırlamaq üçün
kiçik lokal veb tətbiq. Mahnıları əlavə edin, dalğa forması üzərində kəsin,
keçidləri qurun və hamısını bir WAV və ya MP3 faylı kimi ixrac edin. Hesab,
hostinq və bulud lazım deyil. Musiqiniz öz kompüterinizdə qalır.

Tətbiq DJ tapılmayan bir kənd toyu üçün hazırlanıb. DJ proqramları çox mürəkkəb
idi, ona görə də interfeys texnikadan anlayışı olmayan bir ailə üzvünün də
rahat istifadə edə biləcəyi şəkildə qurulub.

## İmkanlar

- **İstənilən mənbədən idxal.** Audio və ya video faylları (MP3, M4A, FLAC,
  WAV, OGG, OPUS, MP4, MKV və ffmpeg-in aça bildiyi digər formatlar) sürüşdürüb
  atın, ya da YouTube video və pleylist linkini yapışdırın. Pleylistdən hansı
  mahnıların əlavə olunacağını özünüz seçirsiniz.
- **Kitabxana.** Fonda işləyən idxal prosesləri və onların gedişatı, axtarış,
  adını dəyişmə, dinləmə, silmə və uğursuz idxalı təkrarlama. Brauzer tabını
  bağlasanız da proseslər davam edir.
- **Dəqiq kəsmə.** Böyüdülə bilən dalğa forması üzərində başlanğıc və son
  nöqtələri təyin edin. Klaviatura qısayolları var (`i` / `o` başlanğıcı və
  sonu oxutma nöqtəsində qoyur), səssiz hissələrin kəsilməsi avtomatik təklif
  olunur.
- **Miksin qurulması.** Sürüşdürərək sıralama, hər mahnı üçün səsin artıb-azalması
  (fade) və səs gücü, hər iki mahnı arasında krosfeyd, fasilə və ya birbaşa keçid.
  İstənilən keçidi ayrıca dinləmək olar. Geri al və təkrarla funksiyaları var.
- **Bərabər səs səviyyəsi.** İstəyə görə bütün mahnılar hədəf LUFS səviyyəsinə
  gətirilir ki, hamısı təxminən eyni ucalıqda səslənsin və səs xırıldamasın.
- **İxracdan əvvəl dinləyin.** Bütün miksi ixracla eyni səs emalı ilə yüngül
  önizləmə kimi hazırlayın və istənilən mahnıya keçin.
- **İxrac.** Bir MP3 (192/256/320 kbps) və ya WAV faylı, mahnı siyahısı və
  istəyə görə ayrı-ayrı mahnıların ZIP arxivi.
- Mahnı adlarında Azərbaycan, kiril və istənilən digər Unicode hərfləri ola bilər.

## Texnologiyalar

| Qat | Seçim |
| --- | --- |
| Backend | Python 3.11+, FastAPI, Uvicorn, SQLModel ilə SQLite |
| Audio | ffmpeg / ffprobe (açma, analiz, render) |
| YouTube | yt-dlp, JavaScript mühiti kimi Deno |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, Zustand |
| Dalğa forması və sıralama | wavesurfer.js, dnd-kit |
| Testlər | pytest, Vitest, Playwright |

Həm API-ni, həm də hazır React tətbiqini bir Python prosesi təqdim edir. Bütün
səs emalı backend-də aparılır; brauzer yalnız faylı yükləyir və səsi oxudur.

## Docker ilə sürətli başlanğıc

Compose plagini olan Docker lazımdır.

```sh
docker compose up --build -d --wait
```

**http://127.0.0.1:8000** ünvanını açın. İmicin içində Python, ffmpeg, yt-dlp,
Deno və hazır frontend var, ona görə də kompüterinizə başqa heç nə qurmaq
lazım deyil. İlk qurulma üçün internet lazımdır.

- Port yalnız `127.0.0.1` ünvanında açılır, yəni tətbiqə şəbəkədəki digər
  cihazlardan daxil olmaq mümkün deyil.
- 8000 portu məşğuldursa, başqa port seçin:
  `WEDDING_MIX_PORT=8001 docker compose up --build -d --wait`
  (PowerShell-də əvvəlcə `$env:WEDDING_MIX_PORT = "8001"` yazın).
- Loglar: `docker compose logs -f app`. Dayandırmaq: `docker compose down`.
- Məlumatlar `mix-data` adlı volume-da saxlanılır. `docker compose down --volumes`
  **kitabxananızı silir**; bunu yalnız həqiqətən istəyirsinizsə işlədin.
- YouTube dəyişikliklərindən sonra yt-dlp-ni yeniləmək üçün imici yenidən qurun:
  `docker compose build --no-cache --pull && docker compose up -d --wait`

`make docker-run` və `make docker-stop` bu əmrlərin qısa yoludur.

## Docker olmadan işə salmaq

### Tələblər

- Python 3.11+ (`venv` və pip ilə) və ya [uv](https://docs.astral.sh/uv/)
- Node.js 22.12+ və ya 20.19+, npm ilə birlikdə
- `PATH`-də ffmpeg **6 və ya daha yeni**, ffprobe ilə birlikdə
- `PATH`-də [Deno](https://docs.deno.com/runtime/getting_started/installation/) (yalnız YouTube idxalı üçün)
- GNU Make (Windows-da WSL və ya aşağıdakı əmrlərdən istifadə edin)

Sistem alətlərinin qurulması:

```sh
# macOS
brew install python node ffmpeg deno

# Ubuntu (`ffmpeg -version` ilə yoxlayın; bəzi versiyalarda ffmpeg 6-dan köhnədir)
sudo apt install python3 python3-venv python3-pip ffmpeg make
```

```powershell
# Windows
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Gyan.FFmpeg
winget install DenoLand.Deno
```

### Qurulma və işə salma

```sh
make setup   # .venv yaradır, backend və frontend asılılıqlarını qurur
make run     # frontend-i qurur və tətbiqi işə salır
```

Tətbiq **http://127.0.0.1:8000** ünvanında açılır. Dayandırmaq üçün Ctrl+C
basın. `make setup` mövcuddursa uv-dən, yoxdursa venv və pip-dən istifadə edir.
Konkret Python versiyası seçmək üçün: `make setup PYTHON=python3.12`. Qurulma
qlobal Python paketlərinə toxunmur və sistem alətləri qurmur.

Make olmayan Windows-da:

```powershell
py -3 scripts/setup.py
npm --prefix frontend run build
cd backend
..\.venv\Scripts\python.exe -m app
```

İlk ekran ffmpeg, ffprobe, yt-dlp və Deno-nun olub-olmadığını yoxlayır və
çatışmayan alətin necə qurulacağını göstərir.

## Tərtibat (development)

```sh
make dev       # Vite :5173-də canlı yenilənmə ilə, FastAPI :8000-də avtomatik yenidən başlatma ilə
make test      # pytest, TypeScript yoxlaması, Vitest
make test-e2e  # Playwright end-to-end testi (boş data qovluğu ilə işə salın)
make build     # frontend-in backend/static/ qovluğuna istehsal üçün qurulması
```

Test səsləri ffmpeg ilə yaradılır. Musiqi faylları repozitoriyaya əlavə
edilməməlidir. Tətbiq işləyərkən interaktiv API sənədləri `/docs` ünvanındadır.

### Layihənin quruluşu

```
backend/
  app/
    api/         # routerlər: system, tracks, youtube, projects, jobs, exports
    audio/       # ffprobe, transcode, loudness, peaks, timeline, render
    importers/   # fayl yükləmə və YouTube
    models.py    # SQLModel cədvəlləri
    jobs.py      # fon proseslərinin icrası
  tests/
frontend/
  src/
    components/  # Library, ClipEditor, MixList, MixPreview, ExportDialog, ...
    api/         # tipli API klienti
    store/       # Zustand store-ları
    strings.ts   # bütün interfeys mətnləri bir yerdə
  e2e/
scripts/         # qurulma və development köməkçiləri
```

## Məlumatlar və saxlama

İş zamanı yaranan məlumatlar `data/` qovluğunda (Git tərəfindən nəzərə alınmır)
və ya `WEDDING_MIX_DATA_DIR` ilə göstərilən qovluqda saxlanılır. Orada orijinal
fayllar dəyişdirilmədən, işçi WAV nüsxələri (stereo, 44.1 kHz, 16-bit), dalğa
forması məlumatları, önizləmələr, ixrac faylları və `app.db` SQLite bazası olur.
Fayllar istifadəçinin verdiyi adlarla deyil, yaradılmış ID-lərlə saxlanılır.
Kitabxananızı qorumaq üçün bütün qovluğun və ya Docker volume-un ehtiyat
nüsxəsini çıxarın.

## Problemlərin həlli

- **Alət çatışmır kimi göstərilir:** onu `PATH`-ə əlavə edin, tətbiqi yenidən
  başladın və **Check again** düyməsini basın.
- **YouTube idxalı alınmır:** əvvəlcə yt-dlp-ni yeniləyin.
  ```sh
  .venv/bin/python -m pip install -U 'yt-dlp[default]'
  # və ya uv mühiti üçün:
  uv pip install --python .venv/bin/python --upgrade 'yt-dlp[default]'
  ```
  Windows-da `.venv\Scripts\python.exe` işlədin. Ətraflı:
  [yt-dlp asılılıqları](https://github.com/yt-dlp/yt-dlp#dependencies).

## Qeydlər

Bu, şəxsi və oflayn işləyən alətdir. Yalnız istifadə hüququnuz olan musiqini
yükləyin və səsləndirin. İnterfeys hazırda ingiliscədir; bütün mətnlər
tərcümə üçün `frontend/src/strings.ts` faylında toplanıb. Dizayn qeydləri və
ilkin plan [DESIGN.md](DESIGN.md), [PRODUCT.md](PRODUCT.md) və
[qurulma planı](Wedding%20Mix%20Maker%20%E2%80%94%20Build%20Plan.md) fayllarındadır.
