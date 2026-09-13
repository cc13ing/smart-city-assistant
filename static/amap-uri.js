/** 高德 URI 唤起（Web / App 导航） */
const AmapUri = (() => {
  const MODE_MAP = {
    driving: "car",
    car: "car",
    walking: "walk",
    walk: "walk",
    transit: "bus",
    bus: "bus",
    riding: "ride",
    ride: "ride",
  };

  function pointSegment(lnglat, locationStr, name, fallbackName) {
    let lng;
    let lat;
    if (Array.isArray(lnglat) && lnglat.length >= 2) {
      lng = lnglat[0];
      lat = lnglat[1];
    } else if (locationStr && String(locationStr).includes(",")) {
      const parts = String(locationStr).split(",");
      lng = parseFloat(parts[0]);
      lat = parseFloat(parts[1]);
    }
    if (lng == null || lat == null || Number.isNaN(lng) || Number.isNaN(lat)) return null;
    const label = encodeURIComponent((name || fallbackName || "").trim() || fallbackName);
    return `${lng},${lat},${label}`;
  }

  /**
   * 构建导航 URI：含起点、终点、出行方式，并尝试唤起高德 App。
   * @param {object} routeData - route_map / parse_route_result 结构
   */
  function buildNavigation(routeData) {
    if (!routeData?.destination) return null;
    return buildNavigationUri(
      routeData.origin || {},
      routeData.destination,
      routeData.mode || routeData.mode_label || "driving"
    );
  }

  /**
   * 根据起终点与出行方式构建高德导航 URI。
   * @param {object} origin - { lnglat?, location?, name? }
   * @param {object} destination - { lnglat?, location?, name? }
   * @param {string} mode - driving/walking/transit/...
   */
  function buildNavigationUri(origin, destination, mode = "driving") {
    if (!destination) return null;
    const navMode = MODE_MAP[mode] || "car";
    const toSeg = pointSegment(
      destination.lnglat,
      destination.location,
      destination.name,
      "终点"
    );
    if (!toSeg) return null;

    const params = [
      `to=${toSeg}`,
      `mode=${navMode}`,
      "coordinate=gaode",
      "callnative=1",
      "src=AutoCityIntro",
    ];

    const fromSeg = pointSegment(
      origin?.lnglat,
      origin?.location,
      origin?.name,
      "起点"
    );
    if (fromSeg) params.unshift(`from=${fromSeg}`);

    if (navMode === "car") params.push("policy=0");
    if (navMode === "bus") params.push("policy=0");

    return `https://uri.amap.com/navigation?${params.join("&")}`;
  }

  function openInAmap(uri) {
    if (!uri) return;
    const link = document.createElement("a");
    link.href = uri;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  return { buildNavigation, buildNavigationUri, openInAmap, MODE_MAP };
})();
