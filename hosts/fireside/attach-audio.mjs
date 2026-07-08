import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({executablePath:'/usr/bin/google-chrome', headless:'new',
  userDataDir:'/home/frank/.openclaw/workspace/bin/fireside/profile',
  args:['--no-sandbox','--disable-dev-shm-usage','--window-size=1400,2200']});
const p = await b.newPage(); await p.setViewport({width:1400,height:2200});
await p.goto('https://app.fireside.fm/podcasts/beerwithgeeks/episodes/9c777adc-7fa8-4cc0-b145-dad7f0edfe5c/edit',{waitUntil:'networkidle2',timeout:45000});
const info = await p.evaluate(()=>{
  const audioEls=[...document.querySelectorAll('audio,source')].map(a=>a.src||a.currentSrc).filter(Boolean);
  const durText=(document.body.innerText.match(/Duration[:\s]*([0-9:]+)/i)||[])[1]||null;
  const dl=[...document.querySelectorAll('a')].map(a=>a.href).filter(h=>/\.mp3/i.test(h));
  const players=[...document.querySelectorAll('.audio-player__element,[class*=audio-player]')].map(e=>({cls:e.className,txt:(e.innerText||'').slice(0,60)}));
  return {audioSrcs:audioEls, durText, mp3Links:dl, players};
});
console.log(JSON.stringify(info,null,1));
await b.close();
