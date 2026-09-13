/** 结构化行程卡：展示 / 编辑 / 收藏 / 全程伴游 */
const TripPanel = (() => {
  let activeTripId = localStorage.getItem("active_trip_id") || null;
  let trackTimer = null;
  let accountToken = localStorage.getItem("account_token") || null;

  function ownerParams() {
    const p = new URLSearchParams({ device_id: ensureDeviceId() });
    if (accountToken) p.set("account_token", accountToken);
    return p;
  }

  async function ensureAccount() {
    if (accountToken) return accountToken;
    try {
      const res = await fetch(`${API}/api/account/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: ensureDeviceId(), display_name: "旅行者" }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      accountToken = data.account_token;
      localStorage.setItem("account_token", accountToken);
      return accountToken;
    } catch {
      return null;
    }
  }

  async function saveTrip(trip) {
    await ensureAccount();
    const res = await fetch(`${API}/api/trips`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: ensureDeviceId(), account_token: accountToken, trip }),
    });
    if (!res.ok) throw new Error("保存行程失败");
    return res.json();
  }

  /** 聊天生成的行程仅有 trip_id，未必已落盘；操作前先确保持久化。 */
  async function ensureTripSaved(trip) {
    await ensureAccount();
    if (trip.trip_id) {
      try {
        const res = await fetch(`${API}/api/trips/${trip.trip_id}?${ownerParams()}`);
        if (res.ok) return res.json();
      } catch (_) {
        /* 网络异常时继续尝试保存 */
      }
    }
    const saved = await saveTrip(trip);
    Object.assign(trip, saved);
    return saved;
  }

  async function updateTrip(tripId, patch) {
    const res = await fetch(`${API}/api/trips/${tripId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: ensureDeviceId(),
        account_token: accountToken,
        patch,
      }),
    });
    if (!res.ok) throw new Error("更新行程失败");
    return res.json();
  }

  async function favoriteTrip(tripId) {
    await ensureAccount();
    const res = await fetch(
      `${API}/api/trips/${tripId}/favorite?${ownerParams()}`,
      { method: "POST" }
    );
    if (!res.ok) throw new Error("收藏失败");
    return res.json();
  }

  function renderCard(container, trip, { onChange } = {}) {
    if (!container || !trip) return;
    const stops = trip.stops || [];
    const progress = trip.progress || {
      completed: stops.filter((s) => s.visited).length,
      total: stops.length,
    };

    container.innerHTML = "";
    container.className = "trip-card";
    const head = document.createElement("div");
    head.className = "trip-card-head";
    head.innerHTML = `
      <div>
        <span class="badge badge-route">行程</span>
        <strong class="trip-card-title">${trip.title || "我的行程"}</strong>
        <p class="trip-card-meta">${trip.city || ""} · ${stops.length} 站 · 已完成 ${progress.completed}/${progress.total || stops.length}</p>
      </div>`;

    const actions = document.createElement("div");
    actions.className = "trip-card-actions";
    const favBtn = document.createElement("button");
    favBtn.type = "button";
    favBtn.className = "btn-ghost";
    favBtn.textContent = trip.favorite ? "已收藏" : "收藏";
    favBtn.onclick = async () => {
      try {
        const saved = await ensureTripSaved(trip);
        const fav = await favoriteTrip(saved.trip_id);
        Object.assign(trip, fav);
        favBtn.textContent = "已收藏";
        FavoritesPanel.refresh?.();
      } catch (e) {
        alert(e.message);
      }
    };

    const trackBtn = document.createElement("button");
    trackBtn.type = "button";
    trackBtn.className = "btn-ghost primary";
    trackBtn.textContent = activeTripId === trip.trip_id ? "伴游中…" : "开启全程伴游";
    trackBtn.onclick = async () => {
      try {
        const saved = await ensureTripSaved(trip);
        activeTripId = saved.trip_id;
        localStorage.setItem("active_trip_id", activeTripId);
        startTracking();
        trackBtn.textContent = "伴游中…";
      } catch (e) {
        alert(e.message);
      }
    };

    const shareBtn = document.createElement("button");
    shareBtn.type = "button";
    shareBtn.className = "btn-ghost";
    shareBtn.textContent = "分享";
    shareBtn.onclick = async () => {
      try {
        const saved = await ensureTripSaved(trip);
        SharePanel.shareTrip(saved);
      } catch (e) {
        alert(e.message);
      }
    };

    actions.appendChild(favBtn);
    actions.appendChild(shareBtn);
    actions.appendChild(trackBtn);
    head.appendChild(actions);
    container.appendChild(head);

    const list = document.createElement("ol");
    list.className = "trip-stop-list";
    stops.forEach((stop, idx) => {
      const li = document.createElement("li");
      li.className = stop.visited ? "visited" : idx === (trip.active_stop_index || 0) ? "active" : "";
      const input = document.createElement("input");
      input.type = "text";
      input.value = stop.name || "";
      input.className = "trip-stop-input";
      input.onchange = () => {
        stop.name = input.value.trim();
        if (onChange) onChange(trip);
      };
      li.appendChild(input);
      if (stop.time) {
        const time = document.createElement("span");
        time.className = "trip-stop-time";
        time.textContent = stop.time;
        li.appendChild(time);
      }
      list.appendChild(li);
    });
    container.appendChild(list);

    const foot = document.createElement("div");
    foot.className = "trip-card-foot";
    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "btn-ghost";
    saveBtn.textContent = "保存修改";
    saveBtn.onclick = async () => {
      try {
        const saved = await ensureTripSaved(trip);
        const updated = await updateTrip(saved.trip_id, { stops: trip.stops, title: trip.title });
        Object.assign(trip, updated);
        alert("行程已保存");
      } catch (e) {
        alert(e.message);
      }
    };
    foot.appendChild(saveBtn);
    container.appendChild(foot);
  }

  function clearActiveTrip() {
    activeTripId = null;
    localStorage.removeItem("active_trip_id");
    stopTracking();
    if (typeof setStatus === "function") setStatus("");
  }

  function isChatStreaming() {
    return typeof window.__cityIntroStreaming === "function" && window.__cityIntroStreaming();
  }

  async function pollTrack() {
    if (!activeTripId || !userLocation || isChatStreaming()) return;
    try {
      const params = ownerParams();
      params.set("location", userLocation);
      params.set("trip_id", activeTripId);
      const res = await fetch(`${API}/api/companion/track?${params}`);
      if (res.status === 404) {
        clearActiveTrip();
        return;
      }
      if (!res.ok) return;
      const data = await res.json();
      if (data.event?.message) {
        setStatus?.(data.event.message);
        appendSystemNotice?.(data.message || data.event.message);
      } else if (data.message) {
        setStatus?.(data.message);
      }
      if (data.status === "completed") {
        stopTracking();
        appendSystemNotice?.("全程伴游：本行程已完成 🎉");
      }
    } catch (_) {}
  }

  function startTracking() {
    stopTracking();
    if (!userLocation) {
      alert("请先定位以开启全程伴游");
      return;
    }
    pollTrack();
    trackTimer = setInterval(pollTrack, 30000);
  }

  function stopTracking() {
    if (trackTimer) clearInterval(trackTimer);
    trackTimer = null;
  }

  async function startCompanionForTrip(tripId) {
    const params = ownerParams();
    const res = await fetch(`${API}/api/trips/${tripId}?${params}`);
    if (!res.ok) throw new Error("无法加载行程");
    const trip = await res.json();
    activeTripId = trip.trip_id;
    localStorage.setItem("active_trip_id", activeTripId);
    startTracking();
    setStatus?.(`已开启全程伴游：${trip.title || trip.city || "我的行程"}`);
    appendSystemNotice?.(`全程伴游已开启，共 ${(trip.stops || []).length} 站`);
  }

  function appendTripToMessage(msgEl, tripData) {
    if (!msgEl || !tripData || msgEl.querySelector(".trip-card")) return;
    const wrap = document.createElement("div");
    wrap.className = "trip-card-wrap";
    renderCard(wrap, tripData, {
      onChange: (t) => {
        wrap._tripData = t;
      },
    });
    wrap._tripData = tripData;
    msgEl.appendChild(wrap);
    if (typeof Feedback !== "undefined") {
      Feedback.attachToSummaryCard(wrap, Feedback.targetsForTrip(tripData), ensureDeviceId());
    }
  }

  async function init() {
    if (!activeTripId) return;
    try {
      const params = ownerParams();
      const res = await fetch(`${API}/api/trips/${activeTripId}?${params}`);
      if (!res.ok) {
        clearActiveTrip();
      }
      // 仅恢复 active_trip_id，不自动轮询，避免覆盖对话生成中的状态提示
    } catch {
      clearActiveTrip();
    }
  }

  return {
    init,
    renderCard,
    appendTripToMessage,
    saveTrip,
    startTracking,
    stopTracking,
    clearActiveTrip,
    startCompanionForTrip,
    getActiveTripId: () => activeTripId,
  };
})();
