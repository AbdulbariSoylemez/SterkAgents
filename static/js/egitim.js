document.addEventListener("DOMContentLoaded", async () => {
    try {
        // Initialize assistant widget
        const assistantToggle = document.getElementById('assistant-toggle');
        const assistantClose = document.getElementById('assistant-close');
        const assistantSection = document.getElementById('assistant-section');
        
        if (assistantToggle && assistantClose && assistantSection) {
            // Open assistant when clicking on the toggle button
            assistantToggle.addEventListener('click', () => {
                assistantSection.classList.add('active');
                // Clear notification when opened
                assistantToggle.classList.remove('has-notification');
                // Focus on input field when opened
                const inputField = document.getElementById('user-question');
                if (inputField) setTimeout(() => inputField.focus(), 300);
            });
            
            // Close assistant when clicking on the close button
            assistantClose.addEventListener('click', () => {
                assistantSection.classList.remove('active');
            });
        }
        
        const logo = document.querySelector('.btk-logo');
        if (logo) {
            logo.style.cursor = 'pointer';
            logo.onclick = () => window.location.href = '/';
        }

        const params = new URLSearchParams(window.location.search);
        const videoId = params.get("id");
        if (!videoId) {
            console.error("Video ID not found in URL, redirecting to homepage.");
            window.location.href = '/';
            return;
        }

        const response = await fetch("/api/videolar");
        if (!response.ok) {
            throw new Error(`Failed to fetch video list: ${response.statusText}`);
        }
        const videos = await response.json();
        
        const videoData = videos.find(v => v.id === videoId);
        if (!videoData) {
            console.error(`Video with ID "${videoId}" not found.`);
            window.location.href = '/';
            return;
        }

        console.log("Successfully loaded video data:", videoData);

        const videoPlayer = document.getElementById("video-player");
        const videoLoading = document.getElementById("video-loading");
        const courseTitleEl = document.getElementById("course-title");
        const moduleList = document.getElementById("module-list");
        const chatHistory = document.getElementById("chat-history");
        const chatForm = document.getElementById("chat-form");
        const questionInput = document.getElementById("user-question");
        const submitBtn = chatForm.querySelector("button[type='submit']");

        if (!videoPlayer || !videoLoading || !courseTitleEl || !moduleList || !chatHistory || !chatForm) {
            console.error("One or more essential page elements are missing.");
            return;
        }

        let currentCollectionName = videoData.collection_name;
        let currentVideoPath = videoData.video_url;
        let sohbetGecmisi = [];
        let isWaitingForAssistant = false;
        
        const renderSohbet = () => {
            // If chat history is empty, don't modify the HTML (use the default welcome message)
            if (sohbetGecmisi.length === 0) {
                chatHistory.scrollTop = chatHistory.scrollHeight;
                return;
            }
            
            chatHistory.innerHTML = sohbetGecmisi.map(msg => {
                // Process message text - convert markdown-style formatting
                let processedText = msg.text;
                
                // Convert **bold** to <strong>bold</strong>
                processedText = processedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                
                // Convert *italic* to <em>italic</em>
                processedText = processedText.replace(/\*(.*?)\*/g, '<em>$1</em>');
                
                // Convert newlines to <br/>
                processedText = processedText.replace(/\n/g, '<br/>');
                
                return `<div class="${msg.sender}-msg">
                    ${processedText}
                    ${msg.sender === 'assistant' && !msg.text.includes("Merhaba!") ? 
                        `<button class="copy-btn" title="Kopyala">📋</button>` : ''}
                </div>`;
            }).join("");
            
            chatHistory.scrollTop = chatHistory.scrollHeight;
            
            // Show notification dot on chat icon if there are new messages
            if (sohbetGecmisi.length > 0 && !document.getElementById('assistant-section').classList.contains('active')) {
                document.getElementById('assistant-toggle').classList.add('has-notification');
            }
        };

        const showTyping = (text) => {
            const typingHTML = `<div class="typing-indicator">
                <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
                ${text ? `<span class="typing-text">${text}</span>` : ''}
            </div>`;
            chatHistory.innerHTML += typingHTML;
            chatHistory.scrollTop = chatHistory.scrollHeight;
        };
        
        const removeTyping = () => {
            const typing = chatHistory.querySelector('.typing-indicator');
            if (typing) typing.remove();
        };

        // Check if collection exists, create if needed
        const ensureCollectionExists = async (collectionName) => {
            try {
                // First check if collection already exists
                const checkResponse = await fetch(`/api/check-collection/${collectionName}`);
                const checkResult = await checkResponse.json();
                
                // If collection exists, we're done
                if (checkResult.exists) {
                    console.log(`Collection '${collectionName}' already exists`);
                    return true;
                }
                
                // Otherwise, create it
                console.log(`Collection '${collectionName}' not found, creating it...`);
                showTyping("Eğitim veritabanı hazırlanıyor, lütfen bekleyin...");
                
                const createResponse = await fetch('/api/ensure-collection', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(collectionName)
                });
                
                if (!createResponse.ok) {
                    throw new Error(`Failed to create collection: ${createResponse.statusText}`);
                }
                
                const result = await createResponse.json();
                console.log("Collection creation result:", result);
                
                removeTyping();
                
                if (result.status === 'error') {
                    sohbetGecmisi.push({ 
                        sender: "assistant", 
                        text: `Eğitim veritabanı oluşturulurken bir hata oluştu: ${result.message}. Lütfen daha sonra tekrar deneyin.` 
                    });
                    renderSohbet();
                    return false;
                } else {
                    sohbetGecmisi.push({ 
                        sender: "assistant", 
                        text: `✅ **Eğitim veritabanı hazır!**\n\nBu eğitim kursunun **tüm içeriği** hakkında sorularınızı artık yanıtlayabilirim. Kursun herhangi bir bölümü veya videolar arasındaki ilişkiler hakkında sorular sorabilirsiniz.` 
                    });
                    renderSohbet();
                    return true;
                }
            } catch (error) {
                console.error("Error ensuring collection exists:", error);
                removeTyping();
                sohbetGecmisi.push({ 
                    sender: "assistant", 
                    text: "Eğitim veritabanı hazırlanırken bir hata oluştu. Lütfen daha sonra tekrar deneyin." 
                });
                renderSohbet();
                return false;
            }
        };

        const updateVideoPlayer = async (videoInfo) => {
            console.log("Updating player to:", videoInfo);
            videoLoading.style.display = "block";
            videoPlayer.style.display = "none";
            videoPlayer.src = videoInfo.path;
            videoPlayer.load();

            currentVideoPath = videoInfo.path;
            currentCollectionName = videoInfo.collection;
            
            if (courseTitleEl) {
                courseTitleEl.textContent = videoInfo.title;
            }

            document.querySelectorAll('.section-item').forEach(item => {
                item.classList.remove('current');
                if (item.dataset.videoPath === videoInfo.path) {
                    item.classList.add('current');
                }
            });
            
            // Reset chat history to empty - we'll use the HTML welcome message
            sohbetGecmisi = [];
            
            // When video changes, minimize the assistant
            const assistantSection = document.getElementById('assistant-section');
            if (assistantSection && assistantSection.classList.contains('active')) {
                assistantSection.classList.remove('active');
            }
            
            // Add notification to the chat icon
            document.getElementById('assistant-toggle').classList.add('has-notification');
            
            // Ensure collection exists for this video
            await ensureCollectionExists(currentCollectionName);
        };

                // Function to update completion percentage
                const updateCompletionPercentage = () => {
                    const allVideoItems = document.querySelectorAll('.section-item:not(.header)');
                    const completedItems = document.querySelectorAll('.section-item.completed');
                    const currentItem = document.querySelector('.section-item.current');
                    
                    // Calculate completion percentage
                    let completionPercentage = 0;
                    if (allVideoItems.length > 0) {
                        completionPercentage = Math.floor((completedItems.length / allVideoItems.length) * 100);
                        
                        // If there's a current item, count it as half-completed
                        if (currentItem && !currentItem.classList.contains('completed')) {
                            completionPercentage += Math.floor(50 / allVideoItems.length);
                        }
                    }
                    
                    // Update progress circle
                    const progressCircle = document.getElementById('progress-circle');
                    const progressSpan = progressCircle.querySelector('span');
                    
                    if (progressSpan) {
                        progressSpan.textContent = `${completionPercentage}%`;
                    }
                    
                    // Update circle clip path based on percentage
                    if (completionPercentage > 0) {
                        const degrees = (completionPercentage / 100) * 360;
                        let clipPath;
                        
                        if (degrees <= 180) {
                            // First half of the circle
                            clipPath = `polygon(50% 50%, 50% 0%, ${50 + 50 * Math.sin(degrees * Math.PI / 180)}% ${50 - 50 * Math.cos(degrees * Math.PI / 180)}%)`;
                        } else {
                            // Second half of the circle
                            clipPath = `polygon(50% 50%, 50% 0%, 100% 0%, 100% ${50 - 50 * Math.cos((degrees - 180) * Math.PI / 180)}%, ${50 + 50 * Math.sin((degrees - 180) * Math.PI / 180)}% ${50 - 50 * Math.cos((degrees - 180) * Math.PI / 180)}%)`;
                        }
                        
                        progressCircle.style.setProperty('--clip-path', clipPath);
                        progressCircle.querySelector('::before')?.style.setProperty('clip-path', clipPath);
                        
                        // Apply clip path using a style element since ::before can't be directly accessed
                        let styleEl = document.getElementById('progress-circle-style');
                        if (!styleEl) {
                            styleEl = document.createElement('style');
                            styleEl.id = 'progress-circle-style';
                            document.head.appendChild(styleEl);
                        }
                        styleEl.textContent = `.progress-circle::before { clip-path: ${clipPath}; }`;
                    }
                };
                
                const renderModuleList = () => {
                    // Check if we already have static content in the module list
                    const existingItems = moduleList.querySelectorAll('.section-item');
                    if (existingItems.length > 0) {
                        console.log("Using static content in module list");
                        
                        // Update durations for each video item
                        if (videoData && videoData.is_series && videoData.series_videos_data) {
                            // Update total duration
                            const totalDuration = videoData.total_duration || "0d 0sn";
                            const progressText = document.querySelector('.progress-text');
                            if (progressText) {
                                progressText.textContent = `Toplam Süre: ${totalDuration}`;
                            }
                            
                            // Update header duration
                            const headerItem = document.querySelector('.section-item.header .section-duration');
                            if (headerItem) {
                                headerItem.textContent = totalDuration;
                            }
                            
                            // Update individual video durations
                            existingItems.forEach((item, index) => {
                                if (item.classList.contains('header')) return;
                                
                                const videoIndex = index - 1; // Adjust for header
                                if (videoData.series_videos_data[videoIndex]) {
                                    const video = videoData.series_videos_data[videoIndex];
                                    const durationEl = item.querySelector('.section-duration');
                                    const titleEl = item.querySelector('.section-title');
                                    
                                    // Update duration if available
                                    if (durationEl && video.duration) {
                                        durationEl.textContent = video.duration;
                                    }
                                    
                                    // Update title with original filename
                                    if (titleEl && video.title) {
                                        titleEl.textContent = video.title;
                                    }
                                    
                                    // Store video path in dataset
                                    item.dataset.videoPath = video.video_path;
                                    item.dataset.index = videoIndex;
                                }
                            });
                        }
                        
                        // Add event listeners to the existing items that aren't headers
                        existingItems.forEach((item, index) => {
                            if (item.classList.contains('header')) return;
                            
                            // Get the video path from videoData if available
                            let videoPath = item.dataset.videoPath;
                            if (!videoPath) {
                                if (videoData && videoData.is_series && videoData.series_videos_data && videoData.series_videos_data[index-1]) {
                                    videoPath = videoData.series_videos_data[index-1].video_path;
                                    // Store the video path in the dataset for later use
                                    item.dataset.videoPath = videoPath;
                                } else if (videoData && videoData.video_url) {
                                    videoPath = videoData.video_url;
                                    item.dataset.videoPath = videoPath;
                                }
                            }
                            
                            item.addEventListener('click', () => {
                                // Remove current class from all items
                                existingItems.forEach(i => {
                                    i.classList.remove('current');
                                });
                                
                                // Mark all previous items as completed
                                existingItems.forEach(i => {
                                    if (i === item || i.classList.contains('header')) return;
                                    
                                    const itemIndex = Array.from(existingItems).indexOf(i);
                                    const clickedIndex = Array.from(existingItems).indexOf(item);
                                    
                                    if (itemIndex < clickedIndex) {
                                        i.classList.add('completed');
                                    } else {
                                        i.classList.remove('completed');
                                    }
                                });
                                
                                // Add current class to clicked item
                                item.classList.add('current');
                                
                                // Update title if needed
                                const title = item.querySelector('.section-title').textContent;
                                if (courseTitleEl) {
                                    courseTitleEl.textContent = title;
                                }
                                
                                // Get the video path from the dataset or use the default
                                const videoPath = item.dataset.videoPath || (videoData && videoData.video_url);
                                
                                if (videoPath) {
                                    updateVideoPlayer({
                                        path: videoPath,
                                        collection: videoData.collection_name,
                                        title: title
                                    });
                                }
                                
                                // Update completion percentage
                                updateCompletionPercentage();
                            });
                        });
                        
                        // Set the first non-header item as current by default
                        const firstVideoItem = Array.from(existingItems).find(item => !item.classList.contains('header'));
                        if (firstVideoItem && !document.querySelector('.section-item.current')) {
                            firstVideoItem.classList.add('current');
                        }
                        
                        // Update completion percentage
                        updateCompletionPercentage();
                        
                        return;
                    }
            
            // If no static content exists, generate dynamic content
            moduleList.innerHTML = "";
            let videosToList = [];

            if (videoData.is_series && Array.isArray(videoData.series_videos_data) && videoData.series_videos_data.length > 0) {
                videosToList = [...videoData.series_videos_data].sort((a, b) => a.index - b.index);
                if (courseTitleEl) {
                     courseTitleEl.textContent = videoData.title; // Set main series title
                }
            } else {
                videosToList.push({
                    title: videoData.title,
                    video_path: videoData.video_url,
                    collection_name: videoData.collection_name
                });
            }
            
            console.log(`Rendering ${videosToList.length} videos in the content list.`);
 
            const sectionList = document.createElement("ul");
            sectionList.className = "section-list";

            // First add a header item
            const headerItem = document.createElement("li");
            headerItem.className = "section-item header";
            
            // Use total_duration if available, otherwise calculate from videos
            let totalDuration = videoData.total_duration || "0d 0sn";
            
            // Update the progress text with total duration
            const progressText = document.querySelector('.progress-text');
            if (progressText) {
                progressText.textContent = `Toplam Süre: ${totalDuration}`;
            }
            
            headerItem.innerHTML = `
                <span class="section-title">${videoData.title}</span>
                <span class="section-duration">${totalDuration}</span>
            `;
            sectionList.appendChild(headerItem);
            
            // Then add all videos
            videosToList.forEach((video, index) => {
                const sectionItem = document.createElement("li");
                sectionItem.className = "section-item";
                sectionItem.dataset.videoPath = video.video_path;
                sectionItem.dataset.index = index;
                
                // Use accurate duration from video data and original filename as title
                const duration = video.duration || "~45 dk";
                // Use the original filename as the title without modifications
                const originalTitle = video.title || `Video ${index + 1}`;
                sectionItem.innerHTML = `
                    <span class="section-title">${originalTitle}</span>
                    <span class="section-duration">${duration}</span>
                `;
                
                // Mark as current if it's the current video
                if (video.video_path === currentVideoPath) {
                    sectionItem.classList.add('current');
                    if (courseTitleEl) courseTitleEl.textContent = video.title;
                    
                    // Mark all previous videos as completed
                    videosToList.forEach((v, i) => {
                        if (i < index) {
                            const prevItem = sectionList.querySelector(`[data-index="${i}"]`);
                            if (prevItem) prevItem.classList.add('completed');
                        }
                    });
                }
                // If it's not the current video but comes before the current one, mark as completed
                else if (currentVideoPath) {
                    const currentIndex = videosToList.findIndex(v => v.video_path === currentVideoPath);
                    if (currentIndex > index) {
                        sectionItem.classList.add('completed');
                    }
                }

                sectionItem.addEventListener('click', () => {
                    // Remove current class from all items
                    const allItems = sectionList.querySelectorAll('.section-item:not(.header)');
                    allItems.forEach(item => {
                        item.classList.remove('current');
                    });
                    
                    // Mark all previous items as completed
                    allItems.forEach(item => {
                        const itemIndex = parseInt(item.dataset.index);
                        if (itemIndex < index) {
                            item.classList.add('completed');
                        } else {
                            item.classList.remove('completed');
                        }
                    });
                    
                    // Add current class to this item
                    sectionItem.classList.add('current');
                    
                    updateVideoPlayer({
                        path: video.video_path,
                        collection: video.collection_name,
                        title: video.title
                    });
                    
                    // Update completion percentage
                    updateCompletionPercentage();
                });
                sectionList.appendChild(sectionItem);
            });
            
            // Update completion percentage after creating the list
            setTimeout(updateCompletionPercentage, 100);
            moduleList.appendChild(sectionList);
        };

        videoPlayer.addEventListener('loadeddata', () => {
            videoLoading.style.display = 'none';
            videoPlayer.style.display = 'block';
        });

        chatForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (isWaitingForAssistant) return;
            const question = questionInput.value.trim();
            if (!question) return;

            sohbetGecmisi.push({ sender: "user", text: question });
            renderSohbet();
            questionInput.value = "";

            isWaitingForAssistant = true;
            questionInput.disabled = true;
            submitBtn.disabled = true;
            showTyping("Yanıt hazırlanıyor...");

            try {
                const res = await fetch("/api/asistana-sor", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        collection_name: currentCollectionName,
                        question: question
                    })
                });
                if (!res.ok) {
                    throw new Error(`API error: ${res.statusText}`);
                }
                const data = await res.json();
                sohbetGecmisi.push({ sender: "assistant", text: data.answer });
            } catch (err) {
                console.error("Assistant API error:", err);
                sohbetGecmisi.push({ sender: "assistant", text: "Asistana bağlanırken bir hata oluştu. Lütfen tekrar deneyin." });
            } finally {
                removeTyping();
                renderSohbet();
                isWaitingForAssistant = false;
                questionInput.disabled = false;
                submitBtn.disabled = false;
                questionInput.focus();
            }
        });
        
                 chatHistory.addEventListener('click', (e) => {
             if (e.target.classList.contains('copy-btn')) {
                 // Get the assistant message element
                 const assistantMsg = e.target.closest('.assistant-msg');
                 
                 // Create a temporary div to extract text content without the button
                 const tempDiv = document.createElement('div');
                 tempDiv.innerHTML = assistantMsg.innerHTML;
                 
                 // Remove the copy button from the temporary div
                 const copyBtn = tempDiv.querySelector('.copy-btn');
                 if (copyBtn) {
                     copyBtn.remove();
                 }
                 
                 // Get the clean text content
                 const textToCopy = tempDiv.textContent.trim();
                 
                 // Copy to clipboard
                 navigator.clipboard.writeText(textToCopy);
                 e.target.textContent = '✔';
                 setTimeout(() => { e.target.textContent = '📋'; }, 1500);
             }
         });

        // --- Initial Page Load ---
        renderModuleList();
        
        // Find the current video item or use the first one
        const currentItem = document.querySelector('.section-item.current:not(.header)');
        const firstItem = document.querySelector('.section-item:not(.header)');
        const videoItem = currentItem || firstItem;
        
        if (videoItem) {
            const videoPath = videoItem.dataset.videoPath || currentVideoPath;
            const videoTitle = videoItem.querySelector('.section-title')?.textContent || courseTitleEl.textContent;
            
            if (!currentItem && firstItem) {
                firstItem.classList.add('current');
            }
            
            await updateVideoPlayer({
                path: videoPath,
                collection: currentCollectionName,
                title: videoTitle
            });
        } else {
            // Fallback to default values if no items found
            await updateVideoPlayer({
                path: currentVideoPath,
                collection: currentCollectionName,
                title: courseTitleEl.textContent
            });
        }
        
        // Update completion percentage after everything is loaded
        setTimeout(updateCompletionPercentage, 300);
        
    } catch (error) {
        console.error("An error occurred during page initialization:", error);
        document.body.innerHTML = `<div class="error-message">
            <h3>Sayfa Yüklenemedi</h3>
            <p>Beklenmedik bir hata oluştu. Lütfen ana sayfaya dönüp tekrar deneyin.</p>
            <button onclick="window.location.href='/'">Ana Sayfaya Dön</button>
        </div>`;
    }
});