"""Riconoscimento vocale (speech-to-text) tramite Whisper.

Componente condiviso da CLI e interfaccia web: entrambe registrano audio e ne ottengono il testo.
"""
import numpy as np
import torch
from transformers import pipeline

from chatbot import config


class SpeechToText:
    """Wrapper attorno alla pipeline Whisper di transformers."""

    def __init__(self, model: str = None):
        # usa la GPU Apple (MPS) se disponibile, altrimenti la CPU
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._pipeline = pipeline(
            "automatic-speech-recognition",
            model=model or config.WHISPER_MODEL,
            device=device,
        )

    def trascrivi_array(self, audio, sample_rate: int) -> str:
        """Trascrive un array audio (float o interi PCM) a un dato sample rate.
        Whisper vuole audio a 16 kHz: se il sample rate è diverso viene ricampionato da torchaudio."""
        dati = np.asarray(audio).astype(np.float32)
        # normalizza gli interi PCM (es. dal microfono del browser) nel range [-1, 1]
        if np.issubdtype(np.asarray(audio).dtype, np.integer):
            dati /= np.iinfo(np.asarray(audio).dtype).max
        if dati.ndim > 1:  # se stereo, media i canali in mono
            dati = dati.mean(axis=1)
        risultato = self._pipeline(
            {"raw": dati, "sampling_rate": sample_rate},
            generate_kwargs={"language": "italian"},
        )
        return risultato["text"].strip()

    def trascrivi_gradio(self, audio) -> str:
        """Trascrive il formato (sample_rate, ndarray) restituito dal microfono di Gradio."""
        sample_rate, dati = audio
        return self.trascrivi_array(dati, sample_rate)
