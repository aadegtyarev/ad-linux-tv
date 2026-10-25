"use strict";

// This function is serialized into the active service tab by scripting.executeScript.
function playerMediaVolume(mode, requested) {
  const media = [...document.querySelectorAll("audio,video")]
    .filter(element => !element.paused && !element.ended &&
      (mode === "pause" || !element.muted));
  if (!media.length) return null;
  if (mode === "pause") {
    const volume = Math.round(media[0].volume * 100);
    for (const element of media) element.pause();
    return volume;
  }
  if (mode === "set") {
    if (!Number.isInteger(requested) || requested < 0 || requested > 100) return null;
    document.__adLinuxTvVolumeTarget = requested / 100;
    for (const element of media) element.volume = requested / 100;
  }
  return Math.round(media[0].volume * 100);
}

// Inject only into a launcher-owned service tab. Leave the user's output volume alone.
function pinMediaVolume(requested = 100) {
  if (!Number.isInteger(requested) || requested < 0 || requested > 100) return false;
  document.__adLinuxTvVolumeTarget = requested / 100;
  if (document.__adLinuxTvVolumePinned) {
    for (const element of document.querySelectorAll("audio,video"))
      if (!element.paused && !element.ended) element.volume = document.__adLinuxTvVolumeTarget;
    return true;
  }
  document.__adLinuxTvVolumePinned = true;
  const normalize = element => {
    if (element && ["audio", "video"].includes(element.localName) &&
        !element.paused && !element.ended && element.volume !== document.__adLinuxTvVolumeTarget)
      element.volume = document.__adLinuxTvVolumeTarget;
  };
  document.addEventListener("play", event => normalize(event.target), true);
  document.addEventListener("volumechange", event => normalize(event.target), true);
  for (const element of document.querySelectorAll("audio,video"))
    if (!element.paused && !element.ended) normalize(element);
  return true;
}

if (typeof module !== "undefined") module.exports = {playerMediaVolume, pinMediaVolume};
