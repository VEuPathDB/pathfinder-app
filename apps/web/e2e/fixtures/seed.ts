import type { APIRequestContext } from "@playwright/test";
import { request } from "@playwright/test";

import { CSRF_HEADERS } from "./api-client";
import { wdkTestToken } from "./wdk-account";

/**
 * Reference data fetched from live VEuPathDB APIs.
 *
 * Worker-scoped: fetched once per Playwright worker process.
 * Read-only: tests never mutate this data.
 */

/** Per-site gene data used by journey tests. */
interface SiteGeneData {
  /** Known gene IDs verified against the live VEuPathDB site. */
  geneIds: string[];
  /** Default organism for GenesByTaxon search on this site. */
  organism: string;
}

export interface SeedData {
  /** Known PlasmoDB gene IDs (malaria drug resistance markers). */
  plasmoGenes: string[];
  /** Known ToxoDB gene IDs (host invasion machinery). */
  toxoGenes: string[];
  /** Per-site gene data for journey tests across all 5 databases. */
  siteData: Record<string, SiteGeneData>;
}

/**
 * Fetch reference gene IDs from live VEuPathDB.
 *
 * Uses the PathFinder gene search endpoint, which calls real WDK APIs. A
 * refused or failed call throws: seeding a spec with unverified ids turns a
 * broken API into a wrong gene count. Gene resolution is a WDK call, and
 * VEuPathDB answers a guest with an empty record set instead of an error, so
 * the client carries the registered account token.
 */
export async function fetchSeedData(baseURL: string): Promise<SeedData> {
  const api = await request.newContext({
    baseURL,
    extraHTTPHeaders: {
      ...CSRF_HEADERS,
      Cookie: `Authorization=${wdkTestToken()}`,
    },
  });
  try {
    return await collectSeedData(api);
  } finally {
    await api.dispose();
  }
}

/** One site's seed: the organism the journey stays inside, the text query
 * and the curated ids that stand in when the search answers with too few. */
interface SiteSeed {
  organism: string;
  query: string;
  curated: string[];
}

const SITE_SEEDS: Record<string, SiteSeed> = {
  plasmodb: {
    organism: "Plasmodium falciparum 3D7",
    query: "chloroquine resistance",
    curated: [
      "PF3D7_0709000", // CRT (chloroquine resistance transporter)
      "PF3D7_1343700", // Kelch13 (artemisinin resistance)
      "PF3D7_0523000", // MDR1 (multidrug resistance)
      "PF3D7_0810800", // DHFR-TS (antifolate resistance)
      "PF3D7_0417200", // DHPS (sulfadoxine resistance)
    ],
  },
  toxodb: {
    organism: "Toxoplasma gondii ME49",
    query: "invasion",
    curated: [
      "TGME49_261080", // MIC2 (micronemal protein)
      "TGME49_233460", // RON4 (rhoptry neck protein)
      "TGME49_300100", // AMA1 (apical membrane antigen)
    ],
  },
  tritrypdb: {
    organism: "Leishmania major strain Friedlin",
    query: "surface protease",
    curated: [
      "LmjF.10.0460", // MSP (major surface protease / GP63)
      "LmjF.35.0010", // A2 family (amastigote-specific)
      "LmjF.33.1740", // Cysteine peptidase B
    ],
  },
  cryptodb: {
    organism: "Cryptosporidium parvum Iowa II",
    query: "oocyst wall",
    curated: [
      "cgd7_5030", // COWP1 (oocyst wall protein)
      "cgd6_1080", // COWP-domain protein
      "cgd3_920", // GP60 (surface glycoprotein)
    ],
  },
  fungidb: {
    organism: "Aspergillus fumigatus Af293",
    query: "glucan synthase",
    curated: [
      "AFUA_6G12400", // FKS1 (beta-1,3-glucan synthase)
      "AFUA_2G13440", // Chitin synthase
      "AFUA_2G05340", // GEL2 (beta-1,3-glucanosyltransferase)
    ],
  },
};

async function collectSeedData(api: APIRequestContext): Promise<SeedData> {
  const siteData: Record<string, SiteGeneData> = {};
  for (const [siteId, seed] of Object.entries(SITE_SEEDS)) {
    siteData[siteId] = {
      geneIds: await fetchGeneIds(api, siteId, seed),
      organism: seed.organism,
    };
  }
  const plasmo = siteData["plasmodb"];
  const toxo = siteData["toxodb"];
  if (plasmo === undefined || toxo === undefined) {
    throw new Error("plasmodb and toxodb seeds are always collected");
  }
  return {
    plasmoGenes: plasmo.geneIds,
    toxoGenes: toxo.geneIds,
    siteData,
  };
}

/**
 * Gene ids of one organism. The text search reaches every organism the site
 * hosts, and an enrichment analysis tests one organism's genes against its own
 * genome, so the search is narrowed to the seed's organism.
 */
async function fetchGeneIds(
  api: APIRequestContext,
  siteId: string,
  { organism, query, curated }: SiteSeed,
): Promise<string[]> {
  const params = new URLSearchParams({ q: query, organism, limit: "10" });
  const searchPath = `/api/v1/sites/${siteId}/genes/search?${params.toString()}`;
  const resp = await api.get(searchPath);
  if (!resp.ok()) {
    throw new Error(`gene search ${siteId} ${resp.status()}: ${await resp.text()}`);
  }
  const data = (await resp.json()) as {
    results?: { geneId: string; organism: string }[];
  };
  const hits = (data.results ?? []).map((r) => r.geneId);
  const found = hits.length === 0 ? [] : await resolveOnSite(api, siteId, hits);
  if (found.length >= curated.length) return found;

  // The search can answer with fewer genes than a spec needs. The curated ids
  // stand in for that case, and they are resolved the same way rather than
  // assumed.
  const known = await resolveOnSite(api, siteId, curated);
  if (known.length < curated.length) {
    throw new Error(
      `${siteId} resolves ${known.length} of ${curated.length} curated gene ids`,
    );
  }
  return known;
}

/** The subset of `geneIds` that WDK holds a record for on `siteId`. */
async function resolveOnSite(
  api: APIRequestContext,
  siteId: string,
  geneIds: string[],
): Promise<string[]> {
  const resp = await api.post(`/api/v1/sites/${siteId}/genes/resolve`, {
    data: { geneIds },
  });
  if (!resp.ok()) {
    throw new Error(`gene resolve ${siteId} ${resp.status()}: ${await resp.text()}`);
  }
  const body = (await resp.json()) as { resolved: { geneId: string }[] };
  return body.resolved.map((r) => r.geneId);
}
