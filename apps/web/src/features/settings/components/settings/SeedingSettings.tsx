"use client";

/**
 * SeedingSettings -- seed demo strategies for VEuPathDB databases.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { seedExperiments } from "@/features/settings/api/experiments";
import { invalidateUserScopedQueries } from "@/lib/query/invalidateUserScoped";
import Image from "next/image";
import { Loader2, FlaskConical } from "lucide-react";
import { SettingsField } from "./SettingsField";

const SEED_DATABASES = [
  { id: "plasmodb", label: "PlasmoDB", description: "P. falciparum malaria" },
  { id: "toxodb", label: "ToxoDB", description: "T. gondii toxoplasmosis" },
  { id: "cryptodb", label: "CryptoDB", description: "Cryptosporidium" },
  {
    id: "piroplasmadb",
    label: "PiroplasmaDB",
    description: "B. bovis babesiosis",
  },
  {
    id: "tritrypdb",
    label: "TriTrypDB",
    description: "Leishmania & Trypanosoma",
  },
  {
    id: "fungidb",
    label: "FungiDB",
    description: "A. fumigatus aspergillosis",
  },
  {
    id: "vectorbase",
    label: "VectorBase",
    description: "A. gambiae mosquito",
  },
  { id: "giardiadb", label: "GiardiaDB", description: "Giardia lamblia" },
  {
    id: "amoebadb",
    label: "AmoebaDB",
    description: "E. histolytica amoeba",
  },
  {
    id: "microsporidiadb",
    label: "MicrosporidiaDB",
    description: "E. cuniculi microsporidia",
  },
  {
    id: "hostdb",
    label: "HostDB",
    description: "Human host immune response",
  },
  {
    id: "trichdb",
    label: "TrichDB",
    description: "T. vaginalis trichomoniasis",
  },
  { id: "veupathdb", label: "VEuPathDB", description: "Cross-species portal" },
  { id: "orthomcl", label: "OrthoMCL", description: "Ortholog groups" },
] as const;

export function SeedingSettings() {
  const queryClient = useQueryClient();

  const [seedingDb, setSeedingDb] = useState<string | null>(null);
  const [seedStatus, setSeedStatus] = useState<string | null>(null);

  const handleSeed = async (siteId?: string) => {
    setSeedingDb(siteId ?? "all");
    setSeedStatus("Starting...");
    try {
      await seedExperiments((message) => setSeedStatus(message), siteId);
    } catch (err) {
      setSeedStatus(`Error: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setSeedingDb(null);
      invalidateUserScopedQueries(queryClient);
    }
  };

  return (
    <div className="space-y-5">
      <SettingsField label="Seed demo strategies">
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={seedingDb !== null}
              onClick={() => void handleSeed()}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
            >
              {seedingDb === "all" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <FlaskConical className="h-3.5 w-3.5" />
              )}
              {seedingDb === "all" ? "Seeding All..." : "Seed All Databases"}
            </button>
            {seedStatus != null && (
              <span className="text-xs text-muted-foreground">{seedStatus}</span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {SEED_DATABASES.map((db) => (
              <button
                key={db.id}
                type="button"
                disabled={seedingDb !== null}
                onClick={() => void handleSeed(db.id)}
                className="flex items-start gap-2 rounded-md border border-border px-2.5 py-2 text-left text-xs transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
              >
                {seedingDb === db.id ? (
                  <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
                ) : (
                  <Image
                    src={`/icons/${db.id}.png`}
                    alt={db.label}
                    width={16}
                    height={16}
                    className="mt-0.5 h-4 w-4 shrink-0"
                  />
                )}
                <div className="min-w-0">
                  <div className="font-medium text-foreground">{db.label}</div>
                  <div className="truncate text-muted-foreground">{db.description}</div>
                </div>
              </button>
            ))}
          </div>

          <p className="text-xs text-muted-foreground">
            Seeds demo strategies and control sets for the selected database. Strategies
            appear in the sidebar; control sets are available in the Experiments tab.
          </p>
        </div>
      </SettingsField>
    </div>
  );
}
