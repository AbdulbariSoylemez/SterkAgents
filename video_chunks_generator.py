import os
import json
import logging
import yt_dlp
from dotenv import load_dotenv
from typing import Dict, Any, List, Tuple
import whisper
from moviepy.editor import VideoFileClip
from slugify import slugify

# YENİ: VTT formatını işlemek için gerekli kütüphaneler
import requests
import re

# YENİ: LangChain'den metin bölücü ve döküman şemasını içe aktar
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

# ========================================
# 1. ORTAM VE LOGLAMA AYARLARI (DEĞİŞİKLİK YOK)
# ========================================

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("rag_data_generation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========================================
# 2. VİDEO İŞLEME SINIFLARI (GÜNCELLENDİ)
# ========================================

class OnlineVideoProcessor:
    """
    Online videoları (örn. YouTube) işler.
    Altyazıları diske kaydetmeden doğrudan URL'den alıp işler.
    """
    def __init__(self):
        # DEĞİŞTİ: ydl_opts sadeleştirildi. Dosya yazma ile ilgili ayarlar kaldırıldı.
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True, # Video dosyasını indirme
            'subtitleslangs': ['en', 'tr'], # Sadece bu dilleri ara
        }

    # YENİ: VTT zaman damgasını milisaniyeye çeviren yardımcı fonksiyon
    def _vtt_time_to_ms(self, time_str: str) -> int:
        parts = time_str.split(':')
        h, m, s_ms = int(parts[0]), int(parts[1]), float(parts[2].replace(',', '.'))
        return int((h * 3600 + m * 60 + s_ms) * 1000)

    # YENİ: Verilen URL'den VTT altyazısını indiren ve parse eden fonksiyon
    def _parse_vtt_from_url(self, vtt_url: str) -> List[Dict]:
        try:
            response = requests.get(vtt_url)
            response.raise_for_status() # HTTP hatası varsa exception fırlat
            vtt_content = response.text
            
            # VTT formatını (zaman -> metin) yakalamak için Regex
            pattern = re.compile(
                r"(\d{2}:\d{2}:\d{2}[.,]\d{3}) --> (\d{2}:\d{2}:\d{2}[.,]\d{3})(?: .*)?\n(.*?)\n\n",
                re.DOTALL
            )
            
            segments = []
            for match in pattern.finditer(vtt_content):
                start_time, end_time, text = match.groups()
                segments.append({
                    "text": text.strip().replace('\n', ' '),
                    "start_ms": self._vtt_time_to_ms(start_time),
                    "end_ms": self._vtt_time_to_ms(end_time)
                })
            return segments
        except requests.RequestException as e:
            logger.error(f"VTT URL'sini indirirken hata oluştu: {e}")
            return []
        except Exception as e:
            logger.error(f"VTT içeriği parse edilirken hata: {e}")
            return []

    # DEĞİŞTİ: get_transcript metodu tamamen yeniden yazıldı.
    def get_transcript(self, video_url: str) -> Tuple[List[Dict], str, str]:
        logger.info(f"'{video_url}' adresindeki online video işleniyor (in-memory)...")
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                video_title = info.get('title', 'bilinmeyen_video')
                video_id = info.get('id', slugify(video_title))
                
                # Altyazı URL'sini bulmak için öncelik sırası:
                # 1. Manuel Türkçe -> 2. Manuel İngilizce -> 3. Otomatik Türkçe -> 4. Otomatik İngilizce
                sub_url = None
                sub_info = None
                
                if info.get('subtitles') and info['subtitles'].get('tr'):
                    sub_info = info['subtitles']['tr']
                elif info.get('subtitles') and info['subtitles'].get('en'):
                    sub_info = info['subtitles']['en']
                elif info.get('automatic_captions') and info['automatic_captions'].get('tr'):
                    sub_info = info['automatic_captions']['tr']
                elif info.get('automatic_captions') and info['automatic_captions'].get('en'):
                    sub_info = info['automatic_captions']['en']
                
                if sub_info:
                    # 'vtt' formatındaki ilk uygun altyazıyı bul
                    for sub in sub_info:
                        if sub.get('ext') == 'vtt':
                            sub_url = sub.get('url')
                            break
                
                if not sub_url:
                    raise ValueError("Videoda uygun formatlı (VTT) Türkçe veya İngilizce altyazı bulunamadı.")
                
                logger.info(f"VTT formatlı altyazı URL'si bulundu. Veri işleniyor...")
                transcript_segments = self._parse_vtt_from_url(sub_url)

                if not transcript_segments:
                    raise ValueError("Altyazı verisinden zaman damgalı segment çıkarılamadı.")

                logger.info(f"'{video_title}' için transkript başarıyla çıkarıldı.")
                return transcript_segments, video_title, video_id

        except Exception as e:
            logger.error(f"Online video işlenirken hata oluştu: {e}")
            return None, None, None

class LocalVideoProcessor:
    def __init__(self, model_size="medium"):
        logger.info(f"Whisper modeli yükleniyor: {model_size}")
        self.model = whisper.load_model(model_size)
        logger.info("Whisper modeli başarıyla yüklendi.")

    def get_transcript(self, file_path: str) -> Tuple[List[Dict], str, str]:
        logger.info(f"'{file_path}' adresindeki lokal video işleniyor...")
        if not os.path.exists(file_path):
            logger.error(f"Dosya bulunamadı: {file_path}")
            return None, None, None
        try:
            video = VideoFileClip(file_path)
            temp_audio_path = "temp_audio.mp3"
            video.audio.write_audiofile(temp_audio_path, codec='mp3')
            video.close()
            logger.info("Videodan ses başarıyla ayrıştırıldı.")

            logger.info("Whisper ile transkripsiyon başlatılıyor...")
            result = self.model.transcribe(temp_audio_path, verbose=False, word_timestamps=False)
            logger.info("Transkripsiyon tamamlandı.")

            transcript_segments = []
            for segment in result.get("segments", []):
                transcript_segments.append({
                    "text": segment["text"].strip(),
                    "start_ms": int(segment["start"] * 1000),
                    "end_ms": int(segment["end"] * 1000)
                })
            
            video_title = os.path.basename(file_path)
            video_id = slugify(os.path.splitext(video_title)[0]) # Dosya adından ID oluştur

            os.remove(temp_audio_path)
            logger.info("Geçici ses dosyası silindi.")
            
            return transcript_segments, video_title, video_id
        except Exception as e:
            logger.error(f"Lokal video işlenirken hata oluştu: {e}")
            if 'temp_audio_path' in locals() and os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            return None, None, None

# ========================================
# 3. YENİ SINIF: RAG İÇİN VİDEO PARÇALAYICI (CHUNKER)
# ========================================
class VideoChunker:
   
    # DEĞİŞTİ: Artık karakter boyutuna göre değil, cümle sayısına göre çalışıyor.
    def __init__(self, sentences_per_chunk: int = 5):
        """
        Args:
            sentences_per_chunk (int): Her bir metin parçasında (chunk) bulunması gereken cümle sayısı.
        """
        # LangChain'in text_splitter'ına artık bu sınıfta ihtiyacımız yok.
        if sentences_per_chunk <= 0:
            raise ValueError("sentences_per_chunk pozitif bir tamsayı olmalıdır.")
        self.sentences_per_chunk = sentences_per_chunk
        logger.info(f"VideoChunker başlatıldı: Her chunk için {self.sentences_per_chunk} cümle hedefleniyor.")

    def _generate_timestamp_link(self, video_id: str, start_ms: int) -> str:
        """YouTube veya benzeri platformlar için zaman damgası linki oluşturur."""
        if video_id and len(video_id) == 11:
            return f"https://www.youtube.com/watch?v={video_id}&t={start_ms // 1000}s"
        return None

    def chunk_transcript(self, transcript_segments: List[Dict], video_id: str, video_title: str) -> List[Dict]:
        """
        Transkripti alır ve RAG'e uygun, cümle bazlı chunk listesi döndürür.
        """
        if not transcript_segments:
            logger.warning("Parçalanacak transkript segmenti bulunamadı.")
            return []

        # Önceki versiyondaki gibi, zaman damgalarını bulmak için metni ve haritayı oluştur
        full_text = ""
        char_to_time_map = []
        current_char_index = 0
        for segment in transcript_segments:
            text = segment['text']
            start_ms = segment['start_ms']
            end_ms = segment['end_ms']
            
            full_text += text + " "
            
            segment_char_len = len(text) + 1 
            char_to_time_map.append((current_char_index, current_char_index + segment_char_len, start_ms, end_ms))
            current_char_index += segment_char_len
            
        # YENİ MANTIK: LangChain splitter yerine metni cümlelere böl
        # Cümlelere ayırmak için regex. Nokta, soru işareti, ünlem sonrasındaki boşlukları hedefler.
        sentence_ending_pattern = r'(?<=[.?!])\s+'
        sentences = [s.strip() for s in re.split(sentence_ending_pattern, full_text) if s.strip()]

        chunks = []
        last_char_pos = 0
        
        # YENİ MANTIK: Cümleleri istenen sayıda grupla
        for i in range(0, len(sentences), self.sentences_per_chunk):
            sentence_group = sentences[i:i + self.sentences_per_chunk]
            chunk_text = " ".join(sentence_group)

            # Bu yeni chunk metninin tam metindeki yerini ve zaman damgalarını bul
            try:
                chunk_start_char = full_text.index(chunk_text, last_char_pos)
            except ValueError:
                logger.warning(f"Chunk metni tam olarak bulunamadı. Yaklaşık pozisyon kullanılıyor: {chunk_text[:50]}...")
                chunk_start_char = last_char_pos
            
            chunk_end_char = chunk_start_char + len(chunk_text)
            last_char_pos = chunk_start_char # Bir sonraki arama için pozisyonu güncelle (örtüşmeyi önler)

            chunk_start_ms = -1
            chunk_end_ms = -1

            # Başlangıç zamanını bul
            for start_char, end_char, seg_start_ms, _ in char_to_time_map:
                if chunk_start_char >= start_char and chunk_start_char < end_char:
                    chunk_start_ms = seg_start_ms
                    break
            
            # Bitiş zamanını bul
            for start_char, end_char, _, seg_end_ms in reversed(char_to_time_map):
                if chunk_end_char > start_char:
                    chunk_end_ms = seg_end_ms
                    break

            if chunk_start_ms == -1 and transcript_segments: chunk_start_ms = transcript_segments[0]['start_ms']
            if chunk_end_ms == -1 and transcript_segments: chunk_end_ms = transcript_segments[-1]['end_ms']

            chunks.append({
                'chunk_index': len(chunks),
                'text': chunk_text,
                'start_ms': chunk_start_ms,
                'end_ms': chunk_end_ms,
                'metadata': {
                    'video_id': video_id,
                    'video_title': video_title,
                    'timestamp_link': self._generate_timestamp_link(video_id, chunk_start_ms)
                }
            })
            
        logger.info(f"'{video_title}' için {len(transcript_segments)} segment ve {len(sentences)} cümle, {len(chunks)} chunk'a bölündü.")
        return chunks