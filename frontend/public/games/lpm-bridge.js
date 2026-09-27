/* LAN Party Manager — mini-game bridge (shared by every embedded game).
 *
 * A game never talks to the LPM API itself. It calls LPM.startRun() / LPM.submitRun()
 * and this file relays both over postMessage to the hosting page, which owns the auth
 * token and does the real HTTP call (see frontend/src/components/MiniGames.tsx).
 *
 * Why not just fetch() from the game? The iframe IS same-origin, so it *could* read the
 * JWT out of localStorage. Deliberately not doing that keeps each game a dumb, portable
 * HTML file with no LPM knowledge beyond this file, and keeps credentials on one side of
 * the boundary. With up to 8 games planned, that separation is what makes adding game
 * number 9 a copy of two function calls rather than a copy of the auth handling.
 *
 * Outside an iframe every call resolves to null and the game just runs, unscored — so a
 * game file stays openable on its own by double-clicking it.
 */
(function (global) {
  'use strict';

  // parent === self when the page is top-level, i.e. opened directly.
  var embedded = global.parent && global.parent !== global;

  // The host page is served from the same origin as the game (frontend/public/games/*),
  // so its origin is ours. Never post to '*': that would hand a run token to whatever
  // happens to be framing us. In the desktop app the frontend itself sits inside the
  // Tauri shell's iframe, but the game's *parent* is still the frontend — same origin —
  // so this stays correct there. See CLAUDE.md on the shell/iframe architecture.
  var HOST_ORIGIN = global.location.origin;

  var seq = 0;
  var pending = {};

  // Host may be slow or the feature may have been disabled mid-run; never leave the game
  // waiting on a promise that can't resolve.
  var REPLY_TIMEOUT_MS = 8000;

  function call(type, payload) {
    if (!embedded) return Promise.resolve(null);

    var id = ++seq;
    var message = { source: 'lpm-minigame', id: id, type: type };
    for (var k in payload) {
      if (Object.prototype.hasOwnProperty.call(payload, k)) message[k] = payload[k];
    }

    return new Promise(function (resolve) {
      pending[id] = resolve;
      global.setTimeout(function () {
        if (pending[id]) { delete pending[id]; resolve(null); }
      }, REPLY_TIMEOUT_MS);

      try {
        global.parent.postMessage(message, HOST_ORIGIN);
      } catch (e) {
        delete pending[id];
        resolve(null);
      }
    });
  }

  global.addEventListener('message', function (event) {
    if (event.origin !== HOST_ORIGIN) return;
    var data = event.data;
    if (!data || data.source !== 'lpm-host') return;

    var resolve = pending[data.id];
    if (!resolve) return;
    delete pending[data.id];
    resolve(data.payload === undefined ? null : data.payload);
  });

  global.LPM = {
    /** True when running inside the LPM hub (i.e. scores can be submitted). */
    embedded: embedded,

    /**
     * Open a scored run. Resolves to a run token, or null when unscored
     * (not embedded, feature off, host unreachable). Call at game start.
     * @param {string} game slug, must match the backend registry (minigames_registry.py)
     */
    startRun: function (game) {
      return call('run-start', { game: game });
    },

    /**
     * Submit a finished run. `score` is the single ranked number for this game — its
     * meaning is defined per-game in the backend registry. `details` is a free-form
     * object of extra stats shown next to the score but never ranked on.
     */
    submitRun: function (token, score, details) {
      if (!token) return Promise.resolve(null);
      return call('run-end', { token: token, score: score, details: details || {} });
    },
  };
})(window);
