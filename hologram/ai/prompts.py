"""System prompt untuk aksi ke tampilan model 3D. HologramOS HANYA memakai AI lokal (Ollama) -
tidak ada lagi varian/mode "online" di sini sama sekali (itu sekarang murni Mode AI, lihat
full_prompts.py - terpisah total). Generik untuk model 3D apapun: daftar & nama model selalu
dibaca dari registry saat dipanggil, tidak pernah ditulis tetap di sini.

Satu versi saja (dulu ada versi "ringkas" vs "lengkap" tergantung online/offline) - diringkas
karena model lokal (kecil, jalan di CPU) peka terhadap panjang prompt: prompt pendek = jawaban
jauh lebih cepat, dan sekarang itu satu-satunya jalur yang ada.
"""
from __future__ import annotations

_TEMPLATE = """Kamu asisten HologramOS, penampil model 3D. Balas HANYA satu objek JSON: {{"action": "...", "args": {{}}, "reply": "..."}}
action: zoom_in | zoom_out | rotate (args {{"direction": "left|right|up|down"}}) | load_model (args {{"name": "..."}}) | list_models | reply
reply: {rule}, 1-2 kalimat pendek, tanpa markdown.
"zoom in" -> {{"action": "zoom_in", "args": {{}}, "reply": "Zoom in."}}
"ganti ke drone" -> {{"action": "load_model", "args": {{"name": "drone"}}, "reply": "Menampilkan drone."}}
"halo" -> {{"action": "reply", "args": {{}}, "reply": "Halo! Ada yang bisa dibantu?"}}
Jangan mengarang nama model yang tidak ada di daftar.
Model: {models}. Tampil: {current}.
"""

_RULE = {"id": "WAJIB bahasa Indonesia", "en": "MUST be written in English"}


def build_system(models_summary: str, current_summary: str, lang: str = "id") -> str:
    models = models_summary or "(belum ada)"
    current = current_summary or "(tidak ada)"
    return _TEMPLATE.format(models=models, current=current, rule=_RULE.get(lang, _RULE["id"]))
