/** 右侧地图面板 / 移动端 Bottom Sheet */
const MapPanel = (() => {
  let mapContainer, titleEl, metaEl, actionsEl;
  let sheetEl, sheetContainer, sheetTitleEl, sheetMetaEl, overlayEl, panelEl;
  let currentRoute = null;
  let currentPoi = null;
  let currentTraffic = null;

  function init() {
    panelEl = document.getElementById("mapPanel");
    mapContainer = document.getElementById("mapPanelContainer");
    titleEl = document.getElementById("mapPanelTitle");
    metaEl = document.getElementById("mapPanelMeta");
    actionsEl = document.getElementById("mapPanelActions");
    sheetEl = document.getElementById("mapSheet");
    sheetContainer = document.getElementById("mapSheetContainer");
    sheetTitleEl = document.getElementById("mapSheetTitle");
    sheetMetaEl = document.getElementById("mapSheetMeta");
    overlayEl = document.getElementById("mapOverlay");

    setIcon(document.getElementById("mapCloseIcon"), "x");
    setIcon(document.querySelector("#mapSheetClose .icon"), "x");

    document.getElementById("mapPanelClose")?.addEventListener("click", hide);
    document.getElementById("mapSheetClose")?.addEventListener("click", hide);
    overlayEl?.addEventListener("click", hide);
    document.getElementById("toggleMapBtn")?.addEventListener("click", toggle);
  }

  function isOpen() {
    if (isMobile()) return !!sheetEl?.classList.contains("open");
    return document.body.classList.contains("map-open");
  }

  function updateToggleBtn() {
    const btn = document.getElementById("toggleMapBtn");
    if (!btn) return;
    btn.classList.toggle("active", isOpen());
    btn.setAttribute("aria-pressed", isOpen() ? "true" : "false");
  }

  function restoreFromSummaryCards() {
    const cards = document.querySelectorAll("#messages .summary-card");
    for (let i = cards.length - 1; i >= 0; i--) {
      const payload = cards[i]._mapData;
      if (!payload?.data) continue;
      if (payload.type === "route") {
        showRoute(payload.data);
        return true;
      }
      if (payload.type === "traffic") {
        showTraffic(payload.data);
        return true;
      }
      if (payload.type === "poi") {
        showPoi(payload.data);
        return true;
      }
    }
    return false;
  }

  function showEmpty() {
    setTitles("地图", "提问路线、周边或路况后将在此展示");
    if (actionsEl) actionsEl.innerHTML = "";
    const container = activeContainer();
    if (container) {
      container.innerHTML =
        '<p class="map-loading">暂无地图数据<br><span style="font-size:0.85em;opacity:0.75">试试「附近有什么咖啡店」或对话中问路线</span></p>';
    }
    openPanel();
  }

  function reopenCached() {
    if (currentRoute) showRoute(currentRoute);
    else if (currentTraffic) showTraffic(currentTraffic);
    else if (currentPoi) showPoi(currentPoi);
  }

  function toggle() {
    if (isOpen()) {
      hide();
      return;
    }
    if (hasContent()) {
      reopenCached();
      return;
    }
    if (restoreFromSummaryCards()) return;
    showEmpty();
  }

  function isMobile() {
    return window.matchMedia("(max-width: 900px)").matches;
  }

  function activeContainer() {
    return isMobile() ? sheetContainer : mapContainer;
  }

  function setTitles(title, meta) {
    if (titleEl) titleEl.textContent = title;
    if (metaEl) metaEl.textContent = meta;
    if (sheetTitleEl) sheetTitleEl.textContent = title;
    if (sheetMetaEl) sheetMetaEl.textContent = meta;
  }

  function renderRouteActions(routeData) {
    if (!actionsEl || !routeData?.destination) return;
    actionsEl.innerHTML = "";
    const uri =
      routeData.amap_navi_uri ||
      (typeof AmapUri !== "undefined" ? AmapUri.buildNavigation(routeData) : null);

    const originName = routeData.origin?.name || "起点";
    const destName = routeData.destination?.name || "终点";
    const modeLabel = routeData.mode_label || routeData.mode || "驾车";

    const hint = document.createElement("p");
    hint.className = "map-action-hint";
    hint.textContent = `${modeLabel}：${originName} → ${destName}`;

    const row = document.createElement("div");
    row.className = "map-action-row";

    if (uri) {
      const link = document.createElement("a");
      link.className = "btn-ghost primary";
      link.href = uri;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "在高德 App 中导航";
      row.appendChild(link);
    }

    const dest = routeData.destination;
    const lnglat = dest.lnglat || (dest.location || "").split(",").map(parseFloat);
    if (lnglat?.length >= 2 && !Number.isNaN(lnglat[0])) {
      const taxi = document.createElement("button");
      taxi.type = "button";
      taxi.className = "btn-ghost";
      taxi.textContent = "在高德叫车";
      taxi.onclick = () => openTaxi(lnglat[0], lnglat[1], destName);
      row.appendChild(taxi);
    }

    actionsEl.appendChild(hint);
    actionsEl.appendChild(row);
  }

  async function openTaxi(lng, lat, name) {
    try {
      const params = new URLSearchParams({ lon: lng, lat, name: name || "目的地" });
      const res = await fetch(`/api/taxi/uri?${params}`);
      const data = await res.json();
      if (res.ok && data.uri) AmapUri.openInAmap(data.uri);
      else alert("无法生成叫车链接");
    } catch {
      alert("叫车链接生成失败");
    }
  }

  function renderPoiActions(poiData) {
    if (!actionsEl || !poiData?.pois?.length) return;
    actionsEl.innerHTML = "";
    if (poiData.offline) {
      const offline = document.createElement("p");
      offline.className = "map-action-hint offline-badge";
      offline.textContent = "当前为离线缓存数据";
      actionsEl.appendChild(offline);
    }
    poiData.pois.slice(0, 6).forEach((p) => {
      const row = document.createElement("div");
      row.className = "map-poi-action-row";
      const label = document.createElement("span");
      label.className = "map-poi-action-name map-poi-action-link";
      label.textContent = p.name || "地点";
      label.title = "查看详情";
      label.onclick = () => openPoiDetail(p, poiData);
      const detailBtn = document.createElement("button");
      detailBtn.type = "button";
      detailBtn.className = "btn-ghost";
      detailBtn.textContent = "详情";
      detailBtn.onclick = () => openPoiDetail(p, poiData);
      row.appendChild(label);
      row.appendChild(detailBtn);
      if (p.lnglat?.length >= 2) {
        const taxiBtn = document.createElement("button");
        taxiBtn.type = "button";
        taxiBtn.className = "btn-ghost";
        taxiBtn.textContent = "叫车";
        taxiBtn.onclick = () => openTaxi(p.lnglat[0], p.lnglat[1], p.name);
        row.appendChild(taxiBtn);
      }
      actionsEl.appendChild(row);
    });
  }

  function openPanel() {
    if (isMobile()) {
      sheetEl?.classList.add("open");
      overlayEl?.classList.add("open");
    } else {
      panelEl?.classList.add("is-visible");
      document.body.classList.add("map-open");
      PanelResize.enforceMainMin?.();
    }
    updateToggleBtn();
    setTimeout(() => MapRoute.resize?.(activeContainer()), 350);
  }

  function showRoute(routeData) {
    if (!routeData) return;
    currentRoute = routeData;
    currentPoi = null;
    currentTraffic = null;
    const mode = routeData.mode_label || routeData.mode || "路线";
    const from = routeData.origin?.name || "起点";
    const to = routeData.destination?.name || "终点";
    setTitles(
      routeData.trip_type === "halfday" ? "半日游路线" : `${mode}导航`,
      routeData.trip_type === "halfday"
        ? routeData.summary || `${from} → ${to}`
        : `${from} → ${to}${routeData.duration_text ? " · " + routeData.duration_text : ""}`
    );
    renderRouteActions(routeData);
    MapRoute.show(activeContainer(), routeData);
    openPanel();
  }

  function poiMeta(poiData) {
    const foodN = poiData?.food_count;
    const sightN = poiData?.sight_count;
    if (foodN != null && sightN != null) {
      return `美食 ${foodN} · 景点 ${sightN}`;
    }
    return `共 ${(poiData?.pois || []).length} 个地点`;
  }

  function showPoi(poiData) {
    if (!poiData) return;
    currentPoi = poiData;
    currentRoute = null;
    currentTraffic = null;
    setTitles(poiData.title || "地点推荐", poiMeta(poiData));
    renderPoiActions(poiData);
    MapRoute.showPoi(activeContainer(), poiData, {
      onPoiClick: (poi) => openPoiDetail(poi, poiData),
    });
    openPanel();
  }

  function showTraffic(trafficData) {
    if (!trafficData) return;
    currentTraffic = trafficData;
    currentRoute = null;
    currentPoi = null;
    const status = trafficData.status || "实时路况";
    const radius = trafficData.radius || 1500;
    let meta = `${status} · 半径 ${radius}米 · 畅通 ${trafficData.expedite ?? "?"}%`;
    if (trafficData.coverage_limited) {
      meta = `${trafficData.local_area || "当前区域"} · 地图路况图层 · 半径 ${radius}米`;
      if (trafficData.reference_city) {
        meta += ` · 参考${trafficData.reference_city}`;
      }
    }
    setTitles(trafficData.title || "周边实时路况", meta);
    if (actionsEl) actionsEl.innerHTML = "";
    MapRoute.showTraffic(activeContainer(), trafficData);
    openPanel();
  }

  function hide() {
    panelEl?.classList.remove("is-visible");
    sheetEl?.classList.remove("open");
    overlayEl?.classList.remove("open");
    document.body.classList.remove("map-open");
    updateToggleBtn();
  }

  function clear() {
    currentRoute = null;
    currentPoi = null;
    currentTraffic = null;
    hide();
    if (mapContainer) mapContainer.innerHTML = "";
    if (sheetContainer) sheetContainer.innerHTML = "";
    if (actionsEl) actionsEl.innerHTML = "";
    if (titleEl) titleEl.textContent = "地图";
    if (metaEl) metaEl.textContent = "";
    if (sheetTitleEl) sheetTitleEl.textContent = "地图";
    if (sheetMetaEl) sheetMetaEl.textContent = "";
  }

  function prepareNewTurn() {
    clear();
  }

  function hasContent() {
    return !!(currentRoute || currentPoi || currentTraffic);
  }

  return {
    init,
    showRoute,
    showPoi,
    showTraffic,
    hide,
    clear,
    prepareNewTurn,
    hasContent,
    toggle,
    isOpen,
  };
})();
