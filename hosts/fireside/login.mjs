// Fireside login → dashboard recon.
// Creds arrive via env (FS_EMAIL/FS_PASS) piped from `op read` in the calling
// shell, so they never touch disk or logs. Persistent profile keeps the session
// alive across subsequent steps.
import puppeteer from 'puppeteer-core';

const EMAIL = process.env.FS_EMAIL, PASS = process.env.FS_PASS;
if (!EMAIL || !PASS) { console.error('missing FS_EMAIL/FS_PASS'); process.exit(2); }

const b = await puppeteer.launch({
  executablePath: '/usr/bin/google-chrome',
  headless: 'new',
  userDataDir: '/home/frank/.openclaw/workspace/bin/fireside/profile',
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1400,1900'],
});
const p = await b.newPage();
await p.setViewport({ width: 1400, height: 1900 });

await p.goto('https://app.fireside.fm/login', { waitUntil: 'networkidle2', timeout: 45000 });

// Already logged in from a prior run?
if (!p.url().includes('/login')) {
  console.log('already authenticated, url:', p.url());
} else {
  await p.type('#email', EMAIL, { delay: 15 });
  await p.type('#password', PASS, { delay: 15 });
  await Promise.all([
    p.waitForNavigation({ waitUntil: 'networkidle2', timeout: 45000 }),
    p.click('button[type=submit]'),
  ]);
}

const url = p.url();
const title = await p.title();
const loginErr = await p.evaluate(() => {
  const el = document.querySelector('.alert, .flash, .error, [role=alert]');
  return el ? el.innerText.slice(0, 120) : null;
});

// Enumerate podcasts/shows visible on the dashboard so we can pick Beer With Geeks.
const links = await p.evaluate(() =>
  [...document.querySelectorAll('a')]
    .map(a => ({ text: (a.innerText || '').trim().slice(0, 40), href: a.href }))
    .filter(l => l.text && (/podcast|show|episode|dashboard/i.test(l.href) || /beer|geek/i.test(l.text)))
    .slice(0, 40)
);

await p.screenshot({ path: '/home/frank/.openclaw/workspace/bin/fireside/step-dashboard.png', fullPage: true });

console.log(JSON.stringify({
  ok: !url.includes('/login'),
  url, title, loginErr,
  links,
}, null, 1));

await b.close();
