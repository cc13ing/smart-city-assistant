/** 侧栏「我的城市」：收藏、常去城市、偏好摘要（支持删除） */

const FavoritesPanel = (() => {
  const container = () => document.getElementById("favoritesPanel");

  let cachedPoiNames = new Set();

  function accountToken() {
    return localStorage.getItem("account_token") || "";
  }

  function ownerParams() {
    const p = new URLSearchParams({ device_id: ensureDeviceId() });
    const token = accountToken();
    if (token) p.set("account_token", token);
    return p;
  }

  async function loadProfileSummary() {
    try {
      const res = await fetch(`${API}/api/profile/${ensureDeviceId()}`);
      if (!res.ok) return null;
      return res.json();
    } catch {
      return null;
    }
  }

  async function load() {
    const el = container();
    if (!el) return;
    el.innerHTML = '<p class="favorites-empty">加载中...</p>';
    try {
      const [favRes, profile] = await Promise.all([
        fetch(`${API}/api/favorites?${ownerParams()}`),
        loadProfileSummary(),
      ]);
      if (!favRes.ok) throw new Error("加载失败");
      const data = await favRes.json();
      if (data.account_token) {
        localStorage.setItem("account_token", data.account_token);
      }
      cachedPoiNames = new Set(data.favorite_poi_names || []);
      render(data, profile);
    } catch (e) {
      el.innerHTML = `<p class="favorites-empty">加载失败</p>`;
      console.error(e);
    }
  }

  function preferenceEntries(profile) {
    const weights = profile?.poi_weights || {};
    return Object.entries(weights).map(([key, val]) => {
      const idx = key.indexOf(":");
      const category = idx >= 0 ? key.slice(0, idx) : "poi";
      const target = idx >= 0 ? key.slice(idx + 1) : key;
      return { category, target, weight: val };
    });
  }

  function render(data, profile) {
    const el = container();
    if (!el) return;

    const pois = data.favorite_poi_names || [];
    const trips = data.favorite_trips || [];
    const cities = data.favorite_cities?.length
      ? data.favorite_cities
      : profile?.favorite_cities || [];
    const taste = profile?.feedback_summary || "";
    const prefs = preferenceEntries(profile);

    if (!pois.length && !trips.length && !cities.length && !taste && !prefs.length) {
      el.innerHTML =
        '<p class="favorites-empty">暂无收藏<br><span>在地点详情或行程卡上收藏，反馈会更新偏好</span></p>';
      return;
    }

    el.innerHTML = "";

    if (cities.length) {
      el.appendChild(sectionTitle("常去城市", cities.length));
      const cityRow = document.createElement("div");
      cityRow.className = "my-city-tags";
      cities.slice(0, 8).forEach((city) => {
        cityRow.appendChild(cityTag(city));
      });
      el.appendChild(cityRow);
    }

    if (taste || prefs.length) {
      el.appendChild(sectionTitle("偏好", prefs.length || (taste ? 1 : 0)));
      if (taste) {
        const tasteEl = document.createElement("p");
        tasteEl.className = "my-city-taste";
        tasteEl.textContent = taste;
        el.appendChild(tasteEl);
      }
      if (prefs.length) {
        const list = document.createElement("ul");
        list.className = "favorites-list my-pref-list";
        prefs.slice(0, 12).forEach((item) => list.appendChild(preferenceItem(item)));
        el.appendChild(list);
        const clearBtn = document.createElement("button");
        clearBtn.type = "button";
        clearBtn.className = "my-pref-clear-btn";
        clearBtn.textContent = "清空全部偏好";
        clearBtn.onclick = () => clearAllFeedback();
        el.appendChild(clearBtn);
      }
    }

    if (pois.length) {
      el.appendChild(sectionTitle("收藏地点", pois.length));
      const list = document.createElement("ul");
      list.className = "favorites-list";
      pois.forEach((name) => list.appendChild(poiItem(name)));
      el.appendChild(list);
    }

    if (trips.length) {
      el.appendChild(sectionTitle("收藏行程", trips.length));
      const list = document.createElement("ul");
      list.className = "favorites-list";
      trips.forEach((trip) => list.appendChild(tripItem(trip)));
      el.appendChild(list);
    }
  }

  function sectionTitle(label, count) {
    const h = document.createElement("div");
    h.className = "favorites-section-title";
    h.textContent = `${label} · ${count}`;
    return h;
  }

  function cityTag(city) {
    const wrap = document.createElement("span");
    wrap.className = "my-city-tag-wrap";

    const tag = document.createElement("button");
    tag.type = "button";
    tag.className = "my-city-tag";
    tag.textContent = city;
    tag.onclick = () => {
      closeSidebar?.();
      sendMessage(`${city}有什么值得去的地方？`);
    };

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "my-city-tag-remove";
    removeBtn.title = "移除";
    removeBtn.textContent = "×";
    removeBtn.onclick = (e) => {
      e.stopPropagation();
      removeCity(city);
    };

    wrap.appendChild(tag);
    wrap.appendChild(removeBtn);
    return wrap;
  }

  function preferenceItem({ category, target, weight }) {
    const li = document.createElement("li");
    li.className = "favorite-item my-pref-item";
    const icon = weight > 0 ? "👍" : "👎";
    const catLabel = category === "poi" ? "地点" : category;
    li.innerHTML = `
      <span class="favorite-name" title="${target}">${icon} ${target}</span>
      <span class="favorite-meta">${catLabel}</span>`;
    li.appendChild(
      actionRow([{ label: "移除", danger: true, onClick: () => removeFeedback(target, category) }])
    );
    return li;
  }

  function poiItem(name) {
    const li = document.createElement("li");
    li.className = "favorite-item";
    li.innerHTML = `<span class="favorite-name" title="${name}">${name}</span>`;
    li.appendChild(
      actionRow([
        { label: "详情", primary: true, onClick: () => openPoiFromFavorite(name) },
        { label: "导航", onClick: () => navigateToPoi(name) },
        { label: "移除", danger: true, onClick: () => removePoi(name) },
      ])
    );
    return li;
  }

  function tripItem(trip) {
    const li = document.createElement("li");
    li.className = "favorite-item";
    const title = trip.title || trip.city || "我的行程";
    const meta = `${trip.city || ""}${trip.stop_count ? ` · ${trip.stop_count} 站` : ""}`;
    li.innerHTML = `
      <span class="favorite-name" title="${title}">${title}</span>
      <span class="favorite-meta">${meta}</span>`;
    li.appendChild(
      actionRow([
        { label: "打开", primary: true, onClick: () => openTrip(trip.trip_id) },
        { label: "分享", onClick: () => shareTripFromFavorite(trip.trip_id) },
        { label: "伴游", onClick: () => startCompanion(trip.trip_id) },
        { label: "移除", danger: true, onClick: () => removeTrip(trip.trip_id) },
      ])
    );
    return li;
  }

  function actionRow(actions) {
    const row = document.createElement("div");
    row.className = "favorite-actions";
    actions.forEach(({ label, onClick, primary, danger }) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "favorite-action-btn";
      if (primary) btn.classList.add("primary");
      if (danger) btn.classList.add("danger");
      btn.textContent = label;
      btn.onclick = (e) => {
        e.stopPropagation();
        onClick();
      };
      row.appendChild(btn);
    });
    return row;
  }

  function openPoiFromFavorite(name) {
    closeSidebar?.();
    openPoiDetail({ name }, { city: getUserCity() });
  }

  async function navigateToPoi(name) {
    closeSidebar?.();
    openPoiFromFavorite(name);
  }

  async function shareTripFromFavorite(tripId) {
    try {
      const res = await fetch(`${API}/api/trips/${tripId}?${ownerParams()}`);
      if (!res.ok) throw new Error("无法加载行程");
      const trip = await res.json();
      closeSidebar?.();
      await SharePanel.shareTrip?.(trip);
    } catch (e) {
      alert(e.message || "分享失败");
    }
  }

  async function openTrip(tripId) {
    try {
      const res = await fetch(`${API}/api/trips/${tripId}?${ownerParams()}`);
      if (!res.ok) throw new Error("无法加载行程");
      const trip = await res.json();
      closeSidebar?.();
      messagesEl.querySelector(".welcome-hero")?.remove();
      const div = document.createElement("div");
      div.className = "message assistant";
      messagesEl.appendChild(div);
      TripPanel.appendTripToMessage(div, trip);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    } catch (e) {
      alert(e.message || "打开行程失败");
    }
  }

  async function startCompanion(tripId) {
    closeSidebar?.();
    if (!userLocation) {
      try {
        await requestLocation({ reverseGeocode: true });
      } catch {
        alert("伴游需要先定位");
        return;
      }
    }
    try {
      await TripPanel.startCompanionForTrip?.(tripId);
    } catch (e) {
      alert(e.message || "开启伴游失败");
    }
  }

  async function removeCity(city) {
    try {
      const params = ownerParams();
      params.set("city", city);
      const res = await fetch(`${API}/api/profile/${ensureDeviceId()}/city?${params}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("移除失败");
      await load();
    } catch (e) {
      alert(e.message || "移除失败");
    }
  }

  async function removeFeedback(target, category) {
    try {
      const params = ownerParams();
      params.set("target", target);
      params.set("category", category || "poi");
      const res = await fetch(`${API}/api/profile/${ensureDeviceId()}/feedback?${params}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("移除失败");
      await load();
    } catch (e) {
      alert(e.message || "移除失败");
    }
  }

  async function clearAllFeedback() {
    if (!confirm("确定清空全部偏好反馈？此操作不可恢复。")) return;
    try {
      const res = await fetch(
        `${API}/api/profile/${ensureDeviceId()}/feedback/all?${ownerParams()}`,
        { method: "DELETE" }
      );
      if (!res.ok) throw new Error("清空失败");
      await load();
    } catch (e) {
      alert(e.message || "清空失败");
    }
  }

  async function removePoi(name) {
    try {
      const params = ownerParams();
      params.set("poi_name", name);
      const res = await fetch(`${API}/api/favorites/poi?${params}`, { method: "DELETE" });
      if (!res.ok) throw new Error("移除失败");
      await load();
    } catch (e) {
      alert(e.message);
    }
  }

  async function removeTrip(tripId) {
    try {
      const res = await fetch(`${API}/api/favorites/trip/${tripId}?${ownerParams()}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("移除失败");
      await load();
    } catch (e) {
      alert(e.message);
    }
  }

  async function favoritePoi(name) {
    if (!name) return false;
    try {
      const res = await fetch(`${API}/api/favorites/poi`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_id: ensureDeviceId(),
          account_token: accountToken() || undefined,
          poi_name: name,
        }),
      });
      if (!res.ok) throw new Error("收藏失败");
      cachedPoiNames.add(name);
      await load();
      return true;
    } catch (e) {
      alert(e.message);
      return false;
    }
  }

  function isFavorited(name) {
    return cachedPoiNames.has(name);
  }

  return { load, refresh: load, favoritePoi, isFavorited };
})();
