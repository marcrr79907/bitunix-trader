// controllers/stream.js — live WS stream (update() only) + close refresh.
//
// DI factory (R14): ``create({store, bus, host, config})``. LEAF module — never
// imports main. Owns the socket, ping/backoff timers and the ``sub`` key.
// #68 write path: the live push uses host.updateCandle + series ``update()``
// ONLY (never a full-series setData). On candle close it refreshes the LAST
// point of every active series via update().
import * as Core from "../chart-core.js";
import { klineUrlFrom } from "./history.js";

export function createStream({ store, bus, host, config }) {
  const state = store.get();
  const refetchDelay = 1500;

  let ws = null;
  let sub = null; // {symbol, interval} pending or active
  let retry = 0;
  let pingTimer = null;
  let closeTimer = null;

  function onPush(m) {
    if (!sub || m.symbol !== state.symbol) return;
    // #150: drop frames whose exchange channel does not match the ACTIVE
    // subscription. `sub.interval` (not state.interval, which mutates before the
    // socket confirms) is authoritative for both the compare and the bucket.
    if (!Core.isFrameForChannel(m, config.channels[sub.interval])) return;
    const t = Core.bucketTime(m.ts, sub.interval);
    const bar = {
      time: t,
      open: +m.data.o, high: +m.data.h, low: +m.data.l, close: +m.data.c,
    };
    host.updateCandle(bar); // the ONLY live candle write (update, never setData)

    if (t > host.getLastBucket()) {
      host.setLastBucket(t); // monotonic: a closed candle advanced the bucket
      bus.emit("candle:closed", { time: t });
      scheduleCloseRefresh();
    }
  }

  // On candle close, advance the LAST point of every active series via update()
  // (no setData): R6, single-write-path preserved for the live stream.
  function scheduleCloseRefresh() {
    if (closeTimer) return;
    closeTimer = setTimeout(function () {
      closeTimer = null;
      fetch(klineUrlFrom(state, config.urls.kline, "limit=2"))
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (p) {
          if (!p) return;
          const seriesData = host.getSeriesData();
          host.getActiveSeries().forEach(function (a) {
            const pt = Core.lastPoint(host.seriesFromPayload(a, p));
            if (!pt) return;
            const k = host.dataKey(a.place, a.pane, a.key);
            Core.upsertCandle(seriesData[k] || (seriesData[k] = []), pt);
            a.series.update(pt); // advance the last point only
          });
          host.setRsi(host.rsiValues(p));
        })
        .catch(function () { /* keep current series */ });
    }, refetchDelay);
  }

  function sendSubscribe(next) {
    if (sub && ws) {
      ws.send(JSON.stringify({
        op: "unsubscribe",
        args: [{ ch: config.channels[sub.interval], symbol: sub.symbol }],
      }));
    }
    sub = next;
    ws.send(JSON.stringify({
      op: "subscribe",
      args: [{ ch: config.channels[next.interval], symbol: next.symbol }],
    }));
  }

  function startPing() {
    if (pingTimer) clearInterval(pingTimer);
    pingTimer = setInterval(function () {
      if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({ op: "ping", ping: Math.floor(Date.now() / 1000) }));
      }
    }, 20000);
  }

  function backoff() {
    return Math.min(1000 * Math.pow(2, retry), 60000) * (0.5 + Math.random());
  }

  function connect(next) {
    if (next) sub = next;
    ws = new WebSocket(config.wsUrl);
    ws.onopen = function () {
      retry = 0;
      startPing();
      if (sub) sendSubscribe(sub);
    };
    ws.onmessage = function (e) { onPush(JSON.parse(e.data)); };
    ws.onclose = function () {
      if (pingTimer) clearInterval(pingTimer);
      setTimeout(connect, backoff());
      retry += 1;
    };
    ws.onerror = function () { ws.close(); };
  }

  // Subscribe to the given key: unsubscribe+subscribe on a live socket, else
  // just record the pending key (the socket connects/subscribes on open).
  function subscribe(next) {
    if (ws && ws.readyState === 1) sendSubscribe(next);
    else sub = next;
  }

  return { connect, subscribe };
}
