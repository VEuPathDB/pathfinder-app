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

async function collectSeedData(api: APIRequestContext): Promise<SeedData> {
  const plasmoGenes = await fetchGeneIds(api, "plasmodb", "chloroquine resistance", [
    "PF3D7_0709000", // CRT (chloroquine resistance transporter)
    "PF3D7_1343700", // Kelch13 (artemisinin resistance)
    "PF3D7_0523000", // MDR1 (multidrug resistance)
    "PF3D7_0810800", // DHFR-TS (antifolate resistance)
    "PF3D7_0417200", // DHPS (sulfadoxine resistance)
  ]);

  const toxoGenes = await fetchGeneIds(api, "toxodb", "invasion", [
    "TGME49_261080", // MIC2 (micronemal protein)
    "TGME49_233460", // RON4 (rhoptry neck protein)
    "TGME49_300100", // AMA1 (apical membrane antigen)
  ]);

  const tritrypGenes = await fetchGeneIds(api, "tritrypdb", "surface protease", [
    "LmjF.10.0460", // MSP (major surface protease / GP63)
    "LmjF.35.0010", // A2 family (amastigote-specific)
    "LmjF.33.1740", // Cysteine peptidase B
  ]);

  const cryptoGenes = await fetchGeneIds(api, "cryptodb", "oocyst wall", [
    "cgd7_5030", // COWP1 (oocyst wall protein)
    "cgd6_1080", // COWP-domain protein
    "cgd3_920", // GP60 (surface glycoprotein)
  ]);

  const fungiGenes = await fetchGeneIds(api, "fungidb", "glucan synthase", [
    "AFUA_6G12400", // FKS1 (beta-1,3-glucan synthase)
    "AFUA_2G13440", // Chitin synthase
    "AFUA_2G05340", // GEL2 (beta-1,3-glucanosyltransferase)
  ]);

  const siteData: Record<string, SiteGeneData> = {
    plasmodb: {
      geneIds: plasmoGenes,
      organism: "Plasmodium falciparum 3D7",
    },
    toxodb: {
      geneIds: toxoGenes,
      organism: "Toxoplasma gondii ME49",
    },
    tritrypdb: {
      geneIds: tritrypGenes,
      organism: "Leishmania major strain Friedlin",
    },
    cryptodb: {
      geneIds: cryptoGenes,
      organism: "Cryptosporidium parvum Iowa II",
    },
    fungidb: {
      geneIds: fungiGenes,
      organism: "Aspergillus fumigatus Af293",
    },
  };

  return {
    plasmoGenes,
    toxoGenes,
    siteData,
  };
}

async function fetchGeneIds(
  api: APIRequestContext,
  siteId: string,
  query: string,
  curated: string[],
): Promise<string[]> {
  const searchPath = `/api/v1/sites/${siteId}/genes/search?q=${encodeURIComponent(query)}&limit=10`;
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

  // The text search reaches every site, so it can answer with fewer genes of
  // this site than a spec needs. The curated ids stand in for that case, and
  // they are resolved the same way rather than assumed.
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
