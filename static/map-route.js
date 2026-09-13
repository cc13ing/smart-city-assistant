/** 高德地图路线展示 */
const MapRoute = (() => {
  let amapKey = null;
  let scriptLoading = null;
  const mapInstances = new WeakMap();

  async function getKey() {
    if (amapKey) return amapKey;
    const res = await fetch("/api/config/map");
    const data = await res.json();
    amapKey = data.amap_key || "";
    if (!amapKey) throw new Error("未配置高德地图 Key");
    return amapKey;
  }

  function loadScript(key) {
    if (window.AMap) return Promise.resolve();
    if (scriptLoading) return scriptLoading;
    scriptLoading = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}&plugin=AMap.TileLayer.Traffic`;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("高德地图脚本加载失败"));
      document.head.appendChild(s);
    });
    return scriptLoading;
  }

  function markerLabel(text, kind) {
    return {
      content: `<div class="map-pin-label map-pin-${kind}">${text}</div>`,
      direction: "top",
      offset: new AMap.Pixel(0, -4),
    };
  }

  function addLabeledMarker(map, lnglat, title, labelText, kind, onClick) {
    const opts = {
      position: new AMap.LngLat(lnglat[0], lnglat[1]),
      map,
      title,
      zIndex: kind === "start" ? 120 : kind === "end" ? 110 : 100,
    };
    if (labelText) opts.label = markerLabel(labelText, kind);
    const marker = new AMap.Marker(opts);
    if (onClick) marker.on("click", onClick);
    return marker;
  }

  function render(container, routeData) {
    if (!routeData || !routeData.path || routeData.path.length < 2) {
      container.innerHTML = '<p class="map-error">路线数据不足，无法绘制地图</p>';
      return;
    }

    if (routeData.path_fallback) {
      container.innerHTML = '<p class="map-error">路线详情不足，请重试或更换出行方式</p>';
      return;
    }

    const origin = routeData.origin?.lnglat || routeData.path[0];
    const dest =
      routeData.destination?.lnglat || routeData.path[routeData.path.length - 1];
    const path = routeData.path.map(([lng, lat]) => new AMap.LngLat(lng, lat));
    const isTrip = routeData.trip_type === "halfday" || (routeData.stops || []).length > 0;

    const map = new AMap.Map(container, {
      zoom: 13,
      center: path[Math.floor(path.length / 2)],
      viewMode: "2D",
    });

    const polyline = new AMap.Polyline({
      path,
      strokeColor: isTrip ? "#22c55e" : "#3b82f6",
      strokeWeight: isTrip ? 5 : 6,
      strokeOpacity: 0.92,
      lineJoin: "round",
      showDir: true,
    });
    map.add(polyline);

    const overlays = [polyline];

    overlays.push(
      addLabeledMarker(
        map,
        origin,
        (routeData.origin?.name || "起点") + "（起点）",
        "起点",
        "start"
      )
    );
    overlays.push(
      addLabeledMarker(
        map,
        dest,
        (routeData.destination?.name || "终点") + "（终点）",
        "终点",
        "end"
      )
    );

    (routeData.stops || []).forEach((stop) => {
      if (!stop.lnglat || stop.lnglat.length < 2) return;
      const label = stop.order ? `${stop.order}` : "·";
      overlays.push(
        addLabeledMarker(map, stop.lnglat, stop.name || `途经点${label}`, label, "stop")
      );
    });

    map.on("complete", () => {
      map.setFitView(overlays, false, [56, 56, 56, 56]);
    });
    mapInstances.set(container, map);
    setTimeout(() => map.resize(), 200);
  }

  function renderPoi(container, poiData, options = {}) {
    const onPoiClick = options.onPoiClick;
    const center = poiData.center?.lnglat;
    const pois = poiData.pois || [];
    if (!center || pois.length === 0) {
      container.innerHTML = '<p class="map-error">景点数据不足，无法绘制地图</p>';
      return;
    }

    const isCityScope = poiData.scope === "city";
    const map = new AMap.Map(container, {
      zoom: isCityScope ? 11 : 14,
      center: new AMap.LngLat(center[0], center[1]),
      viewMode: "2D",
    });

    const overlays = [];
    if (!isCityScope) {
      overlays.push(
        addLabeledMarker(
          map,
          center,
          poiData.center?.name || "当前位置",
          "起点",
          "start"
        )
      );
    }

    pois.forEach((p, i) => {
      if (!p.lnglat || p.lnglat.length < 2) return;
      const cat = p.category || "";
      let kind = "stop";
      let label = String(i + 1);
      if (cat === "food") {
        kind = "food";
        label = "食";
      } else if (cat === "sight") {
        kind = "sight";
        label = "景";
      } else if (i === pois.length - 1 && pois.length > 1) {
        kind = "end";
      }
      const m = addLabeledMarker(
        map,
        p.lnglat,
        `${p.display_name || p.name || "地点"}${cat === "food" ? "（美食）" : cat === "sight" ? "（景点）" : ""}`,
        label,
        kind,
        onPoiClick ? () => onPoiClick(p) : null
      );
      overlays.push(m);
    });

    map.on("complete", () => {
      map.setFitView(overlays, false, [48, 48, 48, 48]);
    });
    mapInstances.set(container, map);
    setTimeout(() => map.resize(), 200);
  }

  async function show(container, routeData) {
    container.innerHTML = '<p class="map-loading">正在加载地图...</p>';
    try {
      const key = await getKey();
      await loadScript(key);
      container.innerHTML = "";
      render(container, routeData);
    } catch (e) {
      container.innerHTML = `<p class="map-error">地图加载失败: ${e.message}</p>`;
    }
  }

  async function showPoi(container, poiData, options) {
    container.innerHTML = '<p class="map-loading">正在加载地图...</p>';
    try {
      const key = await getKey();
      await loadScript(key);
      container.innerHTML = "";
      renderPoi(container, poiData, options);
    } catch (e) {
      container.innerHTML = `<p class="map-error">地图加载失败: ${e.message}</p>`;
    }
  }

  function renderTraffic(container, trafficData) {
    const center = trafficData.center?.lnglat;
    if (!center || center.length < 2) {
      container.innerHTML = '<p class="map-error">路况数据不足，无法展示地图</p>';
      return;
    }
    const radius = Number(trafficData.radius) || 1500;
    const map = new AMap.Map(container, {
      zoom: 14,
      center: new AMap.LngLat(center[0], center[1]),
      viewMode: "2D",
    });
    const overlays = [];
    if (AMap.TileLayer && AMap.TileLayer.Traffic) {
      map.add(new AMap.TileLayer.Traffic({ zIndex: 10, autoRefresh: true }));
    }
    const circle = new AMap.Circle({
      center: new AMap.LngLat(center[0], center[1]),
      radius,
      strokeColor: "#f59e0b",
      strokeWeight: 2,
      strokeOpacity: 0.85,
      fillColor: "#f59e0b",
      fillOpacity: 0.08,
    });
    map.add(circle);
    overlays.push(circle);
    overlays.push(
      addLabeledMarker(
        map,
        center,
        trafficData.center?.name || "当前位置",
        "查询点",
        "start"
      )
    );
    map.on("complete", () => {
      map.setFitView(overlays, false, [56, 56, 56, 56]);
    });
    mapInstances.set(container, map);
    setTimeout(() => map.resize(), 200);
  }

  async function showTraffic(container, trafficData) {
    container.innerHTML = '<p class="map-loading">正在加载路况地图...</p>';
    try {
      const key = await getKey();
      await loadScript(key);
      container.innerHTML = "";
      renderTraffic(container, trafficData);
    } catch (e) {
      container.innerHTML = `<p class="map-error">地图加载失败: ${e.message}</p>`;
    }
  }

  function resize(container) {
    const map = mapInstances.get(container);
    if (map) map.resize();
  }

  return { show, showPoi, showTraffic, resize };
})();
