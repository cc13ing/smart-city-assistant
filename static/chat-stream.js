/** SSE 流式事件消费（chat/stream 与 chat/resume 共用） */
const ChatStream = (() => {
  async function consume(response, ctx) {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const event = JSON.parse(line.slice(6));
          await handleEvent(event, ctx);
        } catch (_) {}
      }
    }
  }

  async function handleEvent(event, ctx) {
    const {
      setStatus,
      ensureAssistantShell,
      ensureAssistantText,
      appendPoiSummary,
      appendRouteSummary,
      appendTrafficSummary,
      appendMessageFooter,
      appendMessage,
      onConfirmRequired,
    } = ctx;

    if (event.type === "status") {
      setStatus?.(event.content);
    } else if (event.type === "poi_map") {
      setStatus?.("");
      ctx.pendingPoiMap = event.content;
      ctx.mapUpdatedThisTurn = true;
      appendPoiSummary?.(
        ensureAssistantShell(),
        ctx.pendingPoiMap,
        !ctx.pendingRouteMap && !ctx.pendingTrafficMap
      );
    } else if (event.type === "traffic_map") {
      setStatus?.("");
      ctx.pendingTrafficMap = event.content;
      ctx.mapUpdatedThisTurn = true;
      appendTrafficSummary?.(
        ensureAssistantShell(),
        ctx.pendingTrafficMap,
        !ctx.pendingRouteMap
      );
    } else if (event.type === "route_map") {
      setStatus?.("");
      ctx.pendingRouteMap = event.content;
      ctx.mapUpdatedThisTurn = true;
      appendRouteSummary?.(ensureAssistantShell(), ctx.pendingRouteMap);
    } else if (event.type === "trip_plan") {
      setStatus?.("");
      ctx.pendingTripPlan = event.content;
      TripPanel.appendTripToMessage(ensureAssistantShell(), ctx.pendingTripPlan);
    } else if (event.type === "image") {
      setStatus?.("");
      ensureAssistantShell().appendChild(
        Multimodal.createGeneratedImage(event.content?.url || event.content, "生成图片")
      );
    } else if (event.type === "token") {
      setStatus?.("");
      ctx.fullText = (ctx.fullText || "") + event.content;
      Markdown.setContent(ensureAssistantText(), ctx.fullText, true);
      ctx.messagesEl.scrollTop = ctx.messagesEl.scrollHeight;
    } else if (event.type === "done") {
      setStatus?.("");
      if (event.session_id) {
        ctx.sessionId = event.session_id;
        localStorage.setItem("session_id", event.session_id);
      }
      if (event.poi_map && !ctx.pendingPoiMap) {
        ctx.mapUpdatedThisTurn = true;
        appendPoiSummary?.(
          ensureAssistantShell(),
          event.poi_map,
          !event.route_map && !event.traffic_map
        );
      }
      if (event.traffic_map && !ctx.pendingTrafficMap) {
        ctx.mapUpdatedThisTurn = true;
        appendTrafficSummary?.(ensureAssistantShell(), event.traffic_map, !event.route_map);
      }
      if (event.route_map && !ctx.pendingRouteMap) {
        ctx.mapUpdatedThisTurn = true;
        appendRouteSummary?.(ensureAssistantShell(), event.route_map);
      }
      if (event.trip_plan && !ctx.pendingTripPlan) {
        TripPanel.appendTripToMessage(ensureAssistantShell(), event.trip_plan);
      }
      if (event.image_url) {
        ensureAssistantShell().appendChild(
          Multimodal.createGeneratedImage(event.image_url, "生成图片")
        );
      }
      const routeMap = ctx.pendingRouteMap || event.route_map;
      const poiMap = ctx.pendingPoiMap || event.poi_map;
      const trafficMap = ctx.pendingTrafficMap || event.traffic_map;
      if (routeMap) MapPanel.showRoute?.(routeMap);
      else if (poiMap) MapPanel.showPoi?.(poiMap);
      else if (trafficMap) MapPanel.showTraffic?.(trafficMap);
      else if (!ctx.mapUpdatedThisTurn) MapPanel.clear?.();
      ctx.fullText = event.content || ctx.fullText;
      if (ctx.fullText || ctx.pendingRouteMap || ctx.pendingPoiMap || ctx.pendingTripPlan) {
        Markdown.setContent(ensureAssistantText(), ctx.fullText || "", false);
        appendMessageFooter?.(ensureAssistantShell(), {
          text: ctx.fullText,
          routeMap: ctx.pendingRouteMap,
          poiMap: ctx.pendingPoiMap,
          tripPlan: ctx.pendingTripPlan,
        });
      }
    } else if (event.type === "confirm_required" || event.type === "image_confirm") {
      setStatus?.("");
      await onConfirmRequired?.(event);
    } else if (event.type === "error") {
      setStatus?.("");
      if (ctx.assistantEl && !ctx.fullText?.trim() && !ctx.pendingRouteMap && !ctx.pendingPoiMap) {
        ctx.assistantEl.remove();
        ctx.assistantEl = null;
      }
      appendMessage?.("assistant", "错误: " + event.content);
    }
  }

  return { consume };
})();
