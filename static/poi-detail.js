/** POI 详情弹窗：营业/门票/攻略 + 高德导航/叫车/收藏 */

const PoiDetail = (() => {

  const overlay = () => document.getElementById("poiDetailOverlay");

  const bodyEl = () => document.getElementById("poiDetailBody");



  function close() {

    overlay()?.classList.remove("open");

  }



  function stripStationPrefix(name) {
    return String(name || "").replace(/^第\d+站\s*/, "").trim();
  }

  function parseOpts(keywordsOrOpts, city = "") {

    if (typeof keywordsOrOpts === "object" && keywordsOrOpts) {

      const rawName = keywordsOrOpts.display_name || keywordsOrOpts.name || keywordsOrOpts.keywords || "";

      const keywords = stripStationPrefix(rawName) || rawName;

      return {

        keywords,

        displayName: stripStationPrefix(keywordsOrOpts.display_name || "") || keywords,

        city: keywordsOrOpts.city || city,

        poiId: keywordsOrOpts.poiId || keywordsOrOpts.poi_id || keywordsOrOpts.id || "",

        presetLnglat: keywordsOrOpts.lnglat,

        presetLocation: keywordsOrOpts.location,

      };

    }

    const keywords = stripStationPrefix(keywordsOrOpts) || keywordsOrOpts;

    return {
      keywords,
      displayName: keywords,
      city,
      poiId: "",
      presetLnglat: null,
      presetLocation: "",
    };

  }

  function resolveNavCoords(poi, preset) {
    if (preset?.presetLnglat?.length >= 2) {
      const [lng, lat] = preset.presetLnglat;
      if (!Number.isNaN(lng) && !Number.isNaN(lat)) {
        return {
          lng,
          lat,
          loc: preset.presetLocation || `${lng},${lat}`,
        };
      }
    }
    if (preset?.presetLocation?.includes(",")) {
      const [lng, lat] = preset.presetLocation.split(",").map(parseFloat);
      if (!Number.isNaN(lng) && !Number.isNaN(lat)) {
        return { lng, lat, loc: preset.presetLocation };
      }
    }
    const loc = poi.location || "";
    if (loc.includes(",")) {
      const [lng, lat] = loc.split(",").map(parseFloat);
      if (!Number.isNaN(lng) && !Number.isNaN(lat)) {
        return { lng, lat, loc };
      }
    }
    if (poi.lnglat?.length >= 2) {
      const [lng, lat] = poi.lnglat;
      return { lng, lat, loc: `${lng},${lat}` };
    }
    return { lng: undefined, lat: undefined, loc: "" };
  }

  function resolveNavName(poi, keywords, preset) {
    return (
      preset?.displayName ||
      stripStationPrefix(keywords) ||
      stripStationPrefix(poi.display_name) ||
      stripStationPrefix(poi.name) ||
      poi.name ||
      keywords ||
      "目的地"
    );
  }



  async function openTaxi(lng, lat, name) {

    const params = new URLSearchParams({ lon: lng, lat, name: name || "目的地" });

    const res = await fetch(`/api/taxi/uri?${params}`);

    const data = await res.json();

    if (res.ok && data.uri) AmapUri.openInAmap(data.uri);

    else alert("无法生成叫车链接");

  }



  async function openNavigation(name, lng, lat, loc) {

    if (!userLocation) {

      try {

        setStatus?.("正在定位...");

        await requestLocation({ reverseGeocode: true });

        setStatus?.("");

      } catch {

        alert("导航需要先定位");

        return;

      }

    }

    const dest = {

      name,

      lnglat: lng != null && lat != null ? [lng, lat] : undefined,

      location: loc || (lng != null && lat != null ? `${lng},${lat}` : ""),

    };

    const parts = (userLocation || "").split(",");

    const origin = {

      name: locationLabel || "当前位置",

      location: userLocation,

      lnglat: parts.length >= 2 ? [parseFloat(parts[0]), parseFloat(parts[1])] : undefined,

    };

    const uri = AmapUri.buildNavigationUri(origin, dest, "walking");

    if (uri) {

      AmapUri.openInAmap(uri);

      close();

      return;

    }

    close();

    sendMessage(`从当前位置到${name}怎么走？`);

  }



  function render(data, keywords, preset) {

    const el = bodyEl();

    if (!el) return;

    const poi = data.poi || {};

    const guide = poi.guide || data.guide || {};

    const name = resolveNavName(poi, keywords, preset);

    const culture = poi.culture || guide.culture || "";

    const tips = poi.visit_tips || guide.tips || "";

    const ticket = poi.ticket || "";

    const cost = poi.cost || "";

    const rating = poi.rating || poi.biz_ext?.rating || "";

    const bestTime = poi.best_time || guide.best_time || "";

    const hasGuide = poi.has_guide || data.has_guide || !!culture;



    el.innerHTML = `

      <h4>${name}${hasGuide ? ' <span class="poi-guide-badge">有攻略</span>' : ""}</h4>

      ${poi.address ? `<p class="poi-detail-row"><strong>地址</strong>${poi.address}</p>` : ""}

      ${poi.tel ? `<p class="poi-detail-row"><strong>电话</strong>${poi.tel}</p>` : ""}

      ${poi.opentime ? `<p class="poi-detail-row"><strong>营业</strong>${poi.opentime}</p>` : ""}

      ${bestTime ? `<p class="poi-detail-row"><strong>推荐时段</strong>${bestTime}</p>` : ""}

      ${ticket ? `<p class="poi-detail-row"><strong>门票</strong>${ticket}</p>` : ""}

      ${cost ? `<p class="poi-detail-row"><strong>消费</strong>${cost}</p>` : ""}

      ${rating ? `<p class="poi-detail-row"><strong>评分</strong>${rating}</p>` : ""}

      ${culture ? `<p class="poi-detail-block"><strong>文化</strong>${culture}</p>` : ""}

      ${tips ? `<p class="poi-detail-block"><strong>贴士</strong>${tips}</p>` : ""}

      ${data.summary ? `<p class="poi-detail-summary">${data.summary}</p>` : ""}

      <div id="poiDetailActions" class="poi-detail-actions"></div>`;



    const actions = el.querySelector("#poiDetailActions");

    const { lng, lat, loc } = resolveNavCoords(poi, preset);



    const navBtn = document.createElement("button");

    navBtn.type = "button";

    navBtn.className = "btn-ghost primary";

    navBtn.textContent = "在高德 App 导航";

    navBtn.onclick = () => openNavigation(name, lng, lat, loc);

    actions.appendChild(navBtn);



    if (lng != null && lat != null) {

      const taxiBtn = document.createElement("button");

      taxiBtn.type = "button";

      taxiBtn.className = "btn-ghost";

      taxiBtn.textContent = "在高德叫车";

      taxiBtn.onclick = () => openTaxi(lng, lat, name);

      actions.appendChild(taxiBtn);

    }



    const favBtn = document.createElement("button");

    favBtn.type = "button";

    favBtn.className = "btn-ghost";

    favBtn.textContent = "收藏";

    favBtn.onclick = async () => {

      const ok = await FavoritesPanel.favoritePoi(name);

      if (ok) favBtn.textContent = "已收藏";

    };

    actions.appendChild(favBtn);

  }



  async function show(keywordsOrOpts, city = "") {

    const opts = parseOpts(keywordsOrOpts, city);

    if (!opts.keywords) return;

    overlay()?.classList.add("open");

    if (bodyEl()) bodyEl().innerHTML = '<p class="poi-detail-loading">正在加载详情...</p>';



    try {

      const params = new URLSearchParams({ keywords: opts.keywords });

      const resolvedCity = opts.city || (typeof getUserCity === "function" ? getUserCity() : "");

      if (resolvedCity) params.set("city", resolvedCity);

      if (opts.poiId) params.set("poi_id", opts.poiId);

      if (opts.presetLocation) params.set("hint_location", opts.presetLocation);

      else if (opts.presetLnglat?.length >= 2) {
        params.set("hint_location", `${opts.presetLnglat[0]},${opts.presetLnglat[1]}`);
      }

      const res = await fetch(`/api/poi/detail?${params}`);

      if (!res.ok) throw new Error("未找到详情");

      const data = await res.json();

      render(data, opts.keywords, opts);

    } catch (e) {

      if (bodyEl()) bodyEl().innerHTML = `<p class="poi-detail-error">${e.message || "加载失败"}</p>`;

    }

  }



  function bind() {

    document.getElementById("poiDetailClose")?.addEventListener("click", close);

    overlay()?.addEventListener("click", (e) => {

      if (e.target === overlay()) close();

    });

    document.querySelector(".poi-detail-dialog")?.addEventListener("click", (e) => e.stopPropagation());

  }



  bind();

  return { show, close };

})();



function openPoiDetail(poi, poiData) {

  PoiDetail.show({

    name: poi.display_name || poi.name,

    display_name: poi.display_name || poi.name,

    city: typeof getUserCity === "function" ? getUserCity() : poiData?.city || "",

    poiId: poi.poi_id || poi.id,

    lnglat: poi.lnglat,

    location: poi.location,

  });

}



function getUserCity() {

  return userCity || "";

}


