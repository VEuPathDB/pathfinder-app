/**
 * Per-site header banners from VEuPathDB ApiCommonWebsite, stored locally
 * in public/banners/. Header always uses a dark overlay and white text.
 */

/** When set, the site header uses white text (dark overlay). */
export type HeaderTextVariant = "light";

interface SiteBannerConfig {
  /** Path under public/ (e.g. /banners/plasmodb.jpg). */
  imagePath: string;
}

const BANNERS: Record<string, SiteBannerConfig> = {
  plasmodb: { imagePath: "/banners/plasmodb.jpg" },
  toxodb: { imagePath: "/banners/toxodb.jpg" },
  cryptodb: { imagePath: "/banners/cryptodb.jpg" },
  veupathdb: { imagePath: "/banners/veupathdb.jpg" },
  giardiadb: { imagePath: "/banners/giardiadb.jpg" },
  amoebadb: { imagePath: "/banners/amoebadb.jpg" },
  microsporidiadb: { imagePath: "/banners/microsporidiadb.jpg" },
  piroplasmadb: { imagePath: "/banners/piroplasmadb.jpg" },
  tritrypdb: { imagePath: "/banners/tritrypdb.jpg" },
  fungidb: { imagePath: "/banners/fungidb.jpg" },
  hostdb: { imagePath: "/banners/hostdb.jpg" },
  vectorbase: { imagePath: "/banners/vectorbase.jpg" },
  schistodb: { imagePath: "/banners/schistodb.jpg" },
  trichdb: { imagePath: "/banners/trichdb.jpg" },
};

const DEFAULT_BANNER: SiteBannerConfig = {
  imagePath: "/banners/veupathdb.jpg",
};

/**
 * Returns banner config for a site. Uses VEuPathDB portal banner for unknown sites.
 */
export function getSiteBanner(siteId: string): SiteBannerConfig {
  const key = siteId.toLowerCase();
  return BANNERS[key] ?? DEFAULT_BANNER;
}
