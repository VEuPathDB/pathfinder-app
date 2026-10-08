import { sameOriginFramer } from "./frameBridge";

export function signInHref(siteSignInUrl: string, destination: string): string {
  const url = new URL(siteSignInUrl);
  url.searchParams.set("destination", destination);
  return url.href;
}

export function goToSiteSignIn(win: Window, siteSignInUrl: string): void {
  const page = sameOriginFramer(win) ?? win;
  page.location.assign(signInHref(siteSignInUrl, page.location.href));
}
