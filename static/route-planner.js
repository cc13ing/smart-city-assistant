/** 路线导航：定位 → 填目的地 → 选方式 → 唤起高德 App */
const RoutePlanner = (() => {
  const overlay = () => document.getElementById("routePlannerOverlay");
  const originEl = () => document.getElementById("routePlannerOrigin");
  const destInput = () => document.getElementById("routePlannerDest");
  const errorEl = () => document.getElementById("routePlannerError");
  const goBtn = () => document.getElementById("routePlannerGo");

  let state = {
    location: "",
    label: "",
    city: "",
    mode: "driving",
  };

  function setError(msg) {
    const el = errorEl();
    if (!el) return;
    if (msg) {
      el.textContent = msg;
      el.classList.remove("hidden");
    } else {
      el.textContent = "";
      el.classList.add("hidden");
    }
  }

  function setMode(mode) {
    state.mode = mode;
    document.querySelectorAll(".route-mode-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === mode);
    });
  }

  function close() {
    overlay()?.classList.remove("open");
    setError("");
  }

  function open(loc) {
    state = {
      location: loc.location,
      label: loc.label || loc.location,
      city: loc.city || "",
      mode: "driving",
    };
    if (originEl()) originEl().textContent = state.label;
    if (destInput()) destInput().value = "";
    setMode("driving");
    setError("");
    overlay()?.classList.add("open");
    destInput()?.focus();
  }

  function parseOrigin() {
    const parts = String(state.location).split(",");
    if (parts.length < 2) return null;
    const lng = parseFloat(parts[0]);
    const lat = parseFloat(parts[1]);
    if (Number.isNaN(lng) || Number.isNaN(lat)) return null;
    return {
      name: state.label || "起点",
      location: state.location,
      lnglat: [lng, lat],
    };
  }

  async function navigate() {
    const keywords = destInput()?.value?.trim();
    if (!keywords) {
      setError("请输入要去的目的地");
      return;
    }
    if (!state.location) {
      setError("请先完成定位");
      return;
    }

    const origin = parseOrigin();
    if (!origin) {
      setError("起点坐标无效，请重新定位");
      return;
    }

    setError("");
    const btn = goBtn();
    if (btn) {
      btn.disabled = true;
      btn.textContent = "正在解析目的地...";
    }

    try {
      const params = new URLSearchParams({ keywords });
      if (state.city) params.set("city", state.city);
      if (state.location) params.set("near", state.location);
      const res = await fetch(`/api/location/geocode?${params}`);
      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail;
        const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? detail[0]?.msg : "";
        setError(msg || data.error || "未找到该地点");
        return;
      }

      const uri =
        typeof AmapUri !== "undefined"
          ? AmapUri.buildNavigationUri(origin, data, state.mode)
          : null;
      if (!uri) {
        setError("无法生成导航链接");
        return;
      }

      close();
      AmapUri.openInAmap(uri);
    } catch (e) {
      setError("网络错误，请稍后重试");
      console.error(e);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "在高德 App 中导航";
      }
    }
  }

  function bindEvents() {
    document.getElementById("routePlannerClose")?.addEventListener("click", close);
    overlay()?.addEventListener("click", (e) => {
      if (e.target === overlay()) close();
    });
    document.querySelector(".route-planner")?.addEventListener("click", (e) => e.stopPropagation());
    goBtn()?.addEventListener("click", navigate);
    destInput()?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        navigate();
      }
    });
    document.querySelectorAll(".route-mode-tab").forEach((btn) => {
      btn.addEventListener("click", () => setMode(btn.dataset.mode || "driving"));
    });
  }

  bindEvents();

  return { open, close };
})();
