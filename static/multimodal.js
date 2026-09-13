/** 多模态：图片上传与摄像头拍照 */
const Multimodal = (() => {
  let previewUrl = null;

  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result;
        if (typeof result === "string") {
          const base64 = result.split(",")[1] || result;
          resolve(base64);
        } else reject(new Error("读取失败"));
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  async function captureFromCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("浏览器不支持摄像头");
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
    });
    return new Promise((resolve, reject) => {
      const video = document.createElement("video");
      video.srcObject = stream;
      video.playsInline = true;
      video.onloadedmetadata = async () => {
        await video.play();
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(video, 0, 0);
        stream.getTracks().forEach((t) => t.stop());
        const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
        resolve(dataUrl.split(",")[1]);
      };
      video.onerror = () => {
        stream.getTracks().forEach((t) => t.stop());
        reject(new Error("摄像头启动失败"));
      };
    });
  }

  async function analyzeImage(base64, location, sessionId, deviceId) {
    const res = await fetch("/api/analyze_image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image_base64: base64,
        location: location || "",
        session_id: sessionId,
        device_id: deviceId,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async function generateImage(prompt, sessionId, deviceId) {
    const res = await fetch("/api/generate_image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        session_id: sessionId,
        device_id: deviceId,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  function createImagePreview(base64, alt) {
    const wrap = document.createElement("div");
    wrap.className = "message-image-wrap";
    const img = document.createElement("img");
    img.className = "message-image";
    img.src = `data:image/jpeg;base64,${base64}`;
    img.alt = alt || "上传图片";
    wrap.appendChild(img);
    return wrap;
  }

  function createGeneratedImage(url, alt) {
    const wrap = document.createElement("div");
    wrap.className = "message-image-wrap";
    const img = document.createElement("img");
    img.className = "message-image";
    img.src = url;
    img.alt = alt || "生成图片";
    const dl = document.createElement("a");
    dl.href = url;
    dl.download = "city-intro.png";
    dl.className = "btn-text image-download";
    dl.textContent = "下载图片";
    wrap.appendChild(img);
    wrap.appendChild(dl);
    return wrap;
  }

  return {
    readFileAsBase64,
    captureFromCamera,
    analyzeImage,
    generateImage,
    createImagePreview,
    createGeneratedImage,
  };
})();
