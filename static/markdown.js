/** 轻量 Markdown 渲染（助手回复） */
const Markdown = (() => {
  function escapeHtml(s) {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function render(text) {
    if (!text) return "";
    let html = escapeHtml(text);
    html = html.replace(/^### (.+)$/gm, "<h4>$1</h4>");
    html = html.replace(/^## (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^# (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/^\s*[-*]\s+(.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`);
    html = html.replace(/\n{2,}/g, "</p><p>");
    html = html.replace(/\n/g, "<br>");
    return `<div class="md-body"><p>${html}</p></div>`;
  }

  function setContent(el, text, streaming = false) {
    if (!el) return;
    el.innerHTML = render(text);
    if (streaming) {
      el.classList.add("is-streaming");
      if (!el.querySelector(".stream-cursor")) {
        const c = document.createElement("span");
        c.className = "stream-cursor";
        el.appendChild(c);
      }
    } else {
      el.classList.remove("is-streaming");
      el.querySelector(".stream-cursor")?.remove();
    }
  }

  function toSpeechText(text) {
    if (!text) return "";
    let s = String(text);

    // 代码块 / 行内代码
    s = s.replace(/```[\s\S]*?```/g, " ");
    s = s.replace(/`([^`]+)`/g, "$1");

    // 标题（保留文字，去掉 #）
    s = s.replace(/^#{1,6}\s+/gm, "");

    // 引用、列表
    s = s.replace(/^>\s?/gm, "");
    s = s.replace(/^\s*[-*+]\s+/gm, "");
    s = s.replace(/^\s*\d+[.)．、]\s+/gm, "");

    // 强调 / 删除线
    s = s.replace(/\*\*(.+?)\*\*/g, "$1");
    s = s.replace(/\*(.+?)\*/g, "$1");
    s = s.replace(/__(.+?)__/g, "$1");
    s = s.replace(/~~(.+?)~~/g, "$1");

    // 链接与图片
    s = s.replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1");
    s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");

    // 分隔线、表格符号
    s = s.replace(/^-{3,}\s*$/gm, " ");
    s = s.replace(/^\*{3,}\s*$/gm, " ");
    s = s.replace(/^\|?[\s:|-]+\|?\s*$/gm, " ");
    s = s.replace(/\|/g, "，");

    // 常见 Markdown / 装饰符号
    s = s.replace(/[#*_~`>|]/g, " ");
    s = s.replace(/\\([\\`*_{}[\]()#+.!-])/g, "$1");

    // 标点与 emoji（保留中文标点）
    s = s.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, " ");
    s = s.replace(/→/g, "到");
    s = s.replace(/·/g, "，");
    s = s.replace(/…/g, "。");

    // 空白归一
    s = s.replace(/[^\S\n]+/g, " ");
    s = s.replace(/\n+/g, "，");
    s = s.replace(/\s{2,}/g, " ");
    s = s.replace(/[，,。．；;：:\s]{2,}/g, "，");

    return s.trim().slice(0, 800);
  }

  return { render, setContent, toSpeechText };
})();
