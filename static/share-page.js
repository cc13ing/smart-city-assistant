(function () {

  const token = location.pathname.split("/").pop();

  const titleEl = document.getElementById("shareTitle");

  const metaEl = document.getElementById("shareMeta");

  const contentEl = document.getElementById("shareContent");



  function escapeHtml(text) {

    const d = document.createElement("div");

    d.textContent = text || "";

    return d.innerHTML;

  }



  function renderStops(trip) {

    const stops = trip.stops || [];

    if (stops.length) {

      return `<ol class="share-stops">${stops

        .map(

          (s, i) =>

            `<li><span class="share-stop-order">${i + 1}</span><div><strong>${escapeHtml(

              s.name || s.title || "站点"

            )}</strong>${s.note ? `<p>${escapeHtml(s.note)}</p>` : ""}${

              s.time ? `<span class="share-stop-time">${escapeHtml(s.time)}</span>` : ""

            }</div></li>`

        )

        .join("")}</ol>`;

    }



    const calendar = trip.calendar || [];

    const timeline = trip.timeline || [];

    if (calendar.length && timeline.length) {

      return calendar

        .map((day) => {

          const events = timeline.filter((e) => e.day === day.day);

          const items = events

            .map(

              (e) =>

                `<li><strong>${escapeHtml(e.time || "")}</strong> ${escapeHtml(

                  e.title || e.name || ""

                )}${e.note ? ` — ${escapeHtml(e.note)}` : ""}</li>`

            )

            .join("");

          return `<section class="share-day"><h3>第 ${day.day} 天 · ${escapeHtml(

            day.title || day.date || ""

          )}</h3><ul>${items}</ul></section>`;

        })

        .join("");

    }



    return `<pre class="share-fallback">${escapeHtml(

      JSON.stringify(trip, null, 2)

    )}</pre>`;

  }



  function renderTripCard(trip, createdAt) {

    const title = trip.title || `${trip.city || "城市"}行程`;

    const city = trip.city ? `<span class="share-city-tag">${escapeHtml(trip.city)}</span>` : "";

    const stopCount = (trip.stops || []).length;

    const meta =

      stopCount > 0

        ? `${stopCount} 个站点`

        : trip.days

          ? `${trip.days} 日游`

          : "只读分享";

    titleEl.textContent = title;

    metaEl.innerHTML = `${city}<span>${meta}</span> · 分享于 ${escapeHtml(

      (createdAt || "").slice(0, 16)

    )} · 只读`;

    contentEl.innerHTML = `

      <article class="share-trip-card">

        ${trip.summary ? `<p class="share-summary">${escapeHtml(trip.summary)}</p>` : ""}

        ${renderStops(trip)}

      </article>`;

  }



  async function load() {

    if (!token) {

      contentEl.textContent = "无效的分享链接";

      return;

    }

    try {

      const res = await fetch(`/api/share/${encodeURIComponent(token)}`);

      if (!res.ok) throw new Error("链接无效或已过期");

      const data = await res.json();

      renderTripCard(data.trip || {}, data.created_at);

    } catch (e) {

      contentEl.textContent = e.message || "加载失败";

    }

  }



  load();

})();


