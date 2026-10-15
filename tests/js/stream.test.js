// stream controller — socket lifecycle tests (node --test, DOM-free).
//
// R8 (issue #149/DEBT-8): a subscribe BEFORE boot completes must still OPEN the
// socket, not merely record the pending key. The exchange socket is faked so we
// assert construction count deterministically (no browser, no network).
import test from "node:test";
import assert from "node:assert";
import { createStream } from "../../web/market/templates/market/controllers/stream.js";

function fakeDeps() {
  const store = { get: () => ({ symbol: "BTCUSDT", interval: "1m" }) };
  const bus = { emit: () => {} };
  const host = {};
  const config = {
    wsUrl: "wss://fapi.bitunix.com/public/",
    channels: { "1m": "market_kline_1min", "5m": "market_kline_5min" },
  };
  return { store, bus, host, config };
}

function installWebSocketStub() {
  const constructed = [];
  class FakeWebSocket {
    constructor(url) {
      this.url = url;
      this.readyState = 0; // CONNECTING
      this.sent = [];
      constructed.push(this);
    }
    send(payload) {
      this.sent.push(JSON.parse(payload));
    }
    close() {}
  }
  globalThis.WebSocket = FakeWebSocket;
  return constructed;
}

test("subscribe with no socket opens exactly one", () => {
  const constructed = installWebSocketStub();
  const stream = createStream(fakeDeps());

  stream.subscribe({ symbol: "BTCUSDT", interval: "5m" });

  assert.strictEqual(constructed.length, 1);
  assert.strictEqual(constructed[0].url, "wss://fapi.bitunix.com/public/");
});

test("2nd subscribe before open constructs no new socket", () => {
  const constructed = installWebSocketStub();
  const stream = createStream(fakeDeps());

  stream.subscribe({ symbol: "BTCUSDT", interval: "5m" });
  stream.subscribe({ symbol: "BTCUSDT", interval: "1m" });

  assert.strictEqual(constructed.length, 1);
});

test("subscribe on an OPEN socket sends the frame, no new socket", () => {
  const constructed = installWebSocketStub();
  const stream = createStream(fakeDeps());

  stream.subscribe({ symbol: "BTCUSDT", interval: "5m" });
  const socket = constructed[0];
  socket.readyState = 1; // OPEN

  stream.subscribe({ symbol: "BTCUSDT", interval: "1m" });

  assert.strictEqual(constructed.length, 1, "no duplicate socket");
  const ops = socket.sent.map((f) => f.op);
  assert.deepStrictEqual(ops, ["unsubscribe", "subscribe"]);
  assert.strictEqual(socket.sent[1].args[0].ch, "market_kline_1min");
});
