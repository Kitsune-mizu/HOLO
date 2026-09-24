"""Tebak bahasa kalimat pendek: Indonesia atau Inggris. Kalimat yang meragukan mengikuti bahasa sebelumnya."""
from __future__ import annotations

import re

# Hanya kata yang khas satu bahasa. Kata bersama ("model", "zoom", "drone") sengaja tidak dimasukkan.
_EN = {
    "the", "is", "are", "was", "what", "how", "please", "hello", "hi", "hey", "thanks", "thank", "you",
    "can", "could", "would", "show", "change", "switch", "turn", "this", "that", "and", "me", "my", "which",
    "who", "why", "where", "when", "display", "bigger", "smaller", "closer", "list", "rotate", "left", "right",
    "tell", "about", "explain", "does", "do", "it", "its", "of", "with", "from", "there", "here", "now",
    "a", "an", "to", "in", "on", "for", "your", "give", "make", "look", "see", "let", "want", "need",
}
_EN -= {"in", "to", "a", "list", "left", "right"} | {"on"}       # ambigu dengan kata Indonesia atau perintah umum
_EN |= {"rotate", "left", "right"}
_ID = {
    "yang", "dan", "apa", "ini", "itu", "dengan", "untuk", "tolong", "ganti", "tampilkan", "putar", "kanan", "kiri",
    "atas", "bawah", "perbesar", "perkecil", "saya", "aku", "kamu", "bisa", "tidak", "ke", "di", "dari", "apakah",
    "bagaimana", "siapa", "kenapa", "mengapa", "berapa", "halo", "terima", "kasih", "jelaskan", "sedang", "lagi",
    "dong", "nih", "ada", "saja", "sudah", "belum", "mau", "ingin", "coba", "lebih", "sedikit", "jenis", "buatan",
    "pesawat", "negara", "munculkan", "dekatkan", "jauhkan", "sebutkan", "ceritakan",
}


def detect(text: str, default: str = "id") -> str:
    """Kembalikan "id" atau "en". Ragu-ragu: pakai `default` (bahasa percakapan sebelumnya)."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    en = sum(1 for w in words if w in _EN)
    idn = sum(1 for w in words if w in _ID)
    if idn > en:
        return "id"
    if en > idn and (en >= 2 or (en == 1 and len(words) <= 2 and idn == 0)):
        return "en"
    return default