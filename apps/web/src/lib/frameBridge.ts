const PATHFINDER_LOCATION = "pathfinder:location";

let lastPosted: string | null = null;

export function sameOriginFramer(win: Window): Window | null {
  const parent = win.parent;
  if (parent === win) return null;
  try {
    return parent.location.origin === win.location.origin ? parent : null;
  } catch {
    return null;
  }
}

export function reportLocation(win: Window, path: string): void {
  const framer = sameOriginFramer(win);
  if (framer === null || path === lastPosted) return;
  framer.postMessage({ type: PATHFINDER_LOCATION, path }, win.location.origin);
  lastPosted = path;
}

export function goToWebsitePage(win: Window, sitePageUrl: string, path: string): void {
  if (win.parent !== win || !URL.canParse(sitePageUrl)) return;
  if (new URL(sitePageUrl).origin !== win.location.origin) return;
  win.location.replace(`${sitePageUrl}${path}`);
}
