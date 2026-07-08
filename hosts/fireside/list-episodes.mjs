import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({
  executablePath: '/usr/bin/google-chrome', headless: 'new',
  userDataDir: '/home/frank/.openclaw/workspace/bin/fireside/profile',
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1400,2200'],
});
const p = await b.newPage();
await p.setViewport({ width: 1400, height: 2200 });
await p.goto('https://app.fireside.fm/podcasts/beerwithgeeks/episodes', { waitUntil: 'networkidle2', timeout: 45000 });

// Visit the first ~8 edit pages to read slug/title/status reliably.
const editUrls = await p.evaluate(() =>
  [...new Set([...document.querySelectorAll('a')]
    .map(a => a.href)
    .filter(h => /\/episodes\/[0-9a-f-]{36}\/edit/.test(h)))].slice(0, 8)
);

const rows = [];
for (const u of editUrls) {
  await p.goto(u, { waitUntil: 'networkidle2', timeout: 45000 });
  const r = await p.evaluate(() => {
    const g = id => document.getElementById(id);
    const sel = el => el ? (el.options ? el.options[el.selectedIndex]?.text : el.value) : null;
    return {
      slug: g('episode_slug')?.value,
      title: g('episode_title')?.value,
      status: sel(g('episode_status')),
      hasDesc: (g('episode_description')?.value || '').replace(/\s|\*|Beers of the Week/g, '').length > 5,
    };
  });
  r.url = u;
  rows.push(r);
}
rows.sort((a, b) => Number(a.slug) - Number(b.slug));
console.log(JSON.stringify(rows, null, 1));
await b.close();
