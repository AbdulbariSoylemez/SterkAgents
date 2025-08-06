document.addEventListener("DOMContentLoaded", async () => {
    try {
        const params = new URLSearchParams(window.location.search);
        const videoId = params.get("id");

        if (!videoId) {
            window.location.href = '/';
            return;
        }

        const response = await fetch("/api/videolar");
        const videos = await response.json();
        const videoData = videos.find(v => v.id === videoId);

        if (!videoData) {
            window.location.href = '/';
            return;
        }

        const videoPlayer = document.getElementById("video-player");
        const videoLoading = document.getElementById("video-loading");
        const courseTitleEl = document.getElementById("course-title");
        const moduleList = document.getElementById("module-list");
        const chatHistory = document.getElementById("chat-history");
        const chatForm = document.getElementById("chat-form");
        const questionInput = document.getElementById("user-question");
        let currentCollectionName = videoData.collection_name;
        
        // Chatbot toggle işlevselliği
        const assistantToggle = document.getElementById("assistant-toggle");
        const assistantSection = document.getElementById("assistant-section");
        const assistantClose = document.getElementById("assistant-close");
        
        if (assistantToggle) {
            assistantToggle.addEventListener("click", function() {
                assistantSection.classList.toggle("active");
            });
        }
        
        if (assistantClose) {
            assistantClose.addEventListener("click", function() {
                assistantSection.classList.remove("active");
            });
        }
        
        const updateVideoPlayer = (videoInfo) => {
            videoLoading.style.display = "flex";
            videoPlayer.style.display = "none";
            videoPlayer.src = videoInfo.path;
            videoPlayer.load();

            courseTitleEl.textContent = videoInfo.title;
            currentCollectionName = videoInfo.collection;

            document.querySelectorAll('.section-item').forEach(item => {
                item.classList.remove('current');
                if (item.dataset.videoPath === videoInfo.path) {
                    item.classList.add('current');
                }
            });
            
            // Video yüklenmesi ve koleksiyon kontrolünü paralel yap
            // Koleksiyon kontrolünü arka planda başlat, böylece video yüklenmesi beklemez
            setTimeout(() => {
                checkAndEnsureCollection(currentCollectionName);
            }, 100);
        };
                
                // İzlenen videoları saklamak için localStorage kullan
        const getWatchedVideos = () => {
            const watchedVideosStr = localStorage.getItem(`watched_${videoData.id}`) || '[]';
            return JSON.parse(watchedVideosStr);
        };
        
        // Video izlendi olarak işaretle
        const markVideoAsWatched = (videoPath) => {
            const watchedVideos = getWatchedVideos();
            if (!watchedVideos.includes(videoPath)) {
                watchedVideos.push(videoPath);
                localStorage.setItem(`watched_${videoData.id}`, JSON.stringify(watchedVideos));
                updateProgressCircle();
                renderModuleList();
            }
        };
        
        // İlerleme dairesini güncelle
        const updateProgressCircle = () => {
            const watchedVideos = getWatchedVideos();
            const totalCount = videoData.series_videos_data.length;
            const completedCount = watchedVideos.length;
            const completionPercentage = Math.round((completedCount / totalCount) * 100);
            
            // Yüzde metnini güncelle
            document.getElementById("progress-circle").querySelector("span").textContent = `${completionPercentage}%`;
            
            // Dairesel ilerleme çubuğunu güncelle
            if (completionPercentage > 0) {
                // Dairesel ilerleme için clip-path hesapla
                const angle = (completionPercentage / 100) * 360;
                let clipPath;
                
                if (angle <= 180) {
                    // 0-180 derece arası
                    const x = 50 + 50 * Math.sin(angle * Math.PI / 180);
                    clipPath = `polygon(50% 0%, 50% 50%, ${x}% 0%)`;
                } else {
                    // 180-360 derece arası
                    const x = 50 + 50 * Math.sin((angle - 180) * Math.PI / 180);
                    clipPath = `polygon(50% 0%, 100% 0%, 100% 100%, 0% 100%, 0% 0%, 50% 0%, 50% 50%, ${x}% 100%)`;
                }
                
                const progressCircle = document.querySelector(".progress-circle");
                progressCircle.style.setProperty("--clip-path", clipPath);
            }
                };
                
        const renderModuleList = () => {
            moduleList.innerHTML = '';
            const fragment = document.createDocumentFragment();
            const totalDuration = videoData.total_duration || "N/A";
            
            // İzlenen videoları al
            const watchedVideos = getWatchedVideos();
            const totalCount = videoData.series_videos_data.length;
            const completedCount = watchedVideos.length;
            const completionPercentage = Math.round((completedCount / totalCount) * 100);
            
            // İlerleme yüzdesini güncelle
            document.getElementById("progress-circle").querySelector("span").textContent = `${completionPercentage}%`;
            document.querySelector(".progress-text").textContent = `Toplam Süre: ${totalDuration}`;

            const headerItem = document.createElement('li');
            headerItem.className = 'section-item header';
            headerItem.innerHTML = `<span class="section-title">${videoData.title}</span><span class="section-duration">${totalDuration}</span>`;
            fragment.appendChild(headerItem);
            
            videoData.series_videos_data.forEach((video) => {
                const videoItem = document.createElement('li');
                videoItem.className = 'section-item';
                
                // Eğer video izlendiyse "completed" sınıfını ekle
                const watchedVideos = getWatchedVideos();
                if (watchedVideos.includes(video.video_path)) {
                    videoItem.classList.add('completed');
                }
                
                // Şu an oynatılan video ise "current" sınıfını ekle
                if (videoPlayer.src.includes(video.video_path)) {
                    videoItem.classList.add('current');
                }
                
                videoItem.dataset.videoPath = video.video_path;
                videoItem.innerHTML = `<span class="section-title">${video.title}</span><span class="section-duration">${video.duration}</span>`;
                videoItem.addEventListener('click', () => {
                    updateVideoPlayer({
                        path: video.video_path,
                        collection: videoData.collection_name,
                        title: video.title
                    });
                });
                fragment.appendChild(videoItem);
            });
            moduleList.appendChild(fragment);
        };
        
        const checkAndEnsureCollection = async (collectionName) => {
            try {
                // Önce koleksiyon var mı kontrol et
                const response = await fetch(`/api/check-collection/${collectionName}`);
                const data = await response.json();
                
                if (!data.exists) {
                    // Koleksiyon yoksa, arka planda oluşturulmasını başlat
                    console.log(`Collection ${collectionName} does not exist, starting background creation`);
                    
                    // Kullanıcıya bilgi ver - gelişmiş animasyon ile
                    const processingMsgId = `processing-${Date.now()}`;
                    chatHistory.innerHTML += `<div id="${processingMsgId}" class="assistant-msg">
                        <div class="chat-loading">
                            <span class="thinking">Veritabanı hazırlanıyor</span>
                            <div class="chat-loading-dots">
                                <div class="chat-loading-dot"></div>
                                <div class="chat-loading-dot"></div>
                                <div class="chat-loading-dot"></div>
                            </div>
                        </div>
                        <p>Bu eğitim için veritabanı hazırlanıyor. Bu işlem arka planda devam edecek ve birkaç dakika sürebilir.</p>
                        <p>Bu sırada videoyu izleyebilirsiniz. Veritabanı hazır olduğunda soru sorabileceksiniz.</p>
                    </div>`;
                    chatHistory.scrollTop = chatHistory.scrollHeight;
                    
                    // Arka planda koleksiyon oluşturma isteği gönder
                    const createResponse = await fetch('/api/ensure-collection', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ collection_name: collectionName })
                    });
                    
                    // İşlem başarılı mı kontrol et
                    const createResult = await createResponse.json();
                    console.log("Collection creation result:", createResult);
                    
                    // Eğer koleksiyon zaten varsa (farklı isimle), kullanıcıya hemen bildir
                    if (createResult.status === "exists") {
                        const processingMsg = document.getElementById(processingMsgId);
                        if (processingMsg) {
                            processingMsg.remove();
                        }
                        
                        chatHistory.innerHTML += `<div class="assistant-msg">
                            <p><i class="fas fa-check-circle" style="color: var(--success-green);"></i> Veritabanı hazır! Sorularınızı sorabilirsiniz.</p>
                        </div>`;
                        chatHistory.scrollTop = chatHistory.scrollHeight;
                    }
                    // Eğer işlem başladıysa, durumu periyodik olarak kontrol et
                    else if (createResult.status === "processing") {
                        // 30 saniye sonra tekrar kontrol et
                        setTimeout(() => {
                            fetch(`/api/check-collection/${collectionName}`)
                                .then(res => res.json())
                                .then(checkData => {
                                    if (checkData.exists) {
                                        chatHistory.innerHTML += `<div class="assistant-msg">
                                            <p><i class="fas fa-check-circle" style="color: var(--success-green);"></i> Veritabanı hazır! Artık sorularınızı sorabilirsiniz.</p>
                                        </div>`;
                                        chatHistory.scrollTop = chatHistory.scrollHeight;
                                    }
                                });
                        }, 30000);
                    }
                } else {
                    console.log(`Collection ${collectionName} already exists`);
                    // Koleksiyon zaten varsa, kullanıcıya bildir
                    if (chatHistory.querySelectorAll('.assistant-msg').length <= 1) {
                        chatHistory.innerHTML += `<div class="assistant-msg">
                            <p><i class="fas fa-check-circle" style="color: var(--success-green);"></i> Veritabanı hazır! Sorularınızı sorabilirsiniz.</p>
                        </div>`;
                        chatHistory.scrollTop = chatHistory.scrollHeight;
                    }
                }
            } catch (error) {
                console.error("Error checking/ensuring collection:", error);
            }
        };

        videoPlayer.addEventListener('loadeddata', () => {
            videoLoading.style.display = 'none';
            videoPlayer.style.display = 'block';
            
            // Video yüklendiğinde, şu anki videoyu izlendi olarak işaretle
            const currentVideoPath = videoPlayer.src.split('/').slice(-2).join('/');
            const fullPath = '/' + currentVideoPath;
            markVideoAsWatched(fullPath);
        });

        chatForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const question = questionInput.value.trim();
            if (!question) return;

            // Kullanıcı sorusunu temizle ve ekrana yaz
            questionInput.value = "";
            chatHistory.innerHTML += `<div class="user-msg">${question}</div>`;
            chatHistory.scrollTop = chatHistory.scrollHeight;
            
            // Gelişmiş yükleniyor göstergesi ekle
            const loadingMsgId = `loading-${Date.now()}`;
            chatHistory.innerHTML += `<div id="${loadingMsgId}" class="assistant-msg">
                <div class="chat-loading">
                    <span class="thinking">SterkAgents AI düşünüyor</span>
                    <div class="chat-loading-dots">
                        <div class="chat-loading-dot"></div>
                        <div class="chat-loading-dot"></div>
                        <div class="chat-loading-dot"></div>
                    </div>
                </div>
            </div>`;
            chatHistory.scrollTop = chatHistory.scrollHeight;
            
            try {
                // Timeout ekle (30 saniye)
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 30000);
                
                const res = await fetch("/api/asistana-sor", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ collection_name: currentCollectionName, question: question }),
                    signal: controller.signal
                });
                
                clearTimeout(timeoutId);
                const data = await res.json();
                
                // Yükleniyor mesajını kaldır
                const loadingMsg = document.getElementById(loadingMsgId);
                if (loadingMsg) {
                    loadingMsg.remove();
                }
                
                // Yanıtı ekle
                chatHistory.innerHTML += `<div class="assistant-msg">${data.answer}</div>`;
                chatHistory.scrollTop = chatHistory.scrollHeight;
                
                // Eğer "processing" durumu varsa, kullanıcıya bilgi ver
                if (data.status === "processing") {
                    // 30 saniye sonra koleksiyonu tekrar kontrol et
                    setTimeout(() => {
                        fetch(`/api/check-collection/${currentCollectionName}`)
                            .then(res => res.json())
                            .then(checkData => {
                                if (checkData.exists) {
                                    chatHistory.innerHTML += `<div class="assistant-msg">
                                        <p><i class="fas fa-check-circle" style="color: var(--success-green);"></i> Veritabanı hazır! Artık sorularınızı sorabilirsiniz.</p>
                                    </div>`;
                                    chatHistory.scrollTop = chatHistory.scrollHeight;
                                }
                            });
                    }, 30000);
                }
            } catch (error) {
                // Yükleniyor mesajını kaldır
                const loadingMsg = document.getElementById(loadingMsgId);
                if (loadingMsg) {
                    loadingMsg.remove();
                }
                
                // Hata mesajı göster
                if (error.name === 'AbortError') {
                    chatHistory.innerHTML += `<div class="assistant-msg">
                        <p><i class="fas fa-exclamation-triangle" style="color: var(--error-red);"></i> Yanıt oluşturulurken zaman aşımı oluştu. Lütfen daha kısa bir soru sorun veya daha sonra tekrar deneyin.</p>
                    </div>`;
                } else {
                    chatHistory.innerHTML += `<div class="assistant-msg">
                        <p><i class="fas fa-exclamation-circle" style="color: var(--error-red);"></i> Bir hata oluştu: ${error.message}</p>
                    </div>`;
                }
                chatHistory.scrollTop = chatHistory.scrollHeight;
                console.error("Error asking question:", error);
            }
        });

        // İlk yükleme sırasında ilerleme dairesini güncelle
        updateProgressCircle();
        
        renderModuleList();
        const firstVideo = videoData.series_videos_data[0];
        if (firstVideo) {
            updateVideoPlayer({
                path: firstVideo.video_path,
                collection: videoData.collection_name,
                title: firstVideo.title
            });
        }
    } catch (error) {
        console.error("Initialization error:", error);
    }
});