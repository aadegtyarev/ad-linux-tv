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

// A small fitted axis must not accept zero, the opposite sign, or a large
// relative error merely because it falls inside the usual absolute tolerance.
function videoGeometryAxisMatches(actual, expected) {
  return Number.isFinite(actual) && Number.isFinite(expected) && expected !== 0 &&
    Math.sign(actual) === Math.sign(expected) && Math.abs(actual-expected) <= 0.001 &&
    Math.abs(actual-expected) / Math.abs(expected) <= 0.01;
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

  function layout(video, styled = false, ignoreContainment = false) {
    try {
      const box = video.getBoundingClientRect();
      if (![box.left,box.top,box.right,box.bottom,box.width,box.height].every(Number.isFinite) ||
          box.width <= 0 || box.height <= 0) return {reason:"geometry_viewport"};
      const bounds={left:0,top:0,right:view.innerWidth,bottom:view.innerHeight};
      if (![bounds.right,bounds.bottom].every(value => Number.isFinite(value) && value > 0))
        return {reason:"geometry_viewport"};
      let containmentReason = box.left < 0 || box.top < 0 ||
        box.right > bounds.right || box.bottom > bounds.bottom ? "geometry_viewport" : null;
      if (!ignoreContainment && containmentReason) return {reason:containmentReason};
      let element = video, depth = 0;
      while (element) {
        if (++depth > 128) return {reason:"geometry_ancestor_style"};
        const s = styleOf(element);
        if (!s || s.visibility !== "visible" || s.display === "none" || Number(s.opacity) !== 1 ||
            !(normal(s.clip) || s.clip === "auto") || !normal(s.clipPath) ||
            !normal(s.maskImage) || !normal(s.webkitMaskImage) ||
            !normal(s.scale) || !normal(s.rotate) || !normal(s.translate)) return {reason:"geometry_ancestor_style"};
        if ((!styled || element !== video) && !identityTransform(s.transform))
          return {reason:element === video ? "geometry_video_transform" : "geometry_ancestor_style"};
        if ([s.borderTopLeftRadius,s.borderTopRightRadius,s.borderBottomLeftRadius,s.borderBottomRightRadius]
          .some(value => !zero(value))) return {reason:"geometry_ancestor_style"};
        if (element === video && [s.borderLeftWidth,s.borderRightWidth,s.borderTopWidth,s.borderBottomWidth,
          s.paddingLeft,s.paddingRight,s.paddingTop,s.paddingBottom].some(value => !zero(value))) return {reason:"geometry_ancestor_style"};
        // Common player wrappers use overflow:hidden. They are safe when the
        // whole transformed video remains inside their visible rectangle.
        if (element !== video && [s.overflowX,s.overflowY].some(value => value && value !== "visible")) {
          const parent = element.getBoundingClientRect();
          if (![parent.left,parent.top,parent.right,parent.bottom].every(Number.isFinite) ||
              parent.right <= parent.left || parent.bottom <= parent.top) return {reason:"geometry_clipping"};
          bounds.left=Math.max(bounds.left,parent.left);bounds.right=Math.min(bounds.right,parent.right);
          bounds.top=Math.max(bounds.top,parent.top);bounds.bottom=Math.min(bounds.bottom,parent.bottom);
          if (box.left < parent.left || box.right > parent.right || box.top < parent.top || box.bottom > parent.bottom) {
            containmentReason ||= "geometry_clipping";
            if (!ignoreContainment) return {reason:containmentReason};
          }
        }
        element = videoGeometryParent(element);
      }
      return {box,bounds,containmentReason};
    } catch (_) { return {reason:"geometry_ancestor_style"}; }
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
      const s = styleOf(session.video), matrix = matrixOf(s.transform), rect = layout(session.video,true).box;
      if (!rect) return "geometry_presentation_bounds";
      if (!matrix || matrix.is2D === false || /^matrix3d\(/.test(s.transform) || ![matrix.a,matrix.b,matrix.c,matrix.d,matrix.e,matrix.f].every(Number.isFinite) ||
          !videoGeometryAxisMatches(matrix.a,session.scale.x) || !videoGeometryAxisMatches(matrix.d,session.scale.y) ||
          Math.abs(matrix.b)>Math.min(0.001,Math.abs(session.scale.x)*0.01) ||
          Math.abs(matrix.c)>Math.min(0.001,Math.abs(session.scale.y)*0.01) || Math.abs(matrix.e)>0.001 ||
          Math.abs(matrix.f)>0.001 || (session.mode !== "original" && s.objectFit !== "fill")) return "geometry_presentation_matrix";
      const before = session.box;
      if (rect.width > before.width+2 || rect.height > before.height+2 ||
          Math.abs((rect.left+rect.right)-(before.left+before.right)) > 4 ||
          Math.abs((rect.top+rect.bottom)-(before.top+before.bottom)) > 4) return "geometry_presentation_bounds";
      return session.mode === "original" || Math.abs(rect.width/rect.height-VIDEO_RATIOS[session.mode]) <= 0.02 ? null : "geometry_presentation_ratio";
    } catch (_) { return "geometry_presentation_matrix"; }
  }

  async function reset(video,identity,isCurrent,deadline=Date.now()+1500) {
    return apply(video,identity,isCurrent,"original",false,deadline);
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
    if (!eligible(video,identity,isCurrent)) return {outcome:"unsupported",reason:"geometry_eligibility"};
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
      // Reset confirms only removal of our layer, not the site's resulting presentation.
      if (mode === "original" && !mirror) return {outcome:previous ? "restored" : "unchanged"};
      const preparationEnd=Math.min(deadline,Date.now()+700);
      while (true) {
        if (!valid()) return {outcome:"unsupported",reason:"geometry_eligibility"};
        const checked=layout(video,true,true);
        const state=transitionState(video);
        if (!checked.box) return {outcome:"unsupported",reason:checked.reason};
        if (state === "unsafe") return {outcome:"unsupported",reason:"geometry_transition"};
        if (state === "none") break;
        if (Date.now() >= preparationEnd || !await nextFrame(preparationEnd)) {
          if (!valid()) return {outcome:"unsupported",reason:"geometry_eligibility"};
          const checked=layout(video,true,true);
          const state=transitionState(video);
          if (!checked.box) return {outcome:"unsupported",reason:checked.reason};
          return state === "running" ?
            {outcome:"unsupported",reason:"transition_busy"} : {outcome:"unsupported",reason:"geometry_transition"};
        }
      }
      if (!valid()) return {outcome:"unsupported",reason:"geometry_eligibility"};
      const neutral = layout(video,false,true);
      if (!neutral.box) return {outcome:"unsupported",reason:neutral.reason};
      const box = neutral.box;
      if (!page.head) return {outcome:"unsupported"};
      let token;
      try { token = randomToken(); } catch (_) { return {outcome:"unsupported"}; }
      if (!/^[a-f0-9]{32}$/.test(token)) return {outcome:"unsupported"};
      const attribute = `data-ad-tv-geometry-${token}`;
      try { if (video.hasAttribute(attribute)) return {outcome:"unsupported"}; }
      catch (_) { return {outcome:"unsupported"}; }
      const scale = mode === "original" ? {x:mirror ? -1 : 1,y:1} :
        videoGeometryScale(box.width,box.height,VIDEO_RATIOS[mode],mirror);
      const centerX=box.left/2+box.right/2, centerY=box.top/2+box.bottom/2;
      const targetWidth=box.width*Math.abs(scale.x), targetHeight=box.height*scale.y;
      const {bounds}=neutral;
      let fit=Math.min(1,2*((centerX-bounds.left)/targetWidth),2*((bounds.right-centerX)/targetWidth),
        2*((centerY-bounds.top)/targetHeight),2*((bounds.bottom-centerY)/targetHeight));
      if (![centerX,centerY,targetWidth,targetHeight,fit].every(Number.isFinite) ||
          targetWidth <= 0 || targetHeight <= 0 || fit <= 0 ||
          !Number.isFinite(scale.x*fit) || !Number.isFinite(scale.y*fit) ||
          scale.x*fit === 0 || scale.y*fit <= 0)
        return {outcome:"unsupported",reason:neutral.containmentReason || "geometry_viewport"};
      // Leave room for floating-point and browser layout rounding at a limiting edge.
      if (fit < 1) fit*=1-1e-12;
      if (scale.x*fit === 0 || scale.y*fit <= 0)
        return {outcome:"unsupported",reason:neutral.containmentReason || "geometry_viewport"};
      scale.x*=fit;scale.y*=fit;
      const css = `video[${attribute}]{transform:scale(${scale.x},${scale.y}) !important;` +
        `transform-origin:center center !important;${mode === "original" ? "" : "object-fit:fill !important;"}}`;
      const session = {video,identity,isCurrent,mode,source:video.currentSrc,width:video.videoWidth,
        height:video.videoHeight,fullscreen:page.fullscreenElement,attribute,scale,box,layer:null,
        markerTouched:false,closed:false,closeCause:null,cleaned:false,cleaning:false,observer:null,timer:null,retryTimer:null,changed:null,sourceChanged:null};
      active=session;
      let confirming=true;
      try {
        session.layer=page.createElement("style");session.layer.textContent=css;
        const root=video.getRootNode();
        video.setAttribute(attribute,"");(root===page ? page.head : root).appendChild(session.layer);
        session.changed=() => {
          if (!current(session) || !markerOwned(session) || !session.layer.isConnected ||
              (!confirming && (transitionState(video) !== "none" || presentation(session)))) {
            if (!session.closed) session.closeCause="geometry_close_check";
            cleanup(session);
          }
        };
        session.sourceChanged=() => {
          if (!session.closed) session.closeCause="geometry_close_playback";
          cleanup(session);
        };
        session.observer=observe(video,record => {
          if (record?.attributeName===attribute) session.markerTouched=true;
          if (!session.closed) session.closeCause="geometry_close_mutation";
          cleanup(session);
        },attribute);
        for (const key of ["emptied","loadstart","ended"]) video.addEventListener(key,session.sourceChanged);
        page.addEventListener("visibilitychange",session.changed);
        page.addEventListener("fullscreenchange",session.changed);
        view.addEventListener("resize",session.changed);
        session.timer=setTimer(session.changed);
        const confirmationEnd=Math.min(deadline,Date.now()+700);
        while (true) {
          let failure;
          if (!await nextFrame(confirmationEnd)) failure="geometry_post_write_current";
          else if (!valid()) failure=session.closed && session.closeCause || "geometry_post_write_current";
          else if (session.closed) failure=session.closeCause || "geometry_post_write_closed";
          else if (active!==session || !markerOwned(session) || !session.layer.isConnected)
            failure="geometry_post_write_ownership";
          if (failure) return cleanup(session) ? {outcome:"unsupported",reason:failure} : {outcome:"uncertain"};
          let checked=layout(video,true);
          const state=transitionState(video,session.scale);
          if (["geometry_clipping","geometry_viewport"].includes(checked.reason) && state === "running") checked=layout(video,true,true);
          if (!checked.box) return cleanup(session) ? {outcome:"unsupported",reason:checked.reason} : {outcome:"uncertain"};
          if (state === "unsafe") return cleanup(session) ? {outcome:"unsupported",reason:"geometry_transition"} : {outcome:"uncertain"};
          if (state === "none") {
            const mismatch=presentation(session);
            if (mismatch) return cleanup(session) ? {outcome:"unsupported",reason:mismatch} : {outcome:"uncertain"};
            confirming=false;
            // This confirms computed style and geometry, not final decoded pixels or physical screen.
            return {outcome:"applied",token};
          }
          if (Date.now() >= confirmationEnd)
            return cleanup(session) ? {outcome:"unsupported",reason:"geometry_post_write_current"} : {outcome:"uncertain"};
        }
      } catch (_) {
        return cleanup(session) ? {outcome:"unsupported",reason:"geometry_post_write_exception"} : {outcome:"uncertain"};
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
          if (m.is2D !== true || ![m.a,m.b,m.c,m.d,m.e,m.f].every(Number.isFinite) ||
              !videoGeometryAxisMatches(m.a,expected.x) || !videoGeometryAxisMatches(m.d,expected.y) ||
              Math.abs(m.b)>Math.min(0.001,Math.abs(expected.x)*0.01) ||
              Math.abs(m.c)>Math.min(0.001,Math.abs(expected.y)*0.01) || Math.abs(m.e)>0.001 || Math.abs(m.f)>0.001)
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
