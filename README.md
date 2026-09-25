# Hologram OS

Penampil model 3D berwujud jendela desktop. Modelnya bisa diputar dengan gerakan tangan di depan kamera, diubah lewat chat atau suara, dan dijelaskan oleh AI. Semuanya Python: PySide6 dengan QML untuk tampilan, tanpa server web.

Tampilannya mengikuti `hologram-os-preview.png`: latar gelap hangat, grid tipis, garis kawat krem, kartu kamera di kanan bawah.

```
┌──────────────────────────────────────────────────────────┐
│ HOLOGRAM OS  [CHAT]                                      │
│ SHAPE: PYRAMID                                           │
│ ┌────────────────┐                                       │
│ │ AI ▾  [Off|On] │            ╱╲                         │
│ │ pesan...       │           ╱  ╲          ┌───────────┐ │
│ │                │          ╱____╲         │ info AI   │ │
│ └────────────────┘         PYRAMID         │ FPS, RAM  │ │
│ [Sembunyikan ⌄]                            ├───────────┤ │
│ ┌────────────────┐                         │  kamera   │ │
│ │ tulis...  🎤 ➤ │                         └───────────┘ │
│ └────────────────┘                                       │
└──────────────────────────────────────────────────────────┘
```

## Pasang

Butuh Python 3.10 sampai 3.12 (versi paket di bawah diuji bersamaan di 3.12).

```bash
python -m venv .venv
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

**Satu langkah tambahan untuk OpenCV.** `mediapipe` membawa `opencv-contrib-python`, dan paket itu menimpa plugin Qt milik PySide6 sehingga jendela bisa gagal muncul. Ganti dengan versi headless:

```bash
pip uninstall -y opencv-contrib-python opencv-python
pip install --force-reinstall --no-deps opencv-python-headless==5.0.0.93
```

(`pip check` lalu mengeluh soal opencv-contrib. Abaikan, mediapipe tetap jalan tanpanya.)

Unduh model tangan dan model suara. Keduanya tidak ikut di folder ini:

```bash
python tools/download_assets.py                  # model tangan + Whisper base (~150 MB)
python tools/download_assets.py --whisper small  # Whisper lebih akurat, lebih berat
python tools/download_assets.py --no-whisper     # hanya model tangan
```

Jalankan:

```bash
python -m hologram
python -m hologram --no-camera --no-voice   # tanpa kamera dan mikrofon
```

Tiga model 3D contoh (drone, jet tempur, pembom) dan piramida sudah ada di `assets/models/`. Semuanya dibuat oleh `tools/make_placeholder_models.py`, bentuknya generik, bukan replika pesawat sungguhan.

## AI

**Offline lewat Ollama.** Pasang Ollama dari ollama.com, jalankan, lalu tarik model. Untuk laptop biasa:

```bash
ollama pull qwen2.5:1.5b     # ringan, sekitar 1 GB
ollama pull qwen3:4b         # lebih pintar, sekitar 2,5 GB
```

Dropdown di kartu chat menampilkan daftar model seperti `ollama list` (NAME, ID, SIZE, MODIFIED). Titik krem berarti muat di RAM saat ini, titik kuning berarti berat. Pilihan **Auto** mengambil model terbesar yang masih aman. Kalau Ollama belum jalan, kartu chat memberi tahu, dan perintah sederhana seperti zoom tetap bisa lewat pengenalan kata kunci.

**Online lewat Gemini.** Salin `.env.example` menjadi `.env`, isi `GEMINI_API_KEY` (kunci gratis dari Google AI Studio). Tekan **ONLINE**. Pada mode ini AI menerima tangkapan tampilan 3D dan boleh mencari info di internet, jadi pertanyaan seperti "ini model apa, jelaskan jenisnya" dijawab dari gambar dan data model.

Nama model Gemini ada di `config.toml` (`gemini_models`). Model lama cepat pensiun (`gemini-1.5-flash`, `gemini-2.0-flash`, dan `gemini-2.5-*` sudah dijadwalkan mati atau sudah mati), jadi jangan menebak nama. Jalankan `python tools/check_gemini.py` untuk melihat model yang benar-benar tersedia untuk kuncimu. Perintah itu tidak memakai kuota.

Aplikasi sengaja hemat permintaan: satu pesan hanya dikirim satu kali ke Gemini, tanpa mengulang. Kalau kuota habis (429), Gemini dijeda 60 detik. Kalau model tidak ditemukan (404), model itu dilewati sampai aplikasi dibuka lagi. Selama jeda, AI memakai mode offline dan menuliskan alasannya di chat.

Aturan pindah otomatis, semuanya ditulis satu baris di chat:

- Internet putus saat mode online: pindah ke offline.
- Gemini gagal atau kuota habis: coba penyedia cadangan (Groq atau OpenRouter kalau diaktifkan di `config.toml`), lalu Ollama.
- Perintah ringan (zoom, putar, ganti model) saat mode online dikerjakan model lokal lebih dulu supaya kuota tidak terbuang.
- Tanpa internet, dropdown hilang dan hanya info model yang terlihat.

Bisa juga meminta lewat kalimat: "pindah ke online dan jelaskan pesawat ini". AI pindah mode, lalu menjawab pertanyaannya. Kalau tidak bisa pindah (tanpa internet atau tanpa kunci), AI menjelaskan alasannya.

## Cara pakai

**Gerakan tangan.** Buka telapak di depan kamera, geser cepat ke kanan, kiri, atas, atau bawah. Model berputar sekali 45° lalu berhenti pelan. Setelah satu swipe ada jeda sekitar 0,7 detik supaya tangan yang kembali ke posisi awal tidak terbaca sebagai swipe berlawanan. Kalau terlalu sensitif atau kurang peka, atur bagian `[swipe]` di `config.toml`.

**Chat dan suara.** Contoh kalimat:

```
zoom in          perkecil          putar ke kiri
ganti ke drone   tampilkan jet tempur
model apa saja   ini model apa (mode online)
```

Tombol mikrofon merekam sampai kamu berhenti bicara, lalu hasilnya terkirim otomatis. Saat AI berbicara, kolom input berubah jadi bar suara yang bergerak mengikuti suaranya. Klik bar itu untuk menghentikan.

**Tampilan.** Tombol `CHAT` di samping judul menyembunyikan seluruh sisi kiri. Tombol di atas kartu input hanya menyembunyikan percakapan: kartu meluncur turun saat disembunyikan, naik saat ditampilkan.

## Menambah model 3D

1. Taruh file `.glb` (atau `.gltf`) di `assets/models/`.
2. Tambahkan satu entri di `assets/models.json`:

```json
{
  "id": "b2",
  "name": "B-2 Spirit",
  "aliases": ["pembom siluman", "b2"],
  "category": "pesawat",
  "country": "AS",
  "kind": "pembom strategis sayap terbang",
  "file": "b2.glb",
  "description": "Pembom siluman bertenaga empat mesin.",
  "license": "CC-BY-4.0",
  "source": "https://contoh.com/model-b2"
}
```

Lalu ucapkan "ganti ke pembom siluman". Ukuran dan posisi model dihitung otomatis dari bounds-nya. Isi `country`, `kind`, dan `description` dengan benar, karena AI memakai data itu saat menjelaskan. Periksa lisensi tiap model sebelum dipakai atau dibagikan.

Model asli biasanya rapat segitiganya. Kalau mode garis kawat terlihat terlalu padat, set `wireframe = false` di bagian `[viewer]`.

## Susunan folder

```
hologram/
  app.py, __main__.py, config.py
  core/        controller, aksi AI, kata kunci, info perangkat, model pesan
  ai/          Ollama, Gemini, penyedia format OpenAI, router, prompt
  vision/      kamera, MediaPipe, deteksi swipe, gambar untuk kartu kamera
  voice/       mikrofon ke teks, suara AI, level suara
  models3d/    daftar model dari models.json
  ui/          Main.qml, theme/Theme.qml, components/*.qml
assets/        models/*.glb, models.json, ai/, whisper/
tools/         download_assets.py, make_placeholder_models.py
tests/
```

## Uji

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

## Kalau ada masalah

| Gejala | Yang dicek |
|---|---|
| Jendela tidak muncul, ada galat plugin Qt "xcb" atau "cocoa" | Langkah OpenCV di atas belum dilakukan. |
| Kartu kamera menulis "Kamera tidak ditemukan" | Tutup aplikasi lain yang memakai kamera, atau ubah `[camera] index` di `config.toml`. |
| Kartu kamera menulis "Model tangan belum diunduh" | Jalankan `python tools/download_assets.py`. |
| Mikrofon menjawab "Model Whisper belum diunduh" | Sama, lalu pastikan `stt_model` cocok dengan nama folder di `assets/whisper/`. |
| Tidak ada suara AI | Lihat baris pesan di chat. Di Linux pyttsx3 butuh `espeak-ng`. `sounddevice` butuh PortAudio (`libportaudio2`). |
| Garis kawat tidak muncul | Driver GPU lama. Set `wireframe = false`. |
| "Kuota gratis Gemini habis (429)" | Tunggu, atau aktifkan penyedia cadangan di `config.toml`. Offline tetap jalan. |
| Swipe salah arah terbaca | Naikkan `dominance` dan `distance` di `[swipe]`. |

## Yang sudah dan belum diuji

Sudah, di lingkungan Linux tanpa layar (Xvfb dengan OpenGL perangkat lunak): 56 uji otomatis, aplikasi utuh dijalankan dan diambil tangkapan layarnya di beberapa ukuran jendela dan keadaan (chat tersembunyi, dropdown terbuka, mode online, tanpa internet, bar suara, kamera dengan sumber video palsu). Rotasi dan zoom dicek lewat tangkapan layar.

Belum bisa diuji di sana, jadi periksa di mesinmu: kamera dan deteksi tangan sungguhan (model MediaPipe tidak bisa diunduh dari lingkungan itu), mikrofon dan Whisper, suara pyttsx3, Ollama asli, dan panggilan Gemini asli. Logika di sekitar semuanya sudah diuji dengan penyedia tiruan. Uji gesture pertama kali sebaiknya dengan pencahayaan cukup dan telapak menghadap kamera.
