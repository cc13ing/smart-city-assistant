/** 三栏宽度拖拽调整，尺寸持久化到 localStorage */
const PanelResize = (() => {
  const STORAGE_KEY = "cityintro_panel_sizes";
  const LIMITS = {
    sidebar: { min: 200, max: 420, default: 260 },
    map: { min: 320, max: 900, default: 520 },
    main: { min: 360 },
  };

  let dragging = null;
  let startX = 0;
  let startSidebar = 0;
  let startMap = 0;

  function clampSidebar(v) {
    return Math.round(Math.max(LIMITS.sidebar.min, Math.min(LIMITS.sidebar.max, v)));
  }

  function clampMap(v) {
    const max = Math.min(LIMITS.map.max, Math.floor(window.innerWidth * 0.65));
    return Math.round(Math.max(LIMITS.map.min, Math.min(max, v)));
  }

  function getCurrentSizes() {
    const root = getComputedStyle(document.documentElement);
    return {
      sidebar: parseInt(root.getPropertyValue("--sidebar-w"), 10) || LIMITS.sidebar.default,
      map: parseInt(root.getPropertyValue("--map-panel-w"), 10) || LIMITS.map.default,
    };
  }

  function loadSizes() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      return {
        sidebar: clampSidebar(raw.sidebar || LIMITS.sidebar.default),
        map: clampMap(raw.map || LIMITS.map.default),
      };
    } catch {
      return { sidebar: LIMITS.sidebar.default, map: LIMITS.map.default };
    }
  }

  function saveSizes(sidebar, map) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ sidebar, map }));
  }

  function applySizes(sidebar, map) {
    document.documentElement.style.setProperty("--sidebar-w", `${sidebar}px`);
    document.documentElement.style.setProperty("--map-panel-w", `${map}px`);
  }

  function enforceMainMin() {
    if (!document.body.classList.contains("map-open")) return;
    const { sidebar, map } = getCurrentSizes();
    const handles = 10;
    const available = window.innerWidth - sidebar - map - handles;
    if (available >= LIMITS.main.min) return;

    const deficit = LIMITS.main.min - available;
    const newMap = clampMap(map - deficit);
    if (newMap !== map) {
      applySizes(sidebar, newMap);
      saveSizes(sidebar, newMap);
    }
  }

  function onMove(clientX) {
    if (!dragging) return;
    const dx = clientX - startX;
    const current = getCurrentSizes();

    if (dragging === "sidebar") {
      const next = clampSidebar(startSidebar + dx);
      applySizes(next, current.map);
      saveSizes(next, current.map);
      return;
    }

    if (dragging === "map") {
      const next = clampMap(startMap - dx);
      applySizes(current.sidebar, next);
      saveSizes(current.sidebar, next);
      if (document.body.classList.contains("map-open")) {
        MapRoute.resize?.(document.getElementById("mapPanelContainer"));
      }
    }
  }

  function stopDrag() {
    if (!dragging) return;
    dragging = null;
    document.body.classList.remove("is-resizing");
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", stopDrag);
    document.removeEventListener("touchmove", onTouchMove);
    document.removeEventListener("touchend", stopDrag);
    MapRoute.resize?.(document.getElementById("mapPanelContainer"));
  }

  function onMouseMove(e) {
    e.preventDefault();
    onMove(e.clientX);
  }

  function onTouchMove(e) {
    if (!e.touches.length) return;
    onMove(e.touches[0].clientX);
  }

  function startDrag(kind, clientX) {
    if (window.matchMedia("(max-width: 900px)").matches) return;
    const current = getCurrentSizes();
    dragging = kind;
    startX = clientX;
    startSidebar = current.sidebar;
    startMap = current.map;
    document.body.classList.add("is-resizing");
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", stopDrag);
    document.addEventListener("touchmove", onTouchMove, { passive: false });
    document.addEventListener("touchend", stopDrag);
  }

  function bindHandle(el, kind) {
    if (!el) return;
    el.addEventListener("mousedown", (e) => {
      e.preventDefault();
      startDrag(kind, e.clientX);
    });
    el.addEventListener("touchstart", (e) => {
      if (!e.touches.length) return;
      startDrag(kind, e.touches[0].clientX);
    });
  }

  function init() {
    const saved = loadSizes();
    applySizes(saved.sidebar, saved.map);
    bindHandle(document.getElementById("sidebarResize"), "sidebar");
    bindHandle(document.getElementById("mapResize"), "map");
    window.addEventListener("resize", enforceMainMin);
  }

  return { init, enforceMainMin };
})();
