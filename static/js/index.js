document.addEventListener("DOMContentLoaded", async () => {
    // Navbar logo/isim tıklanınca ana sayfa
    const logo = document.querySelector('.btk-logo');
    if (logo) {
        logo.style.cursor = 'pointer';
        logo.onclick = () => window.location.href = '/';
    }
    
    const listDiv = document.getElementById("video-list");
    
    // Skeleton loading
    for (let i = 0; i < 4; i++) {
        const skeleton = document.createElement("div");
        skeleton.className = "course-card";
        skeleton.innerHTML = `
            <div class="course-image skeleton-bg"></div>
            <div class="skeleton-line skeleton-title"></div>
            <div class="skeleton-line skeleton-desc"></div>
            <div class="skeleton-meta">
                <div class="skeleton-line skeleton-duration"></div>
                <div class="skeleton-line skeleton-level"></div>
            </div>
        `;
        listDiv.appendChild(skeleton);
    }
    
    try {
        const response = await fetch("/api/videolar");
        const videos = await response.json();
        listDiv.innerHTML = '';
        
        if (!videos || !videos.length) {
            listDiv.innerHTML = '<div class="no-videos">Hiç video bulunamadı.</div>';
            return;
        }
        
        videos.forEach((video, idx) => {
            const card = document.createElement("div");
            card.className = "course-card";
            card.setAttribute("tabindex", "0");
            card.setAttribute("aria-label", video.title);
            card.style.animationDelay = (0.1 * idx) + 's';
            
            // Video thumbnail'ı varsa kullan, yoksa placeholder
            const imageContent = video.thumbnail ? 
                `<img src="${video.thumbnail}" alt="${video.title}" class="course-thumbnail">` :
                `<i class="fas fa-play-circle"></i>`;
            
            card.innerHTML = `
                <div class="course-image">
                    ${imageContent}
                </div>
                <h3 class="course-title">${video.title}</h3>
                <p class="course-description">${video.description}</p>
                <div class="course-meta">
                    <div class="course-duration">
                        <i class="fas fa-clock"></i>
                        <span>${video.is_series ? 'Seri' : '~45 dk'}</span>
                    </div>
                    <div class="course-level">${video.is_series ? 'Eğitim Serisi' : 'Tekil Video'}</div>
                </div>
            `;
            
            // Karta tıklanınca video sayfasına yönlendir
            card.addEventListener('click', () => {
                try {
                    // Debug: Video bilgilerini yazdır
                    console.log("Tıklanan video:", {
                        id: video.id,
                        title: video.title,
                        is_series: video.is_series,
                        series_videos_count: video.series_videos_data?.length || 0
                    });
                    
                    // Video sayfasına doğrudan yönlendir (dosya kontrolü yapmadan)
                    const url = `video_page.html?id=${encodeURIComponent(video.id)}`;
                    console.log("Yönlendirme URL:", url);
                    console.log("Video ID:", video.id);
                    
                    // Debug: Tüm video verilerini yazdır
                    console.log("Video detayları:", JSON.stringify(video, null, 2));
                    
                    // Sayfayı yönlendir
                    window.location.href = url;
                    
                } catch (error) {
                    console.error("Yönlendirme sırasında hata:", error);
                    alert("Sayfaya yönlendirme sırasında bir hata oluştu!");
                }
            });
            
            listDiv.appendChild(card);
        });
        
    } catch (err) {
        console.error("Video listesi yüklenirken hata:", err);
        listDiv.innerHTML = '<div class="error-message">Video listesi yüklenemedi. Lütfen daha sonra tekrar deneyin.</div>';
    }
});

// NOT: Bu fonksiyon artık kullanılmıyor, ancak gelecekte gerekebilir diye tutuyoruz
async function checkFileExists(path) {
    try {
        const response = await fetch(path, { method: 'HEAD' });
        return response.ok;
    } catch (error) {
        console.error("Dosya kontrolü sırasında hata:", error);
        return false;
    }
}