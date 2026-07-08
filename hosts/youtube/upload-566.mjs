import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";

const VIDEO = "/home/frank/.openclaw/workspace/share/bwg/master_566.mp4";
const SOURCE_PROFILE = "/home/frank/.config/google-chrome";
const PROFILE = "/tmp/openclaw-youtube-profile-566";
const TITLE = "Lanterns Trailer 2 BREAKDOWN — Kyle Chandler IS Hal Jordan | Beer With Geeks 566";
const DESCRIPTION = `Frank and Tim both showed up to the recording in green (neither planned it), Tim forgot his beer, and Frank is very much drinking a Winter Lager in ninety-five-degree heat. Then they read four pages of a Superman novel and break down the second Lanterns teaser trailer — the one that addressed every single fan complaint.

Way more green. Way more sci-fi. Kyle Chandler is Hal Jordan in a way Ryan Reynolds was never Hal Jordan. The shoulder situation on the suit is real. And Frank has a theory: Hal becomes Parallax by the end of season one. Which would be poetic, comic-canon, and also kind of a bummer.

📺 Trailer breakdown starts at 09:54.

🍺 Beers of the Week: Sam Adams Winter Lager & Two Pitchers Nordic Jam

⏱️ Chapters
00:00 Welcome — accidental green shirts, deliberate beer
00:45 Tim exits for beer; Frank defends the off-season Winter Lager
02:20 Tim returns (his daughter had questions)
03:05 Introducing Two Pitchers Nordic Jam
03:51 First taste — "it's not overly tart"
04:37 "A tart start" — the flavor, then philosophy
05:22 Founded by two lousy baseball pitchers
06:07 Dramatic reading: Clark/Superman novelization by CJ Cherry
07:39 Page four done — the Miscellany problem
08:24 Why novelization prose can work against you on audio
09:09 Transition: Lanterns is coming in August
09:54 Second Lanterns teaser — way more substance, way more green
10:40 Addressing the fan backlash ("where's the green?")
11:28 Kyle Chandler as Hal Jordan: on board since day one, proven right
12:59 Kyle vs. Ryan Reynolds — the scruffy nerf-herder advantage
13:44 The suit and the shoulder situation
16:00 Guy Gardner confirmed / "Are you afraid?" — the central thesis
17:31 John Stewart's PTSD and the marine-corps parallel
18:17 Tom King's DNA in the show
19:51 Sinestro as Hal's trainer: what did he actually learn?
20:37 Does Hal become Parallax this season?
22:56 John conquers fear; Hal's bravado gets him
23:42 Laura Linney: Carol Ferris or original character?
25:14 Ring constructs — the intangible made visible
28:19 Will they say the oath?
30:35 "He's a silly boy in a silly movie" — on tone
32:51 Secret identities: space cops don't need masks
34:24 Dollar bills, toilet paper, and the mundane use of power / Cheers

🎧 Full show: https://beerwithgeeks.com — on every podcast app.
👍 Like, subscribe, and tell a friend. It really helps.

#GreenLantern #Lanterns #HBOMax #HalJordan #JohnStewart #KyleChandler #AaronPierre #DCU #JamesGunn #TrailerBreakdown #beerwithgeeks #moviepodcast #comicbookpodcast`;

const TAGS = [
  "Green Lantern",
  "Lanterns",
  "Lanterns HBO",
  "Lanterns trailer",
  "Lanterns trailer breakdown",
  "Hal Jordan",
  "John Stewart",
  "Kyle Chandler",
  "Aaron Pierre",
  "Guy Gardner",
  "Sinestro",
  "Parallax",
  "Carol Ferris",
  "Laura Linney",
  "Tom King",
  "DC",
  "DCU",
  "James Gunn",
  "DC Comics",
  "trailer reaction",
  "trailer breakdown",
  "HBO Max",
  "superhero show",
  "second teaser",
  "beer podcast",
  "beer with geeks",
  "BwG",
  "movie podcast",
  "geek podcast",
  "comic book",
  "comic book podcast",
  "Superman",
  "Sam Adams",
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
    await page.screenshot({ path: "/home/frank/.openclaw/workspace/bin/youtube-566-login-blocker.png", fullPage: true }).catch(() => {});
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

  await page.screenshot({ path: "/home/frank/.openclaw/workspace/bin/youtube-566-final.png", fullPage: true }).catch(() => {});
  await browser.close();
}

main().catch(async (err) => {
  console.error("UPLOAD FAILED:", err?.stack || err?.message || String(err));
  process.exitCode = 1;
});
