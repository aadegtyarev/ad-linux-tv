browser.runtime.onMessage.addListener(({command}) => {
  const map={up:"ArrowUp",down:"ArrowDown",left:"ArrowLeft",right:"ArrowRight",ok:"Enter"};
  if(map[command])document.dispatchEvent(new KeyboardEvent("keydown",{key:map[command],bubbles:true}));
});
