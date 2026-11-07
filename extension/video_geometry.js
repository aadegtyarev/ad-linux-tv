"use strict";

(() => {
// Firefox keeps one isolated extension global per frame. Re-injection must
// preserve the active controller and must not redeclare top-level bindings.
if (typeof module === "undefined" && globalThis.__adLinuxTvVideoGeometry) return;

// Every environment callback is provided by trusted extension code, never a client.
const VIDEO_RATIOS = Object.freeze({"4:3":4 / 3, "16:9":16 / 9});

function videoGeometryParent(node) {
  return node.parentElement || node.getRootNode?.().host || null;
}

function videoGeometryScale(width, height, ratio, mirror) {
  if (![width,height,ratio].every(value => Number.isFinite(value) && value > 0) ||
      typeof mirror !== "boolean") throw new Error("invalid geometry");
  const current = width / height;
  const x = Math.min(1, ratio / current), y = Math.min(1, current / ratio);
  return {x:mirror ? -x : x,y};
}

function createVideoGeometryController(env) {
  const {page, view, styleOf, matrixOf, afterFrame, randomToken, observe, setTimer, clearTimer} = env;
  let active = null, revision = 0;
  const zero = value => !value || Number.parseFloat(value) === 0;
  const normal = value => !value || value === "none" || value === "normal";
  function identityTransform(value) {
    if (normal(value)) return true;
    try {
      if (!/^matrix\(/.test(value)) return false;
      const m = matrixOf(value);
      return m.is2D !== false && m.a === 1 && m.b === 0 && m.c === 0 &&
        m.d === 1 && m.e === 0 && m.f === 0;
    } catch (_) { return false; }
  }

  // Only a running, finite CSS transform transition on the video is waitable.
  // Other transform animations, including those on ancestors, are ambiguous.
  function transitionState(video, expected = null) {
    try {
      let node=video, depth=0, running=false;
      while (node) {
        if (++depth > 128) return "unsafe";
        const state = env.transformTransitions(node, node === video ? expected : null);
        if (state === "unsafe" || (node !== video && state === "running")) return "unsafe";
        if (state === "running") running=true;
        else if (state !== "none") return "unsafe";
        node=videoGeometryParent(node);
      }
      return running ? "running" : "none";
    } catch (_) { return "unsafe"; }
  }

  async function nextFrame(until) {
    const delay=Math.max(0, until-Date.now());
    let timer;
    try {
      return await Promise.race([afterFrame().then(() => true),
        new Promise(resolve => {timer=setTimeout(() => resolve(false),delay);})]);
    } finally { clearTimeout(timer); }
  }

  function eligible(video, identity, isCurrent) {
    try {
      const root = video?.getRootNode();
      if (!video?.isConnected || video.tagName !== "VIDEO" || page.hidden || video.ownerDocument !== page ||
          !(root === page || root?.mode === "open" || root?.mode === "closed") ||
          !video.currentSrc || !video.videoWidth || !video.videoHeight ||
          video.srcObject || video.mediaKeys || video.controls || page.fullscreenElement === video ||
          Array.from(video.textTracks || []).some(track => track.mode === "showing") ||
          !isCurrent(video, identity)) return false;
      if (!page.fullscreenElement) return true;
      for (let node=videoGeometryParent(video); node; node=videoGeometryParent(node))
        if (node === page.fullscreenElement) return true;
      return false;
    } catch (_) { return false; }
  }

  function layout(video, styled = false) {
    try {
      const box = video.getBoundingClientRect();
      if (![box.left,box.top,box.right,box.bottom,box.width,box.height].every(Number.isFinite) ||
          box.width <= 0 || box.height <= 0 || box.left < 0 || box.top < 0 ||
          box.right > view.innerWidth || box.bottom > view.innerHeight) return null;
      let element = video, depth = 0;
      while (element) {
        if (++depth > 128) return null;
        const s = styleOf(element);
        if (!s || s.visibility !== "visible" || s.display === "none" || Number(s.opacity) !== 1 ||
            !(normal(s.clip) || s.clip === "auto") || !normal(s.clipPath) ||
            !normal(s.maskImage) || !normal(s.webkitMaskImage) ||
            !normal(s.scale) || !normal(s.rotate) || !normal(s.translate) ||
            ((!styled || element !== video) && !identityTransform(s.transform))) return null;
        if ([s.borderTopLeftRadius,s.borderTopRightRadius,s.borderBottomLeftRadius,s.borderBottomRightRadius]
          .some(value => !zero(value))) return null;
        if (element === video && [s.borderLeftWidth,s.borderRightWidth,s.borderTopWidth,s.borderBottomWidth,
          s.paddingLeft,s.paddingRight,s.paddingTop,s.paddingBottom].some(value => !zero(value))) return null;
        // Common player wrappers use overflow:hidden. They are safe when the
        // whole transformed video remains inside their visible rectangle.
        if (element !== video && [s.overflowX,s.overflowY].some(value => value && value !== "visible")) {
          const parent = element.getBoundingClientRect();
          if (box.left < parent.left || box.right > parent.right ||
              box.top < parent.top || box.bottom > parent.bottom) return null;
        }
        element = videoGeometryParent(element);
      }
      return box;
    } catch (_) { return null; }
  }

  function current(session) {
    return eligible(session.video,session.identity,session.isCurrent) &&
      session.video.currentSrc === session.source && session.video.videoWidth === session.width &&
      session.video.videoHeight === session.height && page.fullscreenElement === session.fullscreen;
  }

  function markerOwned(session) {
    return !session.markerTouched && session.video.getAttribute(session.attribute) === "";
  }

  function cleanup(session) {
    if (!session || session.cleaned) return true;
    if (session.cleaning) return false;
    session.cleaning = true;
    session.closed = true;
    let clean = true;
    const attempt = fn => { try { fn(); } catch (_) { clean = false; } };
    // Take pending records before disconnect so an identical newer marker write is not lost.
    attempt(() => { if (session.observer?.takeRecords().some(r => r.attributeName === session.attribute)) session.markerTouched = true; });
    attempt(() => session.observer?.disconnect());
    attempt(() => { if (session.timer !== null) clearTimer(session.timer); });
    for (const key of ["emptied","loadstart","ended"]) attempt(() => session.video.removeEventListener(key,session.sourceChanged));
    attempt(() => page.removeEventListener("visibilitychange",session.changed));
    attempt(() => page.removeEventListener("fullscreenchange",session.changed));
    attempt(() => view.removeEventListener("resize",session.changed));
    // The style node and marker are feature-owned; inline styles are never read for restore or changed.
    attempt(() => session.layer?.remove());
    attempt(() => { if (markerOwned(session)) session.video.removeAttribute(session.attribute); });
    if (clean && session.retryTimer !== null) attempt(() => { clearTimer(session.retryTimer);session.retryTimer=null; });
    if (clean) {
      session.cleaned = true;
      if (active === session) active = null;
    } else if (session.retryTimer === null) {
      // Retry internally even if the target is no longer eligible or reachable by a caller.
      attempt(() => { session.retryTimer=setTimer(() => cleanup(session)); });
    }
    session.cleaning = false;
    return clean;
  }

  function presentation(session) {
    try {
      const s = styleOf(session.video), matrix = matrixOf(s.transform), rect = layout(session.video,true);
      if (!rect || !matrix || matrix.is2D === false || /^matrix3d\(/.test(s.transform) || ![matrix.a,matrix.b,matrix.c,matrix.d,matrix.e,matrix.f].every(Number.isFinite) ||
          Math.abs(matrix.a-session.scale.x)>0.001 || Math.abs(matrix.d-session.scale.y)>0.001 ||
          Math.abs(matrix.b)>0.001 || Math.abs(matrix.c)>0.001 || Math.abs(matrix.e)>0.001 ||
          Math.abs(matrix.f)>0.001 || (session.mode !== "original" && s.objectFit !== "fill")) return false;
      const before = session.box;
      if (rect.width > before.width+2 || rect.height > before.height+2 ||
          Math.abs((rect.left+rect.right)-(before.left+before.right)) > 4 ||
          Math.abs((rect.top+rect.bottom)-(before.top+before.bottom)) > 4) return false;
      return session.mode === "original" || Math.abs(rect.width/rect.height-VIDEO_RATIOS[session.mode]) <= 0.02;
    } catch (_) { return false; }
  }

  async function reset(video,identity,isCurrent,deadline=Date.now()+1500) {
    const hadActive=Boolean(active);
    const result=await apply(video,identity,isCurrent,"original",false,deadline);
    return !hadActive && result.outcome === "restored" ? {outcome:"unchanged"} : result;
  }

  function cancel(identity,token) {
    if (!active || active.identity !== identity || active.attribute !== `data-ad-tv-geometry-${token}`)
      return {outcome:"unchanged"};
    revision++;
    return {outcome:cleanup(active) ? "restored" : "uncertain"};
  }

  async function apply(video,identity,isCurrent,mode,mirror,deadline=Date.now()+1500) {
    if ((!Object.hasOwn(VIDEO_RATIOS,mode) && mode !== "original") || typeof mirror !== "boolean" ||
        typeof isCurrent !== "function") return {outcome:"invalid"};
    // Reject a stale request before touching an existing session on another target.
    if (!eligible(video,identity,isCurrent)) return {outcome:"unsupported"};
    if (active && (active.video !== video || active.identity !== identity) && current(active))
      return {outcome:"stale"};
    const ticket=++revision;
    const snapshot={video,identity,isCurrent,source:video.currentSrc,width:video.videoWidth,
      height:video.videoHeight,fullscreen:page.fullscreenElement};
    let playbackChanged=false;
    const invalidatePlayback=() => { playbackChanged=true; };
    const playbackEvents=["emptied","loadstart","ended"];
    const registered=[];
    try {
      for (const event of playbackEvents) {
        video.addEventListener(event,invalidatePlayback);
        registered.push(event);
      }
    } catch (_) {
      for (const event of registered) video.removeEventListener(event,invalidatePlayback);
      return {outcome:"unsupported"};
    }
    const valid=() => !playbackChanged && ticket===revision && Date.now()<=deadline && current(snapshot);
    try {
      // The prior target can be retired only after the new target is verified and
      // the prior session is no longer current. Cleanup is confined to that session.
      const previous=active;
      if (previous && !cleanup(previous)) return {outcome:"uncertain"};
      if (!valid()) return {outcome:"stale"};
      const preparationEnd=Math.min(deadline,Date.now()+700);
      while (true) {
        if (!valid() || !layout(video,true)) return {outcome:"unsupported"};
        const state=transitionState(video);
        if (state === "unsafe") return {outcome:"unsupported"};
        if (state === "none") break;
        if (Date.now() >= preparationEnd || !await nextFrame(preparationEnd)) {
          if (!valid() || !layout(video,true)) return {outcome:"unsupported"};
          return transitionState(video) === "running" ?
            {outcome:"unsupported",reason:"transition_busy"} : {outcome:"unsupported"};
        }
      }
      if (!valid()) return {outcome:"unsupported"};
      const box = layout(video);
      if (!box) return {outcome:"unsupported"};
      if (mode === "original" && !mirror) return {outcome:"restored"};
      if (!page.head) return {outcome:"unsupported"};
      let token;
      try { token = randomToken(); } catch (_) { return {outcome:"unsupported"}; }
      if (!/^[a-f0-9]{32}$/.test(token)) return {outcome:"unsupported"};
      const attribute = `data-ad-tv-geometry-${token}`;
      try { if (video.hasAttribute(attribute)) return {outcome:"unsupported"}; }
      catch (_) { return {outcome:"unsupported"}; }
      const scale = mode === "original" ? {x:mirror ? -1 : 1,y:1} :
        videoGeometryScale(box.width,box.height,VIDEO_RATIOS[mode],mirror);
      const css = `video[${attribute}]{transform:scale(${scale.x},${scale.y}) !important;` +
        `transform-origin:center center !important;${mode === "original" ? "" : "object-fit:fill !important;"}}`;
      const session = {video,identity,isCurrent,mode,source:video.currentSrc,width:video.videoWidth,
        height:video.videoHeight,fullscreen:page.fullscreenElement,attribute,scale,box,layer:null,
        markerTouched:false,closed:false,cleaned:false,cleaning:false,observer:null,timer:null,retryTimer:null,changed:null,sourceChanged:null};
      active=session;
      let confirming=true;
      try {
        session.layer=page.createElement("style");session.layer.textContent=css;
        const root=video.getRootNode();
        video.setAttribute(attribute,"");(root===page ? page.head : root).appendChild(session.layer);
        session.changed=() => {
          if (!current(session) || !markerOwned(session) || !session.layer.isConnected ||
              (!confirming && (transitionState(video) !== "none" || !presentation(session))))
            cleanup(session);
        };
        session.sourceChanged=() => cleanup(session);
        session.observer=observe(video,record => {
          if (record?.attributeName===attribute) session.markerTouched=true;
          cleanup(session);
        },attribute);
        for (const key of ["emptied","loadstart","ended"]) video.addEventListener(key,session.sourceChanged);
        page.addEventListener("visibilitychange",session.changed);
        page.addEventListener("fullscreenchange",session.changed);
        view.addEventListener("resize",session.changed);
        session.timer=setTimer(session.changed);
        const confirmationEnd=Math.min(deadline,Date.now()+700);
        while (true) {
          if (!await nextFrame(confirmationEnd) || !valid() || session.closed || active!==session ||
              !markerOwned(session) || !session.layer.isConnected || !layout(video,true)) {
            return {outcome:cleanup(session) ? "unsupported" : "uncertain"};
          }
          const state=transitionState(video,session.scale);
          if (state === "unsafe") return {outcome:cleanup(session) ? "unsupported" : "uncertain"};
          if (state === "none") {
            if (!presentation(session)) return {outcome:cleanup(session) ? "unsupported" : "uncertain"};
            confirming=false;
            // This confirms computed style and geometry, not final decoded pixels or physical screen.
            return {outcome:"applied",token};
          }
          if (Date.now() >= confirmationEnd)
            return {outcome:cleanup(session) ? "unsupported" : "uncertain"};
        }
      } catch (_) {
        return {outcome:cleanup(session) ? "unsupported" : "uncertain"};
      }
    } finally {
      for (const event of registered) video.removeEventListener(event,invalidatePlayback);
    }
  }
  return {apply,reset,cancel};
}

// Observe only the chosen video, never unrelated page contents. A bounded
// periodic check covers changes to ancestor styles and visibility.
function createVideoGeometryEnvironment(page,view) {
  return {
    page,view,
    styleOf:(element,pseudo) => view.getComputedStyle(element,pseudo || null),
    matrixOf:value => new view.DOMMatrixReadOnly(value),
    transformTransitions:(element,expected) => {
      if (typeof element.getAnimations !== "function") return "unsafe";
      let running=false;
      for (const animation of element.getAnimations()) {
        const effect=animation.effect;
        if (!effect || effect.target !== element || typeof effect.getKeyframes !== "function") return "unsafe";
        const frames=effect.getKeyframes();
        if (!Array.isArray(frames)) return "unsafe";
        if (!frames.some(frame => ["transform","translate","rotate","scale"].some(key => key in frame))) continue;
        const timing=effect.getComputedTiming();
        if (!(typeof view.CSSTransition === "function" && animation instanceof view.CSSTransition) ||
            animation.transitionProperty !== "transform" || animation.playState !== "running" ||
            !Number.isFinite(animation.playbackRate) || animation.playbackRate <= 0 ||
            !Number.isFinite(timing.endTime) || !Number.isFinite(timing.activeDuration) ||
            timing.endTime <= 0 || timing.activeDuration <= 0) return "unsafe";
        if (running) return "unsafe";
        if (expected) {
          const end=frames[frames.length-1];
          if (!end || typeof end.transform !== "string" ||
              ["translate","rotate","scale"].some(key => key in end)) return "unsafe";
          const m=end.transform === "none" ? new view.DOMMatrixReadOnly() : new view.DOMMatrixReadOnly(end.transform);
          if (m.is2D !== true || Math.abs(m.a-expected.x)>0.001 || Math.abs(m.d-expected.y)>0.001 ||
              Math.abs(m.b)>0.001 || Math.abs(m.c)>0.001 || Math.abs(m.e)>0.001 || Math.abs(m.f)>0.001)
            return "unsafe";
        }
        running=true;
      }
      return running ? "running" : "none";
    },
    afterFrame:() => new Promise(resolve => view.requestAnimationFrame(resolve)),
    randomToken:() => [...view.crypto.getRandomValues(new Uint8Array(16))]
      .map(value => value.toString(16).padStart(2,"0")).join(""),
    observe:(video,callback,marker) => {
      const observer=new view.MutationObserver(records => { for (const record of records) callback(record); });
      observer.observe(video,{attributes:true,attributeFilter:["style","class","src",marker]});
      return observer;
    },
    // Video mutations and window resize events are observed immediately. The periodic
    // fallback must stay cheap on video-heavy pages rather than scan the whole
    // document ten times a second throughout playback.
    setTimer:callback => view.setInterval(callback,1000),
    clearTimer:timer => view.clearInterval(timer),
  };
}

// Only the selected frame's existing, opaque media identity may be targeted.
// Never pass a URL, selector or arbitrary CSS from a phone to this boundary.
function createVideoGeometryCommand(page, view, makeController = createVideoGeometryController) {
  const controller = makeController(createVideoGeometryEnvironment(page, view));
  const command = async (mediaId, mode, mirror, deadline) => {
    if (!/^[0-9a-f]{32}$/.test(mediaId || "") ||
        !["original", "4:3", "16:9"].includes(mode) || typeof mirror !== "boolean" ||
        !Number.isSafeInteger(deadline) || Date.now() > deadline || deadline > Date.now() + 6000)
      return {outcome:"unsupported"};
    const registry = page.__adLinuxTvTiming;
    if (!registry?.items || typeof registry.items.get !== "function") return {outcome:"unsupported"};
    const video = registry.last;
    if (!video || registry.items.get(video)?.id !== mediaId) return {outcome:"unsupported"};
    const isSame = (target, identity) => {
      const record = registry.items.get(target);
      return target === video && registry.last === target && identity === mediaId && record?.id === mediaId &&
        record.fingerprint === `${target.currentSrc}\n${target.duration}`;
    };
    // A late dispatched request may not create or retain an effect after its
    // deadline, but an already confirmed session remains until the source ends.
    let confirmed = false;
    const current = (target, identity) => isSame(target, identity) &&
      (confirmed || Date.now() <= deadline);
    if (!current(video, mediaId)) return {outcome:"unsupported"};
    const result = await controller.apply(video, mediaId, current, mode, mirror, deadline);
    if (Date.now() > deadline && ["applied", "restored", "unchanged"].includes(result.outcome)) {
      if (result.outcome === "applied") controller.cancel(mediaId, result.token);
      return {outcome:"uncertain"};
    }
    confirmed = result.outcome === "applied";
    return result;
  };
  command.cancel = (mediaId,token) => /^[0-9a-f]{32}$/.test(token || "") ?
    controller.cancel(mediaId,token) : {outcome:"unsupported"};
  return command;
}

if (typeof module !== "undefined") {
  module.exports={videoGeometryScale,createVideoGeometryController,createVideoGeometryEnvironment,
    createVideoGeometryCommand};
} else {
  globalThis.__adLinuxTvVideoGeometry = createVideoGeometryCommand(document, window);
}
})();
