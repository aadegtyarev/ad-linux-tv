"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const html=fs.readFileSync("src/ad_linux_tv/static/remote.html","utf8");
const tvHtml=fs.readFileSync("src/ad_linux_tv/static/index.html","utf8");
const js=fs.readFileSync("src/ad_linux_tv/static/remote.js","utf8");
const css=fs.readFileSync("src/ad_linux_tv/static/style.css","utf8");

test("phone settings has parameters, not service/URL/browser-command banks",()=>{
  for(const id of ["services","open","remote-url","url-form","history-forward","menu-tab","menu-shift-tab","show-system"]){
    assert.doesNotMatch(html,new RegExp(`id="${id}"`));
    assert.doesNotMatch(js,new RegExp(`querySelector\\("#${id}"\\)`));
  }
  for(const id of ["audio-output","phone-browser-volume","phone-player-volume","phone-pointer-acceleration","phone-magnifier-scale"])
    assert.match(html,new RegExp(`id="${id}"`));
});

test("About is one shared collapsed read-only settings group, not a control bank",()=>{
  const tv=fs.readFileSync("src/ad_linux_tv/static/index.html","utf8");
  const group=source=>source.match(/<details class="settings-control" data-role="about">[\s\S]*?<\/details>/g);
  const phoneGroups=group(html), tvGroups=group(tv);
  assert.equal(phoneGroups.length,1);
  assert.deepEqual(phoneGroups,tvGroups);
  assert.match(phoneGroups[0],/<summary>О программе<\/summary>/);
  assert.doesNotMatch(phoneGroups[0],/\bopen\b|<button|<input|<select|<form|onclick/);
  assert.match(phoneGroups[0],/data-role="app-info" hidden/);
  for(const role of ["server-version","server-build","app-version","app-build"])
    assert.match(phoneGroups[0],new RegExp(`data-role="${role}">неизвестно<`));
  const controls=fs.readFileSync("src/ad_linux_tv/static/settings_controls.js","utf8");
  const about=controls.slice(controls.indexOf("  renderAbout() {"),controls.indexOf("  render(state"));
  assert.doesNotMatch(about,/innerHTML|fetch\(|request\(|setInterval|setTimeout|location|reload|userAgent|addEventListener/);
  assert.match(about,/window\.adLinuxTvAppInfo/);
});

test("both shared About templates wrap complete metadata without clipping or truncation",()=>{
  const tv=fs.readFileSync("src/ad_linux_tv/static/index.html","utf8");
  for(const source of [html,tv]){
    const group=source.match(/<details class="settings-control" data-role="about">[\s\S]*?<\/details>/);
    assert.ok(group,"shared About selector must match each actual template");
    for(const role of ["server-version","server-build","app-version","app-build"])
      assert.match(group[0],new RegExp(`data-role="${role}"`));
  }
  const rules=[...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)];
  const aboutRules=rules.filter(([,selector])=>selector.trim()==='.settings-control[data-role="about"]');
  assert.equal(aboutRules.length,1,"one About-only wrapping rule shared by phone and TV");
  assert.equal(aboutRules[0][2].trim(),"overflow-wrap:anywhere",
    "wrap all inherited metadata text; do not hide, clip, ellipsize, resize or truncate it");
});

test("phone and TV share the same site-view fields and ordering",()=>{
  const roles=source=>[...source.matchAll(/data-role="(view-[^"]+)"/g)].map(match=>match[1]);
  assert.deepEqual(roles(html),roles(tvHtml));
  for(const source of [html,tvHtml]) {
    assert.match(source,/value="common">Все сайты/);
    assert.match(source,/value="desktop">Обычный/);
    assert.match(source,/min="50" max="300" step="1" value="125"/);
    assert.match(source,/Как для всех сайтов|По умолчанию/);
  }
});

test("remaining literal phone selectors exist in actual HTML",()=>{
  const ids=new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]));
  for(const match of js.matchAll(/querySelector\("#([^" ]+)"\)/g))
    assert.ok(ids.has(match[1]),`Missing actual DOM: ${match[1]}`);
});

test("APK invitation is one compact optional MAIN link, with unchanged bound/native layout rules",()=>{
  const main=html.match(/<a class="remote-apk-main"[^>]*>[\s\S]*?<\/a>/g);
  assert.equal(main.length,1);
  assert.match(main[0],/data-apk-browser hidden data-no-wake/);
  assert.match(css,/\.remote-apk-main\{flex:none;min-height:28px;/);
  assert.match(css,/\.remote-face:has\(\.remote-apk-main:not\(\[hidden\]\)\)\{min-height:456px\}/);
  assert.match(css,/\.remote-main \.remote-top-actions \.remote-pill\{min-height:48px\}/);
  assert.doesNotMatch(js,/adLinuxTvAppInfo|download.*fetch|fetch.*download/);
  assert.doesNotMatch(js.slice(js.indexOf("function bootstrapPath")),/apkIsIos|apkPlatform|apkUserAgent|navigator/,
    "platform hints are limited to invitation presentation, never auth/binding/transport");
});

test("restored compact composition has no stacked redesign/container rules",()=>{
  assert.match(css,/\.remote-face\{height:calc\(100dvh - 70px/);
  assert.doesNotMatch(css,/container-type:inline-size|@container|\.remote-main \.remote-bottom\{display:grid/);
  assert.match(css,/\.remote-main \.remote-pad-wrap\{min-height:198px\}/);
  assert.match(css,/\.remote-main:has\(#remote-power\) \.remote-top-actions\{grid-template-columns:minmax\(0,1fr\) 70px 54px 62px\}/);
  assert.match(css,/\.remote-main:has\(#remote-power\) \.remote-top-actions\{grid-template-columns:minmax\(0,1fr\) 58px 48px 56px\}/);
  assert.doesNotMatch(css,/\.remote-main \.remote-top-actions\{grid-template-columns/);
  assert.match(css,/\.remote-main \.remote-page-head\{display:grid;grid-template-columns:minmax\(0,1fr\) var\(--remote-side-controls\)/);
  assert.match(css,/\.remote-main button\.remote-pressed\{transform:none\}/);
  assert.match(css,/\.remote-main \.remote-message\[data-error="true"\],\.remote-main \.remote-message\[data-notice="true"\]\{position:fixed!important/);
});
