import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";

const VIDEO = "/home/frank/.openclaw/workspace/share/bwg-567/master_567_edit_v3.mp4";
const SOURCE_PROFILE = "/home/frank/.config/google-chrome";
const PROFILE = "/tmp/openclaw-youtube-profile-567";
const TITLE = "Spider-Man Isn't a Street-Level Hero (Here's Why) | Beer With Geeks 567";
const DESCRIPTION = `Spider-Man isn't a street-level hero. Neither is Batman. We spent 35 minutes ranking every Spider-Man villain to figure out why — and the whole "street-level" label kind of falls apart.

Tim and Frank came in for a quick five-minute genre argument. We came out with a Breaking Bad analogy, a rogues-gallery tally, an H.P. Lovecraft detour, and a very unresolved take on what "street-level" even means when your hero is swinging above the street.

Plus: Clark Kent finally becomes Superman across one gorgeous page of prose. Because of course he does.

🍺 Beers of the Week
Sam Adams Porch Rocker Lemon Radler (Frank)
Stormalong Legendary Dry Hard Cider — Millis, MA (Tim)

⏱️ Chapters
00:00 Cold open — the Breaking Bad test
00:11 Beers: Porch Rocker + Stormalong dry cider
03:20 H.P. Lovecraft, Providence, and the racism asterisk
05:20 Is Spider-Man street-level at all?
09:00 What "street-level" even means (Daredevil, tone, stakes)
15:00 Peter Parker's sci-fi problem
21:00 Ranking every Spider-Man villain
26:35 The tally: 5 street / 6 middle / 1 cosmic
27:55 The Breaking Bad line, in context
31:35 Superman: The Never-Ending Battle (chapter read)
34:30 Wrap + share the show

🎧 Full show: https://beerwithgeeks.com — on every podcast app.
👍 Like, subscribe, and tell a friend. It really helps.

If you argue about comics in group chats, hit subscribe. If you like the show, share this one with the friend who won't shut up about Spider-Man movies.

#SpiderMan #Comics #Marvel #Podcast #MCU #NoWayHome #SpiderMan4 #BrandNewDay #Kraven #Kingpin #BatmanStreetLevel #beerwithgeeks #moviepodcast #comicbookpodcast`;

const TAGS = [
  "spider-man",
  "spider-man street level",
  "is spider-man street level",
  "spider-man villains ranked",
  "spider-man rogues gallery",
  "spider-man debate",
  "spider-man podcast",
  "marvel podcast",
  "comic book podcast",
  "comic book debate",
  "breaking bad spider-man",
  "batman street level",
  "daredevil street level",
  "kraven the hunter",
  "kingpin",
  "mcu spider-man",
  "no way home",
  "spider-man analysis",
  "beer with geeks",
  "bwg",
  "spider-man 4",
  "brand new day",
  "superhero subgenre",
  "comics ranking",
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function prepareProfile() {
  fs.rmSync(PROFILE, { recursive: true, force: true });
  fs.mkdirSync(PROFILE, { recursive: true });
  const essentials = [
    "Local State",
    path.join("Default", "Preferences"),
    path.join("Default", "Secure Preferences"),
    path.join("Default", "Cookies"),
    path.join("Default", "Network Persistent State"),
    path.join("Default", "Login Data"),
    path.join("Default", "Login Data For Account"),
    path.join("Default", "Web Data"),
    path.join("Default", "Account Web Data"),
    path.join("Default", "TransportSecurity"),
  ];
  for (const rel of essentials) {
    const src = path.join(SOURCE_PROFILE, rel);
    if (!fs.existsSync(src)) continue;
    const dst = path.join(PROFILE, rel);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.cpSync(src, dst, { recursive: true, force: true });
  }
}

async function waitForAnyText(page, patterns, timeoutMs = 120000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const text = await page.evaluate(() => document.body?.innerText || "");
    for (const pattern of patterns) {
      if (pattern.test(text)) return text;
    }
    await sleep(2000);
  }
  throw new Error(`Timed out waiting for one of: ${patterns.map((p) => p.source).join(", ")}`);
}

async function clickText(page, text) {
  return page.evaluate((needle) => {
    const all = [...document.querySelectorAll('button, tp-yt-paper-button, ytcp-button, a, div[role="button"], span, div')];
    const match = all.find((el) => {
      const t = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
      return t === needle || t.includes(needle);
    });
    if (!match) return false;
    const target = match.closest('button, tp-yt-paper-button, ytcp-button, a, div[role="button"]') || match;
    target.click();
    return true;
  }, text);
}

async function clickTextEventually(page, text, timeoutMs = 60000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const clicked = await clickText(page, text);
    if (clicked) return true;
    await sleep(1000);
  }
  return false;
}

async function logTextboxes(page, label) {
  const items = await page.evaluate(() =>
    [...document.querySelectorAll('[contenteditable="true"], input, textarea')]
      .map((el) => ({
        tag: el.tagName,
        aria: el.getAttribute("aria-label"),
        placeholder: el.getAttribute("placeholder"),
        id: el.id || "",
        text: (el.innerText || el.value || "").slice(0, 80),
        visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      }))
      .filter((item) => item.visible)
      .slice(0, 20)
  );
  console.log(label, JSON.stringify(items, null, 2));
}

async function fillContenteditable(page, index, value) {
  await page.evaluate(
    ({ index, value }) => {
      const boxes = [...document.querySelectorAll('[contenteditable="true"]')].filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      });
      const box = boxes[index];
      if (!box) throw new Error(`No contenteditable at index ${index}`);
      box.focus();
      box.innerText = value;
      box.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
      box.dispatchEvent(new Event("change", { bubbles: true }));
      box.dispatchEvent(new Event("blur", { bubbles: true }));
    },
    { index, value }
  );
}

async function pickRadioByLabel(page, labelText) {
  const ok = await page.evaluate((needle) => {
    const labels = [...document.querySelectorAll('tp-yt-paper-radio-button, ytcp-ve, label, div, span')];
    const match = labels.find((el) => {
      const t = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
      return t === needle || t.includes(needle);
    });
    if (!match) return false;
    const target = match.closest('tp-yt-paper-radio-button, ytcp-ve, label, div[role="radio"]') || match;
    target.click();
    return true;
  }, labelText);
  return ok;
}

async function main() {
  if (!fs.existsSync(VIDEO)) throw new Error(`Missing video file: ${VIDEO}`);
  const stats = fs.statSync(VIDEO);
  console.log(`video: ${path.basename(VIDEO)} (${Math.round(stats.size / 1024 / 1024)} MB)`);
  prepareProfile();

  const browser = await puppeteer.launch({
    executablePath: "/usr/bin/google-chrome",
    headless: "new",
    userDataDir: PROFILE,
    pipe: true,
    timeout: 120000,
    protocolTimeout: 120000,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1600,2400"],
  });
  const page = await browser.newPage();
  page.setDefaultTimeout(60000);
  await page.setViewport({ width: 1600, height: 2400 });

  console.log("opening studio...");
  await page.goto("https://studio.youtube.com", { waitUntil: "domcontentloaded", timeout: 120000 }).catch(() => {});
  const firstText = await page.evaluate(() => document.body?.innerText || "");
  if (/sign in|choose an account|accounts\.google\.com/i.test(firstText) || /accounts\.google\.com/i.test(page.url())) {
    await page.screenshot({ path: "/home/frank/.openclaw/workspace/bin/youtube-567-login-blocker.png", fullPage: true }).catch(() => {});
    throw new Error(`Google sign-in blocker at ${page.url()}`);
  }
  console.log(`studio url: ${page.url()}`);

  let clicked = await clickTextEventually(page, "Create", 45000);
  if (!clicked) throw new Error('Could not find "Create" button');
  await sleep(1500);
  clicked = await clickTextEventually(page, "Upload videos", 30000);
  if (!clicked) throw new Error('Could not find "Upload videos" option');

  console.log("waiting for upload page...");
  await page.waitForSelector('input[type="file"]', { timeout: 120000 });
  const fileInput = await page.$('input[type="file"]');
  if (!fileInput) throw new Error("No file input found");
  console.log("starting file upload...");
  await fileInput.uploadFile(VIDEO);

  await waitForAnyText(page, [/title/i, /details/i, /video details/i, /your video has uploaded/i], 120000);
  await logTextboxes(page, "editable fields after upload");

  const bodyText = await page.evaluate(() => document.body?.innerText || "");
  if (/made for kids/i.test(bodyText)) {
    console.log("selecting audience...");
    await pickRadioByLabel(page, "No, it's not made for kids");
  }

  console.log("filling title/description...");
  await fillContenteditable(page, 0, TITLE);
  await fillContenteditable(page, 1, DESCRIPTION);

  for (let i = 0; i < 3; i++) {
    console.log(`next step ${i + 1}...`);
    await clickTextEventually(page, "Next", 45000);
    await sleep(2500);
  }

  const visibilityText = await page.evaluate(() => document.body?.innerText || "");
  if (/visibility/i.test(visibilityText) || /private|unlisted|public/i.test(visibilityText)) {
    console.log("setting visibility to Private...");
    await pickRadioByLabel(page, "Private");
    await sleep(1500);
  }

  await logTextboxes(page, "before save");
  console.log("saving...");
  const saveClicked = await clickTextEventually(page, "Save", 45000) || await clickTextEventually(page, "Done", 15000);
  if (!saveClicked) throw new Error('Could not find "Save" or "Done"');

  await sleep(5000);
  const finalText = await page.evaluate(() => document.body?.innerText || "");
  console.log("final url:", page.url());
  console.log(finalText.slice(0, 2000));

  await page.screenshot({ path: "/home/frank/.openclaw/workspace/bin/youtube-567-final.png", fullPage: true }).catch(() => {});
  await browser.close();
}

main().catch(async (err) => {
  console.error("UPLOAD FAILED:", err?.stack || err?.message || String(err));
  process.exitCode = 1;
});
