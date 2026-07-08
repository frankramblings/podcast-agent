// BwG 567 — Fireside create + fill + schedule (2026-07-15 05:00 AM ET), all in one puppeteer session.
// Uses profile-567 (isolated). Requires FS_EMAIL and FS_PASS in env.
import puppeteer from 'puppeteer-core';
import fs from 'fs';

const EMAIL = process.env.FS_EMAIL, PASS = process.env.FS_PASS;
if (!EMAIL || !PASS) { console.error('missing FS_EMAIL/FS_PASS'); process.exit(2); }

const PROFILE = '/home/frank/.openclaw/workspace/bin/fireside/profile-567';
const MP3     = '/home/frank/.openclaw/workspace/bin/fireside/bwg567.mp3';
const CONTENT = JSON.parse(fs.readFileSync('/home/frank/.openclaw/workspace/bin/fireside/content567.json', 'utf8'));
const SHOTS   = '/home/frank/.openclaw/workspace/bin/fireside';
const SLUG    = '567';
// Publish target: 2026-07-15 05:00 AM America/New_York
const PUB = { y: '2026', mo: 'july', d: '15', h: '05', mi: '00' };

const b = await puppeteer.launch({
  executablePath: '/usr/bin/google-chrome',
  headless: 'new',
  userDataDir: PROFILE,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1400,2400'],
});
const p = await b.newPage();
await p.setViewport({ width: 1400, height: 2400 });
p.on('dialog', d => d.accept());

console.log('→ login');
await p.goto('https://app.fireside.fm/login', { waitUntil: 'networkidle2', timeout: 45000 });
if (p.url().includes('/login')) {
  await p.type('#email', EMAIL, { delay: 10 });
  await p.type('#password', PASS, { delay: 10 });
  await Promise.all([
    p.waitForNavigation({ waitUntil: 'networkidle2', timeout: 45000 }),
    p.click('button[type=submit]'),
  ]);
}
if (p.url().includes('/login')) {
  const err = await p.evaluate(() => document.querySelector('.alert, .flash, [role=alert]')?.innerText?.slice(0,200));
  console.error('login failed:', err); await b.close(); process.exit(1);
}
await p.screenshot({ path: `${SHOTS}/567-login.png` });

// --- Check if 567 draft already exists ---
console.log('→ scanning episode list for slug 567');
await p.goto('https://app.fireside.fm/podcasts/beerwithgeeks/episodes', { waitUntil: 'networkidle2', timeout: 60000 });
let editUrls = await p.evaluate(() => [...new Set([...document.querySelectorAll('a')]
  .map(a => a.href).filter(h => /\/episodes\/[0-9a-f-]{36}\/edit/.test(h)))]);
let editUrl = null;
for (const u of editUrls) {
  await p.goto(u, { waitUntil: 'networkidle2', timeout: 45000 });
  const info = await p.evaluate(() => ({
    slug: document.getElementById('episode_slug')?.value || '',
    title: document.getElementById('episode_title')?.value || '',
  }));
  if (info.slug === SLUG) { editUrl = u; console.log('✓ found existing 567 draft:', u); break; }
}

// --- Create if not found ---
if (!editUrl) {
  console.log('→ creating new draft with slug 567');
  await p.goto('https://app.fireside.fm/podcasts/beerwithgeeks/episodes/new', { waitUntil: 'networkidle2', timeout: 60000 });
  await p.evaluate((slug) => {
    const g = id => document.getElementById(id);
    g('episode_title').value = 'Untitled Episode'; g('episode_title').dispatchEvent(new Event('input', { bubbles: true }));
    g('episode_slug').value = slug; g('episode_slug').dispatchEvent(new Event('input', { bubbles: true }));
    const s = g('episode_status');
    for (const o of s.options) { if (/private/i.test(o.text)) { s.value = o.value; } }
    s.dispatchEvent(new Event('change', { bubbles: true }));
    document.querySelectorAll('input[name="episode[host_ids][]"]').forEach(cb => { if (['524','525'].includes(cb.value)) cb.checked = true; });
  }, SLUG);
  await Promise.all([
    p.waitForNavigation({ waitUntil: 'networkidle2', timeout: 90000 }).catch(() => {}),
    p.click('#episode_form_submit_button'),
  ]);
  editUrl = p.url().includes('/edit') ? p.url() : `${p.url().replace(/\/$/, '')}/edit`;
  console.log('→ created:', editUrl);
}

await p.goto(editUrl, { waitUntil: 'networkidle2', timeout: 60000 });

// --- Fill fields ---
const setVal = (id, val) => p.evaluate((id, val) => {
  const el = document.getElementById(id); if (!el) return false;
  el.value = val;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  el.dispatchEvent(new Event('blur', { bubbles: true }));
  return true;
}, id, val);

await setVal('episode_title', CONTENT.title);
await setVal('episode_subtitle', CONTENT.subtitle);
await setVal('episode_keywords', CONTENT.keywords);
await setVal('episode_tag_list', CONTENT.tag_list);

const setDesc = (text) => p.evaluate((text) => {
  const cm = document.querySelector('.CodeMirror');
  if (cm && cm.CodeMirror) { cm.CodeMirror.setValue(text); cm.CodeMirror.save(); }
  const ta = document.getElementById('episode_description');
  if (ta) { ta.value = text; ta.dispatchEvent(new Event('input', { bubbles: true })); }
}, text);
await setDesc(CONTENT.description);
await new Promise(r => setTimeout(r, 1500));

// --- Audio upload ---
console.log('→ uploading mp3');
const mp3Input = await p.$('#mp3_upload_url');
if (mp3Input) await mp3Input.uploadFile(MP3);
const t0 = Date.now();
let audioOk = false;
while (Date.now() - t0 < 600000) {
  const v = await p.evaluate(() => document.getElementById('episode_mp3_upload_url')?.value || '');
  if (v && v.length > 5) { console.log('✓ audio uploaded:', v.slice(0, 60)); audioOk = true; break; }
  await new Promise(r => setTimeout(r, 3000));
}
if (!audioOk) { console.error('❌ audio upload timed out'); }

// --- Re-verify description (Fireside sometimes clears CM on upload) ---
const descCheck = await p.evaluate(() => document.querySelector('.CodeMirror')?.CodeMirror?.getValue?.() || '');
if (descCheck.length < 100) { console.log('→ re-setting description'); await setDesc(CONTENT.description); await new Promise(r => setTimeout(r, 1000)); }

// --- Save draft ---
await p.screenshot({ path: `${SHOTS}/567-before-save.png`, fullPage: true });
console.log('→ saving draft');
await Promise.all([
  p.waitForNavigation({ waitUntil: 'networkidle2', timeout: 120000 }).catch(() => {}),
  p.click('#episode_form_submit_button'),
]);
await new Promise(r => setTimeout(r, 2500));
await p.goto(editUrl, { waitUntil: 'networkidle2', timeout: 60000 });

// --- Schedule: Public + 2026-07-15 05:00 ---
const pick = (id, matchText, matchVal) => p.evaluate((id, mt, mv) => {
  const s = document.getElementById(id);
  for (const o of s.options) {
    if ((mt && o.text.trim().toLowerCase().startsWith(mt)) || (mv && o.value === mv)) { s.value = o.value; break; }
  }
  s.dispatchEvent(new Event('change', { bubbles: true }));
  return s.options[s.selectedIndex]?.text;
}, id, matchText, matchVal);

console.log('→ setting schedule 2026-07-15 05:00 AM ET');
await pick('episode_status', 'public', null);
await pick('episode_publish_at_1i', null, PUB.y);
await pick('episode_publish_at_2i', PUB.mo, null);
await pick('episode_publish_at_3i', null, PUB.d);
await pick('episode_publish_at_4i', null, PUB.h);
await pick('episode_publish_at_5i', null, PUB.mi);

const pre = await p.evaluate(() => {
  const g = id => { const s = document.getElementById(id); return s?.options[s.selectedIndex]?.text; };
  return { status: g('episode_status'), y: g('episode_publish_at_1i'), mo: g('episode_publish_at_2i'),
    d: g('episode_publish_at_3i'), h: g('episode_publish_at_4i'), mi: g('episode_publish_at_5i') };
});
console.log('PRE-SUBMIT:', JSON.stringify(pre));
const ok = pre.status === 'Public' && pre.y === '2026' && /july/i.test(pre.mo) && pre.d === '15' && /05 AM/.test(pre.h) && pre.mi === '00';
if (!ok) { console.error('❌ selections do not match intent — aborting publish'); await b.close(); process.exit(1); }

await Promise.all([
  p.waitForNavigation({ waitUntil: 'networkidle2', timeout: 90000 }).catch(() => {}),
  p.click('#episode_form_submit_button'),
]);
await new Promise(r => setTimeout(r, 2000));
await p.goto(editUrl, { waitUntil: 'networkidle2', timeout: 60000 });

const post = await p.evaluate(() => {
  const g = id => { const s = document.getElementById(id); return s ? s.options[s.selectedIndex]?.text : null; };
  const banner = (document.body.innerText.match(/schedul[^\n.]{0,60}|will be published[^\n.]{0,60}/i) || [])[0] || null;
  return { status: g('episode_status'), y: g('episode_publish_at_1i'), mo: g('episode_publish_at_2i'),
    d: g('episode_publish_at_3i'), h: g('episode_publish_at_4i'), mi: g('episode_publish_at_5i'), banner };
});
console.log('POST-SUBMIT:', JSON.stringify(post));
await p.screenshot({ path: `${SHOTS}/567-scheduled.png`, fullPage: true });
console.log('✅ DONE — draft:', editUrl.replace('/edit', ''));
await b.close();
