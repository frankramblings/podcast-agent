import puppeteer from 'puppeteer-core';
const EXPECT = [
  ["9c777adc-7fa8-4cc0-b145-dad7f0edfe5c","565","Supergirl (today)"],
  ["ede6e180-639d-4cb7-9e09-02d28a59a67c","566","Winter Lager (restored)"],
  ["ad5e4e35-fea5-40ba-a8a2-9d9e6b064a66","567","Goofy Batman"],
  ["11674cfe-d916-4dbc-ad22-9b469a15cfdc","568","Saturday Morning Boy Child"],
  ["c85c24c6-7a44-4f18-9c16-0a71a18b378f","569","orig-568 Untitled"],
  ["72bf28ec-2b92-439d-8580-7678a46dd921","570","orig-569 Untitled"],
];
const b = await puppeteer.launch({executablePath:'/usr/bin/google-chrome', headless:'new',
  userDataDir:'/home/frank/.openclaw/workspace/bin/fireside/profile',
  args:['--no-sandbox','--disable-dev-shm-usage','--window-size=1400,2200']});
const p = await b.newPage(); await p.setViewport({width:1400,height:2200});
let allok=true;
for (const [uuid,exp,label] of EXPECT){
  await p.goto(`https://app.fireside.fm/podcasts/beerwithgeeks/episodes/${uuid}/edit`,{waitUntil:'networkidle2',timeout:60000});
  const r=await p.evaluate(()=>{const g=id=>document.getElementById(id);const s=g('episode_status');
    return {slug:g('episode_slug')?.value, title:g('episode_title')?.value,
      status:s?s.options[s.selectedIndex].text:null,
      audio:!!document.querySelector('.fa-file-audio, a[href*=".mp3"]')};});
  const ok = r.slug===exp;
  allok = allok && ok;
  console.log(`${ok?'✓':'✗'} ${exp} (${label}): slug=${r.slug} status=${r.status} audio=${r.audio} title="${r.title}"`);
}
console.log(allok?'ALL CORRECT':'MISMATCH — CHECK');
await b.close();
