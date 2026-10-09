import { sameOriginFramer } from "./frameBridge";

const SAME_ORIGIN = "http://same-origin.invalid";

export function signInHref(siteSignInUrl: string, destination: string): string {
  const url = new URL(siteSignInUrl, SAME_ORIGIN);
  url.searchParams.set("destination", destination);
  return url.origin === SAME_ORIGIN ? `${url.pathname}${url.search}` : url.href;
}

export function goToSiteSignIn(win: Window, siteSignInUrl: string): void {
  const page = sameOriginFramer(win) ?? win;
  page.location.assign(signInHref(siteSignInUrl, page.location.href));
}
