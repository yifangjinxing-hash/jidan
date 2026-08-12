(function (root, factory) {
  "use strict";

  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.NineLights = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var PROFILE = "JCL/0.1";
  var RULES_VERSION = "ninelights/1";
  var START_CAPABILITY_ID = "game.ninelights.start";
  var PRESS_CAPABILITY_ID = "game.ninelights.press";

  var LEVELS = Object.freeze({
    cross: Object.freeze([0, 1, 0, 1, 1, 1, 0, 1, 0]),
    corners: Object.freeze([1, 1, 0, 1, 0, 1, 0, 1, 1]),
    full: Object.freeze([1, 1, 1, 1, 1, 1, 1, 1, 1])
  });

  var TOGGLE_MAP = Object.freeze([
    Object.freeze([0, 1, 3]),
    Object.freeze([0, 1, 2, 4]),
    Object.freeze([1, 2, 5]),
    Object.freeze([0, 3, 4, 6]),
    Object.freeze([1, 3, 4, 5, 7]),
    Object.freeze([2, 4, 5, 8]),
    Object.freeze([3, 6, 7]),
    Object.freeze([4, 6, 7, 8]),
    Object.freeze([5, 7, 8])
  ]);

  // Compact signatures copied from the repository's canonical conformance vectors.
  // The Node checker reads that JSON directly; this table keeps file:// browser use
  // fully offline while still giving the visible demo a non-tautological self-check.
  var EXPECTED_PRESS_SIGNATURES = Object.freeze({
    cross: Object.freeze([
      "100011010|0,1,3|pressed",
      "101101010|0,1,2,4|pressed",
      "001110010|1,2,5|pressed",
      "110001110|0,3,4,6|pressed",
      "000000000|1,3,4,5,7|won",
      "011100011|2,4,5,8|pressed",
      "010011100|3,6,7|pressed",
      "010101101|4,6,7,8|pressed",
      "010110001|5,7,8|pressed"
    ]),
    corners: Object.freeze([
      "000001011|0,1,3|pressed",
      "001111011|0,1,2,4|pressed",
      "101100011|1,2,5|pressed",
      "010011111|0,3,4,6|pressed",
      "100010001|1,3,4,5,7|pressed",
      "111110010|2,4,5,8|pressed",
      "110001101|3,6,7|pressed",
      "110111100|4,6,7,8|pressed",
      "110100000|5,7,8|pressed"
    ]),
    full: Object.freeze([
      "001011111|0,1,3|pressed",
      "000101111|0,1,2,4|pressed",
      "100110111|1,2,5|pressed",
      "011001011|0,3,4,6|pressed",
      "101000101|1,3,4,5,7|pressed",
      "110100110|2,4,5,8|pressed",
      "111011001|3,6,7|pressed",
      "111101000|4,6,7,8|pressed",
      "111110100|5,7,8|pressed"
    ])
  });

  var SOLUTIONS = Object.freeze({
    cross: Object.freeze([4]),
    corners: Object.freeze([0, 8]),
    full: Object.freeze([0, 2, 4, 6, 8])
  });

  function isPlainObject(value) {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      return false;
    }
    var prototype = Object.getPrototypeOf(value);
    return prototype === Object.prototype || prototype === null;
  }

  function hasExactKeys(value, expected) {
    var actual = Object.keys(value).sort();
    var wanted = expected.slice().sort();
    return actual.length === wanted.length && actual.every(function (key, index) {
      return key === wanted[index];
    });
  }

  function cloneState(state) {
    return {
      rulesVersion: state.rulesVersion,
      levelId: state.levelId,
      cells: state.cells.slice(),
      moveCount: state.moveCount,
      status: state.status
    };
  }

  function validateState(raw) {
    var fields = ["rulesVersion", "levelId", "cells", "moveCount", "status"];
    if (!isPlainObject(raw)) {
      throw new TypeError("state must be an object");
    }
    if (!hasExactKeys(raw, fields)) {
      throw new TypeError("state fields do not match the Nine Lights contract");
    }
    if (raw.rulesVersion !== RULES_VERSION) {
      throw new RangeError("state rulesVersion is unsupported");
    }
    if (typeof raw.levelId !== "string" || !Object.prototype.hasOwnProperty.call(LEVELS, raw.levelId)) {
      throw new RangeError("state levelId is unsupported");
    }
    if (!Array.isArray(raw.cells) || raw.cells.length !== 9) {
      throw new TypeError("state cells must contain exactly 9 values");
    }
    if (!raw.cells.every(function (value) { return Number.isInteger(value) && (value === 0 || value === 1); })) {
      throw new TypeError("state cells must contain only integer 0 or 1");
    }
    if (!Number.isSafeInteger(raw.moveCount) || raw.moveCount < 0) {
      throw new TypeError("state moveCount must be a non-negative integer");
    }
    var isWon = raw.cells.every(function (value) { return value === 0; });
    if ((raw.status !== "playing" && raw.status !== "won") || (raw.status === "won") !== isWon) {
      throw new RangeError("state status does not match its cells");
    }
    return cloneState(raw);
  }

  function start(argumentsValue) {
    if (!isPlainObject(argumentsValue) || !hasExactKeys(argumentsValue, ["levelId"])) {
      throw new TypeError("start arguments must contain only levelId");
    }
    var levelId = argumentsValue.levelId;
    if (typeof levelId !== "string" || !Object.prototype.hasOwnProperty.call(LEVELS, levelId)) {
      throw new RangeError("levelId must name a built-in Nine Lights level");
    }
    return {
      rulesVersion: RULES_VERSION,
      levelId: levelId,
      cells: LEVELS[levelId].slice(),
      moveCount: 0,
      status: "playing"
    };
  }

  function press(argumentsValue) {
    if (!isPlainObject(argumentsValue) || !hasExactKeys(argumentsValue, ["state", "cell"])) {
      throw new TypeError("press arguments must contain only state and cell");
    }
    var state = validateState(argumentsValue.state);
    if (state.status === "won") {
      throw new RangeError("a won game is terminal; start a new level before pressing");
    }
    var cell = argumentsValue.cell;
    if (!Number.isInteger(cell) || cell < 0 || cell > 8) {
      throw new RangeError("cell must be an integer from 0 through 8");
    }

    var cells = state.cells.slice();
    var changedCells = TOGGLE_MAP[cell].slice();
    changedCells.forEach(function (changed) {
      cells[changed] = 1 - cells[changed];
    });
    var won = cells.every(function (value) { return value === 0; });
    return {
      state: {
        rulesVersion: RULES_VERSION,
        levelId: state.levelId,
        cells: cells,
        moveCount: state.moveCount + 1,
        status: won ? "won" : "playing"
      },
      changedCells: changedCells,
      event: won ? "won" : "pressed"
    };
  }

  function invoke(capabilityId, argumentsValue) {
    if (capabilityId === START_CAPABILITY_ID) {
      return start(argumentsValue);
    }
    if (capabilityId === PRESS_CAPABILITY_ID) {
      return press(argumentsValue);
    }
    throw new RangeError("unknown Nine Lights capability: " + String(capabilityId));
  }

  function pressSignature(output) {
    return output.state.cells.join("") + "|" + output.changedCells.join(",") + "|" + output.event;
  }

  function runConformance() {
    var failures = [];
    var passed = 0;
    var total = 0;

    Object.keys(LEVELS).forEach(function (levelId) {
      total += 1;
      var initial = start({ levelId: levelId });
      var expectedStart = RULES_VERSION + "|" + levelId + "|" + LEVELS[levelId].join("") + "|0|playing";
      var actualStart = initial.rulesVersion + "|" + initial.levelId + "|" + initial.cells.join("") + "|" + initial.moveCount + "|" + initial.status;
      if (actualStart === expectedStart) {
        passed += 1;
      } else {
        failures.push(levelId + " start");
      }

      for (var cell = 0; cell < 9; cell += 1) {
        total += 1;
        var actual = pressSignature(press({ state: initial, cell: cell }));
        if (actual === EXPECTED_PRESS_SIGNATURES[levelId][cell]) {
          passed += 1;
        } else {
          failures.push(levelId + " press " + cell);
        }
      }

      total += 1;
      var state = start({ levelId: levelId });
      SOLUTIONS[levelId].forEach(function (cell) {
        state = press({ state: state, cell: cell }).state;
      });
      if (state.status === "won") {
        passed += 1;
      } else {
        failures.push(levelId + " solution");
      }
    });

    return Object.freeze({
      ok: failures.length === 0,
      passed: passed,
      total: total,
      failures: Object.freeze(failures.slice())
    });
  }

  return Object.freeze({
    PROFILE: PROFILE,
    RULES_VERSION: RULES_VERSION,
    START_CAPABILITY_ID: START_CAPABILITY_ID,
    PRESS_CAPABILITY_ID: PRESS_CAPABILITY_ID,
    LEVEL_IDS: Object.freeze(Object.keys(LEVELS)),
    start: start,
    press: press,
    invoke: invoke,
    validateState: validateState,
    runConformance: runConformance
  });
});
