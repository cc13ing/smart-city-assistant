/** 行程分享弹窗 */
const SharePanel = (() => {
  const overlay = () => document.getElementById("shareOverlay");
  const urlEl = () => document.getElementById("shareUrlInput");
  const qrEl = () => document.getElementById("shareQrImg");

  function close() {
    overlay()?.classList.remove("open");
  }

  async function shareTrip(trip) {
    if (!trip) return;
    try {
      const res = await fetch("/api/export/share", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, trip }),
      });
      if (!res.ok) throw new Error("分享失败");
      const data = await res.json();
      const pageUrl = data.page_url || data.url;
      if (urlEl()) urlEl().value = pageUrl;
      if (qrEl()) {
        qrEl().src = `https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(pageUrl)}`;
        qrEl().alt = "分享二维码";
      }
      overlay()?.classList.add("open");
    } catch (e) {
      alert(e.message || "分享失败");
    }
  }

  function bind() {
    document.getElementById("shareCloseBtn")?.addEventListener("click", close);
    overlay()?.addEventListener("click", (e) => {
      if (e.target === overlay()) close();
    });
    document.getElementById("shareCopyBtn")?.addEventListener("click", async () => {
      const url = urlEl()?.value;
      if (!url) return;
      try {
        await navigator.clipboard.writeText(url);
        alert("链接已复制");
      } catch {
        urlEl()?.select();
        document.execCommand("copy");
        alert("链接已复制");
      }
    });
  }

  bind();
  return { shareTrip, close };
})();
