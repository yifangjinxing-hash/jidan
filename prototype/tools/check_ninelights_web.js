#!/usr/bin/env node
"use strict";

var assert = require("node:assert/strict");
var fs = require("node:fs");
var path = require("node:path");
var vm = require("node:vm");

var repoRoot = path.resolve(__dirname, "..", "..");
var implementationPath = path.join(repoRoot, "prototype", "web", "ninelights.js");
var htmlPath = path.join(repoRoot, "prototype", "web", "ninelights.html");
var vectorsPath = path.join(repoRoot, "profiles", "conformance", "game.ninelights.vectors.json");
var game = require(implementationPath);
var vectors = JSON.parse(fs.readFileSync(vectorsPath, "utf8"));

assert.equal(game.PROFILE, vectors.profile);
assert.equal(game.RULES_VERSION, vectors.rulesVersion);
assert.equal(game.START_CAPABILITY_ID, vectors.startCapability);
assert.equal(game.PRESS_CAPABILITY_ID, vectors.pressCapability);

vectors.startCases.forEach(function (testCase) {
  assert.deepStrictEqual(
    game.invoke(game.START_CAPABILITY_ID, { levelId: testCase.levelId }),
    testCase.expected,
    "start vector failed: " + testCase.levelId
  );
});

vectors.pressCases.forEach(function (testCase) {
  var initial = game.start({ levelId: testCase.levelId });
  var snapshot = JSON.stringify(initial);
  var output = game.invoke(game.PRESS_CAPABILITY_ID, { state: initial, cell: testCase.cell });
  assert.equal(JSON.stringify(initial), snapshot, "press mutated its input state");
  assert.deepStrictEqual(
    {
      cells: output.state.cells,
      moveCount: output.state.moveCount,
      status: output.state.status,
      changedCells: output.changedCells,
      event: output.event
    },
    testCase.expected,
    "press vector failed: " + testCase.levelId + "/" + testCase.cell
  );
});

vectors.solutionCases.forEach(function (testCase) {
  var state = game.start({ levelId: testCase.levelId });
  testCase.cells.forEach(function (cell) {
    state = game.press({ state: state, cell: cell }).state;
  });
  assert.equal(state.status, testCase.expectedStatus, "solution vector failed: " + testCase.levelId);
});

assert.throws(function () { game.start({ levelId: "unknown" }); }, /built-in Nine Lights level/);
assert.throws(function () { game.press({ state: game.start({ levelId: "cross" }), cell: 9 }); }, /0 through 8/);
var won = game.press({ state: game.start({ levelId: "cross" }), cell: 4 }).state;
assert.throws(function () { game.press({ state: won, cell: 0 }); }, /terminal/);

var builtIn = game.runConformance();
assert.equal(builtIn.ok, true, "browser built-in conformance failed");
assert.equal(builtIn.total, vectors.startCases.length + vectors.pressCases.length + vectors.solutionCases.length);

var implementationSource = fs.readFileSync(implementationPath, "utf8");
var browserContext = {};
vm.createContext(browserContext);
vm.runInContext(implementationSource, browserContext, { filename: "ninelights.js" });
assert.ok(browserContext.NineLights, "browser global NineLights was not exported");
assert.equal(browserContext.NineLights.runConformance().ok, true);

var html = fs.readFileSync(htmlPath, "utf8");
assert.match(html, /<script src="ninelights\.js"><\/script>/);
assert.match(html, /独立 JavaScript Host/);
assert.match(html, /不经过 Python/);
assert.equal(/https?:\/\//i.test(html), false, "the offline page contains an external URL");
assert.equal(/\b(?:fetch|XMLHttpRequest|WebSocket)\b/.test(html), false, "the offline page contains a network API");
assert.equal((html.match(/class="cell"/g) || []).length, 9, "the page must expose nine cell buttons");

console.log(
  "Nine Lights Web conformance: " + builtIn.passed + "/" + builtIn.total +
  " canonical vectors passed (independent JavaScript Host; not Python JidanRuntime)."
);
