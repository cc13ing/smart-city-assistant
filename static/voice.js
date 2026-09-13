/** Web Speech API 语音识别与合成 */
const Voice = (() => {
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let listening = false;
  let onResultCallback = null;
  let onEndCallback = null;

  function isSupported() {
    return !!(SpeechRecognition && window.speechSynthesis);
  }

  function initRecognition() {
    if (!SpeechRecognition) return null;
    if (recognition) return recognition;
    recognition = new SpeechRecognition();
    recognition.lang = "zh-CN";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      let interim = "";
      let final = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) final += t;
        else interim += t;
      }
      if (onResultCallback) onResultCallback(final || interim, !!final);
    };
    recognition.onend = () => {
      listening = false;
      if (onEndCallback) onEndCallback();
    };
    recognition.onerror = (e) => {
      listening = false;
      if (onEndCallback) onEndCallback(e.error);
    };
    return recognition;
  }

  function startListening(onResult, onEnd) {
    const rec = initRecognition();
    if (!rec) {
      if (onEnd) onEnd("unsupported");
      return false;
    }
    if (listening) {
      rec.stop();
      return false;
    }
    onResultCallback = onResult;
    onEndCallback = onEnd;
    listening = true;
    try {
      rec.start();
      return true;
    } catch (e) {
      listening = false;
      if (onEnd) onEnd(e.message);
      return false;
    }
  }

  function stopListening() {
    if (recognition && listening) recognition.stop();
    listening = false;
  }

  function isListening() {
    return listening;
  }

  function prepareSpeechText(text) {
    if (typeof Markdown !== "undefined" && Markdown.toSpeechText) {
      return Markdown.toSpeechText(text);
    }
    return String(text || "")
      .replace(/[#*_~`>|]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 800);
  }

  function speak(text, onEnd) {
    if (!text || !window.speechSynthesis) return;
    const plain = prepareSpeechText(text);
    if (!plain) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(plain);
    utter.lang = "zh-CN";
    utter.rate = 1.0;
    if (onEnd) utter.onend = onEnd;
    window.speechSynthesis.speak(utter);
  }

  let currentAudio = null;

  async function speakWithBackend(text, onEnd) {
    const plain = prepareSpeechText(text);
    if (!plain) return false;
    stopSpeaking();
    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: plain }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.url) {
          currentAudio = new Audio(data.url);
          if (onEnd) currentAudio.onended = onEnd;
          await currentAudio.play();
          return true;
        }
      }
    } catch (_) {}
    speak(text, onEnd);
    return false;
  }

  function stopSpeaking() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }

  return {
    isSupported,
    startListening,
    stopListening,
    isListening,
    speak,
    speakWithBackend,
    stopSpeaking,
  };
})();
