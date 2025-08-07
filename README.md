# SterkAgents - Video Eğitim RAG Platformu - http://www.trendizayn.com/

SterkAgents, eğitim videolarını işleyerek Retrieval Augmented Generation (RAG) tabanlı bir asistan oluşturan modern bir eğitim platformudur. Kullanıcılar, eğitim videolarını izlerken içerikle ilgili sorular sorabilir ve gerçek zamanlı yanıtlar alabilirler.

## Özellikler

- **Video Eğitim İçeriği**: Eğitim videolarını organize bir şekilde sunar ve izleme deneyimi sağlar
- **RAG Tabanlı Asistan**: Eğitim içeriğine özel, video içeriklerinden bilgi çıkaran yapay zeka asistanı
- **Çoklu Dil Desteği**: Türkçe ve İngilizce dillerinde içerik ve asistan desteği
- **Multimodal Soru Cevaplama**: Video içeriğinden hem metin hem de görsel bilgileri kullanarak soruları yanıtlar
- **Otomatik Transkripsiyon**: Video içeriklerini otomatik olarak transkribe eder ve işler
- **Performans Optimizasyonu**: LRU önbellek ve verimli vektör depolama ile hızlı yanıt süreleri

## Teknoloji Yığını

- **Backend**: FastAPI (Python)
- **Frontend**: HTML, CSS, JavaScript
- **Vektör Veritabanı**: ChromaDB
- **Yapay Zeka**: Google Gemini API (Embedding ve LLM)
- **Video İşleme**: OpenCV, MoviePy, Whisper
- **Önbellek**: LRU Cache

## Kurulum

### Gereksinimler

- Python 3.9+
- Google API Anahtarı (Gemini API için)
- FFmpeg (Video işleme için)

### Adımlar

1. Repoyu klonlayın:
   ```bash
   git clone https://github.com/kullaniciadi/SterkAgents.git
   cd SterkAgents
   ```

2. Sanal ortam oluşturun ve bağımlılıkları yükleyin:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. `.env` dosyası oluşturun ve Google API anahtarınızı ekleyin:
   ```
   GOOGLE_API_KEY=your_google_api_key_here
   ```

4. Eğitim videolarını `Education_video` klasörüne ekleyin:
   ```
   Education_video/
   ├── Kurs_Adı_1/
   │   ├── video1.mp4
   │   ├── video2.mp4
   │   └── ...
   ├── Kurs_Adı_2/
   │   ├── video1.mp4
   │   └── ...
   ```

5. Uygulamayı başlatın:
   ```bash
   python web_api_service.py
   ```

6. Tarayıcınızda `http://localhost:5001` adresine gidin.

## Kullanım

1. Ana sayfada mevcut eğitim kurslarını görüntüleyin
2. Bir kursa tıklayarak video izleme sayfasına gidin
3. Sağ alt köşedeki asistan simgesine tıklayarak eğitim asistanını açın
4. Eğitim içeriği hakkında sorular sorun ve yanıtlar alın
5. Sağ panelde eğitimin tüm videolarını görüntüleyin ve istediğiniz videoya geçiş yapın

## Proje Yapısı

- `app.py`: Ana FastAPI uygulaması ve API endpoint'leri
- `web_api_service.py`: Web servis API'si ve endpoint'leri
- `query_manager.py`: RAG sorgu yöneticisi
- `video_chunks_generator.py`: Video işleme ve parçalama
- `create_vector_store.py`: Vektör veritabanı oluşturma
- `extract_image_from_video.py`: Video karelerini çıkarma
- `static/`: CSS ve JavaScript dosyaları
- `templates/`: HTML şablonları
- `Education_video/`: Eğitim videoları
- `rag_collections/`: RAG vektör veritabanları

## Güvenlik

- API anahtarı güvenli bir şekilde yönetilir
- Path traversal saldırılarına karşı koruma
- Dosya erişim kontrolleri
- Hata yönetimi ve loglama

## Katkıda Bulunma

1. Bu repoyu fork edin
2. Feature branch oluşturun (`git checkout -b feature/amazing-feature`)
3. Değişikliklerinizi commit edin (`git commit -m 'Add some amazing feature'`)
4. Branch'inize push edin (`git push origin feature/amazing-feature`)
5. Pull Request açın

## Lisans

Bu proje [MIT Lisansı](LICENSE) altında lisanslanmıştır.
